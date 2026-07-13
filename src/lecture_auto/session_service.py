from __future__ import annotations

import json
import os
import shutil
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import typer

from lecture_auto.capture_runtime import (
    CaptureDependencyError,
    CaptureDeviceError,
    CaptureInterruptedError,
    CapturePermissionError,
    CaptureRuntimeAdapter,
    CaptureRuntimeError,
    NoopCaptureRuntimeAdapter,
)
from lecture_auto.stt_config import STTConfig
from lecture_auto.tasking import CancellationToken, ProgressCallback, report_progress
from lecture_auto.stt_runtime import (
    APISTTRuntimeAdapter,
    LocalSTTRuntimeAdapter,
    STTAudioDecodeError,
    STTConfigError,
    STTProviderAuthError,
    STTRuntimeAdapter,
    STTRuntimeError,
    STTTransientNetworkError,
)
from lecture_auto.session_metadata_store import SessionMetadataStore
from lecture_auto.llm_adapter import (
    LLMProviderAdapter,
    LLMConfigError,
    LLMProviderAuthError,
    LLMTransientNetworkError,
)
from lecture_auto.audio_amplifier import AudioAmplificationError, amplified_audio_input
from lecture_auto.document_converter import (
    DocumentConversionError,
    is_supported_format,
    convert_to_pdf,
)
from lecture_auto.local_runtime import LocalRuntimeManager, LocalRuntimeMissingError

VALID_STATES = {"idle", "recording", "stopping", "completed", "failed"}
ALLOWED_TRANSITIONS = {
    "idle": {"recording"},
    "recording": {"stopping", "failed"},
    "stopping": {"completed", "failed"},
    "completed": {"recording"},
    "failed": {"recording"},
}

SUPPORTED_IMPORT_EXTENSIONS = {"wav", "mp3"}
JOB_VALID_STATES = {"queued", "running", "succeeded", "failed", "canceled"}
JOB_ALLOWED_TRANSITIONS = {
    None: {"queued"},
    "queued": {"running", "failed", "canceled"},
    "running": {"succeeded", "failed", "canceled"},
    "succeeded": set(),
    "failed": {"queued"},
    "canceled": {"queued"},
}
MAX_IMPORT_RETRIES = 3
MAX_STT_API_RETRIES = 2
DEFAULT_NOTE_TEMPLATE_NAME = "structured-notes"

# Sentinel used by session_update_metadata to distinguish "not provided" from explicit None
_UNSET = object()


class SessionCommandError(RuntimeError):
    def __init__(self, code: str, message: str, guidance: str, exit_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.guidance = guidance
        self.exit_code = exit_code


@dataclass
class CommandResult:
    command: str
    payload: dict[str, Any]
    message: str

    def as_text(self) -> str:
        return self.message

    def as_json_line(self) -> str:
        return json.dumps(
            {"command": self.command, "payload": self.payload, "message": self.message},
            ensure_ascii=False,
            separators=(",", ":"),
        )


class SessionService:
    def __init__(
        self,
        store: SessionMetadataStore,
        runtime_adapter: CaptureRuntimeAdapter | None = None,
        stt_config: STTConfig | None = None,
        local_stt_adapter: STTRuntimeAdapter | None = None,
        api_stt_adapter: STTRuntimeAdapter | None = None,
        llm_adapter: LLMProviderAdapter | None = None,
        local_runtime_manager: LocalRuntimeManager | None = None,
        audio_format: str = "wav",
    ) -> None:
        self.store = store
        self.runtime_adapter = runtime_adapter or NoopCaptureRuntimeAdapter()
        self.stt_config = stt_config or STTConfig()
        self._local_stt_adapter = local_stt_adapter
        self._api_stt_adapter = api_stt_adapter
        self.llm_adapter = llm_adapter
        self.local_runtime_manager = local_runtime_manager
        self.audio_format = audio_format
        self._migrate_legacy_artifact_paths()

    def session_create(
        self,
        session_id: str,
        date: str,
        title: str | None = None,
        course: str | None = None,
    ) -> CommandResult:
        if self.store.get_by_session_id(session_id) is not None:
            raise SessionCommandError(
                code="SESSION_ID_CONFLICT",
                message=f"Session '{session_id}' already exists.",
                guidance="Choose a unique session ID.",
                exit_code=1,
            )

        naming_pending = not (title and course)
        metadata = {
            "session_id": session_id,
            "date": date,
            "title": title,
            "course": course,
            "status": "idle",
            "audio_file_path": None,
            "timestamps": {"created_at": self._utc_now()},
            "naming_pending": naming_pending,
        }

        saved = self._persist_or_raise(metadata)
        return CommandResult(
            command="session create",
            payload=saved,
            message=f"Session '{saved['session_id']}' created and ready to record.",
        )

    def capture_start(self, session_id: str, audio_file_path: str | None = None) -> CommandResult:
        session = self._require_session(session_id)
        self._transition_or_raise(session, target_state="recording")
        resolved_audio_path = audio_file_path or self.store.build_recording_path(
            session_id,
            extension=self.audio_format,
            course=session.get("course"),
        )
        metadata_root = self.store.metadata_file.parent.parent
        runtime_output_path = resolved_audio_path
        if not Path(resolved_audio_path).is_absolute():
            runtime_output_path = str((metadata_root / resolved_audio_path).resolve())

        append_mode = False
        original_output_path = runtime_output_path
        p_out = Path(runtime_output_path)
        if p_out.exists():
            append_mode = True
            part_suffix = f"-part{p_out.suffix}"
            runtime_output_path = str(p_out.with_name(f"{p_out.stem}{part_suffix}"))
            part_p = Path(runtime_output_path)
            if part_p.exists():
                part_p.unlink(missing_ok=True)

        try:
            handle = self.runtime_adapter.start_capture(
                session_id=session_id,
                output_path=runtime_output_path,
            )
        except CaptureDependencyError as exc:
            raise self.map_capture_failure("dependency") from exc
        except CapturePermissionError as exc:
            raise self.map_capture_failure("permission") from exc
        except CaptureDeviceError as exc:
            raise self.map_capture_failure("device") from exc
        except CaptureRuntimeError as exc:
            raise self.map_capture_failure("runtime") from exc

        session["audio_file_path"] = resolved_audio_path
        session.setdefault("timestamps", {})["recording_started_at"] = self._utc_now()
        session["timestamps"]["capture_process_id"] = handle.process_id
        session["timestamps"]["capture_backend"] = handle.backend
        
        if append_mode:
            session["timestamps"]["active_part_path"] = runtime_output_path
        else:
            session["timestamps"].pop("active_part_path", None)

        saved = self._persist_or_raise(session)
        return CommandResult(
            command="capture start",
            payload=saved,
            message=(
                f"Capture started for session '{session_id}'. "
                f"Output file: {resolved_audio_path}"
            ),
        )

    def capture_stop(self, session_id: str, *, success: bool = True) -> CommandResult:
        session = self._require_session(session_id)
        self._transition_or_raise(session, target_state="stopping")
        session["timestamps"]["stopping_at"] = self._utc_now()
        process_id_raw = session.get("timestamps", {}).get("capture_process_id")
        process_id = process_id_raw if isinstance(process_id_raw, int) else None

        try:
            self.runtime_adapter.stop_capture(
                session_id=session_id,
                interrupted=not success,
                process_id=process_id,
            )
        except CaptureInterruptedError as exc:
            raise self.map_capture_failure("interrupted") from exc
        except CaptureDependencyError as exc:
            raise self.map_capture_failure("dependency") from exc
        except CapturePermissionError as exc:
            raise self.map_capture_failure("permission") from exc
        except CaptureDeviceError as exc:
            raise self.map_capture_failure("device") from exc
        except CaptureRuntimeError as exc:
            raise self.map_capture_failure("runtime") from exc

        active_part_path_raw = session.get("timestamps", {}).pop("active_part_path", None)
        active_part_path = str(active_part_path_raw) if active_part_path_raw else None

        if success and active_part_path:
            base_audio_path = session.get("audio_file_path")
            metadata_root = self.store.metadata_file.parent.parent
            if base_audio_path and not Path(base_audio_path).is_absolute():
                base_audio_path_abs: str | None = str((metadata_root / base_audio_path).resolve())
            else:
                base_audio_path_abs = base_audio_path

            if base_audio_path_abs:
                try:
                    self._concat_audio(base_path=base_audio_path_abs, part_path=active_part_path)
                except Exception as exc:
                    success = False

        if not success and active_part_path and Path(active_part_path).exists():
            try:
                Path(active_part_path).unlink()
            except OSError:
                pass

        final_state = "completed" if success else "failed"
        self._transition_or_raise(session, target_state=final_state)
        if success:
            session["timestamps"]["recording_completed_at"] = self._utc_now()
            message = f"Capture stopped successfully for session '{session_id}'."
        else:
            session["timestamps"]["recording_failed_at"] = self._utc_now()
            message = (
                f"Capture stopped with failure for session '{session_id}'. "
                "Run diagnostics and retry capture start."
            )

        saved = self._persist_or_raise(session)
        return CommandResult(command="capture stop", payload=saved, message=message)

    def session_history(self) -> CommandResult:
        rows = self.store.list_recent_first()
        payload = {
            "count": len(rows),
            "sessions": [
                {
                    "session_id": row["session_id"],
                    "date": row["date"],
                    "title": row["title"],
                    "course": row["course"],
                    "status": row["status"],
                }
                for row in rows
            ],
        }
        return CommandResult(
            command="session history",
            payload=payload,
            message=f"Loaded {payload['count']} session(s) from local history.",
        )

    def recover_stale_recordings(self) -> list[str]:
        """Mark recording sessions failed when their saved capture process no longer exists."""
        recovered: list[str] = []
        for session in self.store.load_all():
            if session.get("status") != "recording":
                continue
            process_id = session.get("timestamps", {}).get("capture_process_id")
            alive = isinstance(process_id, int)
            if alive:
                try:
                    os.kill(process_id, 0)
                except (OSError, ProcessLookupError):
                    alive = False
            if alive:
                continue
            session["status"] = "failed"
            session.setdefault("timestamps", {})["recording_recovered_at"] = self._utc_now()
            self._persist_or_raise(session)
            recovered.append(session["session_id"])
        return recovered

    def session_detail(self, session_id: str) -> CommandResult:
        session = self._require_session(session_id)
        return CommandResult(
            command="session detail",
            payload=session,
            message=f"Loaded details for session '{session_id}'.",
        )

    def session_update_metadata(
        self,
        session_id: str,
        *,
        new_session_id: str | None = _UNSET,  # type: ignore[assignment]
        title: str | None = _UNSET,  # type: ignore[assignment]
        course: str | None = _UNSET,  # type: ignore[assignment]
        date: str | None = _UNSET,  # type: ignore[assignment]
    ) -> CommandResult:
        session = self._require_session(session_id)

        # Apply non-UNSET fields
        if title is not _UNSET:
            session["title"] = title or None
        if course is not _UNSET:
            session["course"] = course or None
        if date is not _UNSET:
            session["date"] = date

        # Recompute naming_pending based on current title/course
        session["naming_pending"] = not (session.get("title") and session.get("course"))

        session.setdefault("timestamps", {})["updated_at"] = self._utc_now()

        if new_session_id is not _UNSET:
            new_id = (new_session_id or "").strip()
            if not new_id:
                raise SessionCommandError(
                    code="SESSION_ID_REQUIRED",
                    message="new_session_id must be a non-empty string.",
                    guidance="Provide a valid session ID string.",
                    exit_code=1,
                )
            if new_id != session_id and self.store.get_by_session_id(new_id) is not None:
                raise SessionCommandError(
                    code="SESSION_ID_CONFLICT",
                    message=f"Session '{new_id}' already exists.",
                    guidance="Choose a unique session ID.",
                    exit_code=1,
                )

            if new_id != session_id:
                metadata_root = self.store.metadata_file.parent.parent

                # Collect file paths that need renaming
                rename_pairs: list[tuple[Path, Path]] = []
                for field in ("audio_file_path", "transcript_file_path"):
                    old_rel = session.get(field)
                    if old_rel and session_id in old_rel:
                        new_rel = old_rel.replace(session_id, new_id, 1)
                        old_abs = metadata_root / old_rel
                        new_abs = metadata_root / new_rel
                        if old_abs.exists():
                            rename_pairs.append((old_abs, new_abs))
                            session[field] = new_rel

                old_edited = metadata_root / self.store.build_edited_transcript_path(
                    session_id,
                    course=session.get("course"),
                )
                if old_edited.exists():
                    new_edited = metadata_root / self.store.build_edited_transcript_path(
                        new_id,
                        course=session.get("course"),
                    )
                    rename_pairs.append((old_edited, new_edited))

                # Perform renames before touching metadata
                try:
                    for old_path, new_path in rename_pairs:
                        new_path.parent.mkdir(parents=True, exist_ok=True)
                        old_path.rename(new_path)
                except OSError as exc:
                    raise SessionCommandError(
                        code="SESSION_FILE_RENAME_ERROR",
                        message=f"Failed to rename associated file: {exc}",
                        guidance="Check filesystem permissions and available disk space.",
                        exit_code=8,
                    ) from exc

                # Swap IDs in metadata store
                session["session_id"] = new_id
                self.store.delete(session_id)
                saved = self._persist_or_raise(session)
                return CommandResult(
                    command="session update",
                    payload=saved,
                    message=(
                        f"Session '{session_id}' renamed to '{new_id}' and metadata updated."
                    ),
                )

        saved = self._persist_or_raise(session)
        return CommandResult(
            command="session update",
            payload=saved,
            message=f"Session '{session_id}' metadata updated.",
        )

    def session_delete(self, session_id: str) -> CommandResult:
        session = self._require_session(session_id)
        
        metadata_root = self.store.metadata_file.parent.parent
        files_to_delete = []
        if session.get("audio_file_path"):
            files_to_delete.append(metadata_root / session["audio_file_path"])
        if session.get("transcript_file_path"):
            files_to_delete.append(metadata_root / session["transcript_file_path"])
        
        edited_transcript = metadata_root / self.store.build_edited_transcript_path(
            session_id,
            course=session.get("course"),
        )
        if edited_transcript.exists():
            files_to_delete.append(edited_transcript)
            
        deleted = self.store.delete(session_id)
        if not deleted:
            raise SessionCommandError(
                code="SESSION_DELETE_FAILED",
                message=f"Session '{session_id}' could not be deleted.",
                guidance="It might have been removed already.",
                exit_code=1,
            )
            
        for f in files_to_delete:
            try:
                if f.exists():
                    f.unlink()
            except OSError:
                pass
                
        return CommandResult(
            command="session delete",
            payload={"session_id": session_id},
            message=f"Session '{session_id}' and associated files have been deleted.",
        )

    def refine_audio_volume(self, session_id: str) -> CommandResult:
        """Apply audio volume refinement (dynaudnorm) to the session's audio recording."""
        session = self._require_session(session_id)
        if session["audio_file_path"] is None:
            raise SessionCommandError(
                code="REFINE_AUDIO_NO_SOURCE",
                message="No original audio found for refinement.",
                guidance="Please import or capture audio for this session first.",
                exit_code=1,
            )

        use_dyn = self.stt_config.use_dynaudnorm
        f = self.stt_config.dynaudnorm_f
        g = self.stt_config.dynaudnorm_g

        if not use_dyn:
            raise SessionCommandError(
                code="REFINE_AUDIO_DYNAUDNORM_DISABLED",
                message="Audio refinement requires use_dynaudnorm to be enabled in config.",
                guidance="Enable it via `config set --use-dynaudnorm True`.",
                exit_code=1,
            )

        source_rel_path = session.get("refined_audio_file_path") or session["audio_file_path"]
        source_path = self._resolve_audio_input_path(source_rel_path)
        # Volume filter ALWAYS outputs a true WAV via pcm_s16le
        source_extension = "wav"

        try:
            with amplified_audio_input(
                audio_path=source_path,
                use_dynaudnorm=use_dyn,
                dynaudnorm_f=f,
                dynaudnorm_g=g,
                gain_db=self.stt_config.gain_db,
            ) as output_tmp_path:
                refined_relative = self.store.build_refined_audio_path(
                    session_id,
                    extension=source_extension,
                    course=session.get("course"),
                )
                refined_abs = (self.store.metadata_file.parent.parent / refined_relative).resolve()
                refined_abs.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(output_tmp_path, refined_abs)

                session["refined_audio_file_path"] = refined_relative
                saved = self._persist_or_raise(session)

                return CommandResult(
                    command="audio refine",
                    payload=self._build_progress_payload(saved),
                    message=f"Successfully refined audio for session '{session_id}'.",
                )
        except AudioAmplificationError as exc:
            raise SessionCommandError(
                code="REFINE_AUDIO_FAILED",
                message="Audio amplification process failed.",
                guidance=str(exc),
                exit_code=1,
            ) from exc

    def refine_audio_noise(
        self,
        session_id: str,
        *,
        progress_callback: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
        job_id: str = "deepfilter",
    ) -> CommandResult:
        """Apply noise reduction (deepFilter) to the session's audio recording."""
        session = self._require_session(session_id)
        if session["audio_file_path"] is None:
            raise SessionCommandError(
                code="REFINE_AUDIO_NO_SOURCE",
                message="No original audio found for refinement.",
                guidance="Please import or capture audio for this session first.",
                exit_code=1,
            )

        source_rel_path = session.get("refined_audio_file_path") or session["audio_file_path"]
        source_path = self._resolve_audio_input_path(source_rel_path)

        if self.local_runtime_manager is not None:
            refined_relative = self.store.build_refined_audio_path(
                session_id,
                course=session.get("course"),
            )
            refined_abs = (self.store.metadata_file.parent.parent / refined_relative).resolve()
            try:
                def runtime_progress(stage, completed, total, message) -> None:
                    report_progress(
                        progress_callback,
                        job_id=job_id,
                        session_id=session_id,
                        stage=stage,
                        completed=int(completed) if isinstance(completed, int) else None,
                        total=int(total) if isinstance(total, int) else None,
                        message=message,
                    )
                self.local_runtime_manager.run_feature(
                    "deepfilter",
                    {
                        "action": "deepfilter",
                        "audio_path": source_path,
                        "output_path": str(refined_abs),
                    },
                    progress=runtime_progress,
                    cancellation_token=cancellation_token,
                    timeout=None,
                )
            except LocalRuntimeMissingError as exc:
                raise SessionCommandError(
                    code="LOCAL_DEEPFILTER_NOT_INSTALLED",
                    message="DeepFilterNet runtime is not installed.",
                    guidance="Open Settings > Local AI and install DeepFilterNet, then retry.",
                    exit_code=2,
                ) from exc
            session["refined_audio_file_path"] = refined_relative
            saved = self._persist_or_raise(session)
            return CommandResult(
                command="audio refine-noise",
                payload=self._build_progress_payload(saved),
                message=f"Successfully reduced noise for session '{session_id}'.",
            )

        try:
            from lecture_auto.audio_amplifier import deepfilter_audio_input, AudioFilterError
            with deepfilter_audio_input(audio_path=source_path) as output_tmp_path:
                refined_relative = self.store.build_refined_audio_path(
                    session_id,
                    course=session.get("course"),
                )
                refined_abs = (self.store.metadata_file.parent.parent / refined_relative).resolve()
                refined_abs.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(output_tmp_path, refined_abs)

                session["refined_audio_file_path"] = refined_relative
                saved = self._persist_or_raise(session)

                return CommandResult(
                    command="audio refine-noise",
                    payload=self._build_progress_payload(saved),
                    message=f"Successfully reduced noise for session '{session_id}'.",
                )
        except AudioFilterError as exc:
            raise SessionCommandError(
                code="REFINE_NOISE_FAILED",
                message="Audio noise reduction process failed.",
                guidance=str(exc),
                exit_code=1,
            ) from exc

    def import_audio(
        self,
        session_id: str,
        source_audio_path: str,
        *,
        allow_failed_retry: bool = False,
    ) -> CommandResult:
        session = self._require_session(session_id)
        normalized_source_path = self._normalize_source_path(source_audio_path)
        extension = self._require_supported_import_extension(normalized_source_path)
        self._reject_duplicate_import(
            session,
            normalized_source_path,
            allow_failed_retry=allow_failed_retry,
        )

        session["import_source_audio_path"] = normalized_source_path
        session["job_attempts"] = int(session.get("job_attempts", 0)) + 1
        session["job_error_code"] = None

        self._transition_job_or_raise(session, "queued")
        session["job_timestamps"]["queued_at"] = self._utc_now()
        self._transition_job_or_raise(session, "running")
        session["job_timestamps"]["started_at"] = self._utc_now()

        persisted_path = session.get("audio_file_path")
        if not persisted_path:
            persisted_path = self.store.next_imported_audio_path(
                session_id,
                extension,
                course=session.get("course"),
            )

        try:
            self._copy_import_audio(
                source_path=normalized_source_path,
                destination_relative_path=persisted_path,
            )
        except OSError as exc:
            self._transition_job_or_raise(session, "failed")
            session["job_error_code"] = "IMPORT_COPY_ERROR"
            session["job_timestamps"]["ended_at"] = self._utc_now()
            saved = self._persist_or_raise(session)
            return CommandResult(
                command="audio import",
                payload=self._build_progress_payload(saved),
                message=(
                    f"Audio import failed for session '{session_id}'. "
                    "Fix file access issues and run retry."
                ),
            )

        session["audio_file_path"] = persisted_path
        self._transition_job_or_raise(session, "succeeded")
        session["job_timestamps"]["ended_at"] = self._utc_now()
        saved = self._persist_or_raise(session)
        return CommandResult(
            command="audio import",
            payload=self._build_progress_payload(saved),
            message=f"Audio import completed for session '{session_id}'.",
        )

    def import_material(self, session_id: str, material_path: str) -> CommandResult:
        session = self._require_session(session_id)
        normalized_source_path = self._normalize_source_path(material_path)
        
        path_obj = Path(normalized_source_path)
        
        # Check if format is supported
        if not is_supported_format(normalized_source_path):
            ext = path_obj.suffix.lower()
            raise SessionCommandError(
                code="IMPORT_MATERIAL_INVALID_FORMAT",
                message=f"Unsupported file format: {ext or 'no extension'}",
                guidance="Supported formats: PDF, PPT, PPTX",
                exit_code=1,
            )

        persisted_path = self.store.build_material_path(
            session_id,
            extension="pdf",
            course=session.get("course"),
        )
        
        metadata_root = self.store.metadata_file.parent.parent
        final_pdf_path = metadata_root / persisted_path
        
        # Convert to PDF if needed
        converted = False
        temp_pdf_path = None
        try:
            if path_obj.suffix.lower() != ".pdf":
                # Need conversion
                import tempfile
                temp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                temp_pdf_path = temp_pdf.name
                temp_pdf.close()
                
                conversion_result = convert_to_pdf(normalized_source_path, temp_pdf_path)
                if conversion_result == "unsupported":
                    raise SessionCommandError(
                        code="IMPORT_MATERIAL_CONVERSION_UNSUPPORTED",
                        message=f"Cannot convert {path_obj.suffix} to PDF",
                        guidance="Only PDF, PPT, and PPTX formats are supported.",
                        exit_code=1,
                    )
                converted = True
                source_for_merge = temp_pdf_path
            else:
                source_for_merge = normalized_source_path
            
            # Merge with existing material if exists
            existing_material = session.get("material_file_path")
            merged = False
            
            if existing_material:
                existing_path = metadata_root / existing_material
                if existing_path.exists() and existing_path.suffix.lower() == ".pdf":
                    self._merge_pdfs(
                        str(existing_path), 
                        source_for_merge, 
                        str(final_pdf_path)
                    )
                    merged = True
                else:
                    self._copy_import_audio(
                        source_path=source_for_merge,
                        destination_relative_path=persisted_path,
                    )
            else:
                self._copy_import_audio(
                    source_path=source_for_merge,
                    destination_relative_path=persisted_path,
                )
                
        except DocumentConversionError as exc:
            raise SessionCommandError(
                code="IMPORT_MATERIAL_CONVERSION_ERROR",
                message=str(exc),
                guidance="Check if required libraries are installed: pip install python-pptx reportlab pillow",
                exit_code=1,
            )
        except OSError as exc:
            raise SessionCommandError(
                code="IMPORT_MATERIAL_COPY_ERROR",
                message=f"Failed to copy or merge material file: {str(exc)}",
                guidance="Check file permissions and try again.",
                exit_code=1,
            )
        except RuntimeError as exc:
            raise SessionCommandError(
                code="IMPORT_MATERIAL_DEPENDENCY_ERROR",
                message=str(exc),
                guidance="Install missing dependencies to merge PDFs.",
                exit_code=1,
            )
        finally:
            # Clean up temporary PDF
            if temp_pdf_path and Path(temp_pdf_path).exists():
                try:
                    Path(temp_pdf_path).unlink()
                except OSError:
                    pass

        session["material_file_path"] = persisted_path
        session.setdefault("timestamps", {})["material_imported_at"] = self._utc_now()
        
        saved = self._persist_or_raise(session)
        
        # Build descriptive message
        msg_parts = []
        if converted:
            msg_parts.append(f"converted from {path_obj.suffix.upper()}")
        if merged:
            msg_parts.append("merged with existing material")
        else:
            msg_parts.append("imported successfully")
        
        msg_action = " and ".join(msg_parts) if msg_parts else "imported successfully"
        
        return CommandResult(
            command="material import",
            payload=saved,
            message=f"Material {msg_action} for session '{session_id}'.",
        )

    def _concat_audio(self, base_path: str, part_path: str) -> None:
        import subprocess
        import os
        from tempfile import NamedTemporaryFile
        from pathlib import Path
        import uuid

        base_p = Path(base_path)
        part_p = Path(part_path)
        
        if not base_p.exists() or not part_p.exists():
            return

        merged_p = base_p.with_name(f"{base_p.stem}-merged-{uuid.uuid4().hex[:6]}{base_p.suffix}")

        try:
            with NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write(f"file '{base_p.absolute().as_posix()}'\n")
                f.write(f"file '{part_p.absolute().as_posix()}'\n")
                list_file_path = f.name
                
            cmd = [
                "ffmpeg",
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_file_path,
                "-c", "copy",
                str(merged_p)
            ]
            
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            os.replace(str(merged_p), str(base_p))
            part_p.unlink(missing_ok=True)
            
        except Exception as exc:
            if merged_p.exists():
                merged_p.unlink(missing_ok=True)
            raise SessionCommandError(
                code="CONCAT_FAILED",
                message=f"Failed to merge new recording part: {exc}",
                guidance="Check ffmpeg and file permissions.",
                exit_code=1,
            ) from exc
        finally:
            if 'list_file_path' in locals() and os.path.exists(list_file_path):
                os.remove(list_file_path)

    def retry_import_audio(self, session_id: str) -> CommandResult:
        session = self._require_session(session_id)
        current_status = session.get("job_status")
        attempts = int(session.get("job_attempts", 0))

        if current_status != "failed":
            raise SessionCommandError(
                code="IMPORT_RETRY_NOT_ALLOWED",
                message="Retry is only allowed for failed import jobs.",
                guidance="Run import first or inspect the last failed job.",
                exit_code=1,
            )

        if attempts >= MAX_IMPORT_RETRIES:
            raise SessionCommandError(
                code="IMPORT_RETRY_LIMIT_EXCEEDED",
                message="Import retry limit has been reached.",
                guidance="Retry limit is 3 attempts. Re-import with a new command if needed.",
                exit_code=1,
            )

        source_audio_path = session.get("import_source_audio_path")
        if not isinstance(source_audio_path, str) or not source_audio_path.strip():
            raise SessionCommandError(
                code="IMPORT_SOURCE_NOT_FOUND",
                message="Cannot retry import because source audio path is missing.",
                guidance="Run the audio import command again with a valid source path.",
                exit_code=1,
            )

        # Retry must preserve the same target path to avoid duplicate artifacts.
        retried = self.import_audio(
            session_id=session_id,
            source_audio_path=source_audio_path,
            allow_failed_retry=True,
        )
        return CommandResult(
            command="audio import retry",
            payload=retried.payload,
            message=retried.message,
        )

    def cancel_import_audio(self, session_id: str) -> CommandResult:
        session = self._require_session(session_id)
        if session.get("job_status") not in {"queued", "running"}:
            raise SessionCommandError(
                code="IMPORT_CANCEL_NOT_ALLOWED",
                message="Import cancellation is only allowed for queued/running jobs.",
                guidance="Start a new import job first or check current status.",
                exit_code=1,
            )

        self._transition_job_or_raise(session, "canceled")
        session["job_timestamps"]["ended_at"] = self._utc_now()
        saved = self._persist_or_raise(session)
        return CommandResult(
            command="audio import cancel",
            payload=self._build_progress_payload(saved),
            message=f"Audio import canceled for session '{session_id}'.",
        )

    def transcribe_session(
        self,
        session_id: str,
        *,
        source_audio_path: str | None = None,
        progress_callback: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
        job_id: str = "transcription",
    ) -> CommandResult:
        token = cancellation_token or CancellationToken()
        token.raise_if_cancelled()
        session = self._require_session(session_id)
        if source_audio_path is not None:
            raise SessionCommandError(
                code="TRANSCRIPTION_SESSION_AUDIO_ONLY",
                message="Transcription accepts only session-linked audio.",
                guidance="Attach/import audio to the session first, then retry transcription.",
                exit_code=1,
            )

        audio_relative_path = session.get("refined_audio_file_path") or session.get("audio_file_path")
        if not isinstance(audio_relative_path, str) or not audio_relative_path.strip():
            raise SessionCommandError(
                code="TRANSCRIPTION_AUDIO_NOT_FOUND",
                message="No session audio is attached for transcription.",
                guidance="Run capture or audio import for this session first.",
                exit_code=1,
            )

        stages = [
            "preflight_checks",
            "mode_provider_initialization",
            "transcription_in_progress",
            "file_write_complete",
        ]
        metadata_root = self.store.metadata_file.parent.parent
        mode = self.stt_config.mode
        attempt = 0
        retry_limit = MAX_STT_API_RETRIES if mode == "api" else 0

        report_progress(progress_callback, job_id=job_id, session_id=session_id, stage=stages[0], completed=0, total=4, message="Checking transcription settings.")
        self._run_transcription_preflight()

        token.raise_if_cancelled()
        report_progress(progress_callback, job_id=job_id, session_id=session_id, stage=stages[1], completed=1, total=4, message="Loading STT provider.")
        adapter = self._build_stt_adapter(
            progress_callback=progress_callback,
            cancellation_token=token,
            job_id=job_id,
            session_id=session_id,
        )
        adapter_audio_path = audio_relative_path
        if mode == "api" and self.stt_config.api_provider == "deepgram":
            adapter_audio_path = self._resolve_audio_input_path(audio_relative_path)

        transcript_text: str | None = None
        transcript_result = None
        effective_audio_path = adapter_audio_path

        while True:
            try:
                attempt += 1
                token.raise_if_cancelled()
                report_progress(progress_callback, job_id=job_id, session_id=session_id, stage=stages[2], completed=2, total=4, message=f"Transcribing audio (attempt {attempt}).")
                transcript_result = adapter.transcribe(audio_path=effective_audio_path)
                transcript_text = transcript_result.transcript_text
                break
            except STTTransientNetworkError as exc:
                if mode == "api" and attempt <= retry_limit:
                    continue
                self._mark_transcription_failure(session, "network/transient")
                raise self.map_transcription_failure(
                    "network/transient", detail=str(exc)
                ) from exc
            except STTProviderAuthError as exc:
                self._mark_transcription_failure(session, "provider_auth")
                raise self.map_transcription_failure(
                    "provider_auth", detail=str(exc)
                ) from exc
            except STTAudioDecodeError as exc:
                self._mark_transcription_failure(session, "audio_decode")
                raise self.map_transcription_failure(
                    "audio_decode", detail=str(exc)
                ) from exc
            except STTConfigError as exc:
                self._mark_transcription_failure(session, "configuration")
                raise self.map_transcription_failure(
                    "configuration", detail=str(exc)
                ) from exc
            except STTRuntimeError as exc:
                self._mark_transcription_failure(session, "runtime")
                raise self.map_transcription_failure("runtime", detail=str(exc)) from exc

        output_text = transcript_text or ""
        if transcript_result and transcript_result.segments:
            if transcript_result.mode == "local":
                output_text = transcript_result.to_plain_text()
            else:
                output_text = transcript_result.to_diarized_markdown()

        token.raise_if_cancelled()
        transcript_relative_path = self.store.build_raw_transcript_path(
            session_id,
            course=session.get("course"),
        )
        try:
            self._write_transcript_file(
                transcript_relative_path=transcript_relative_path,
                transcript_text=output_text,
            )
        except OSError as exc:
            self._mark_transcription_failure(session, "configuration")
            raise SessionCommandError(
                code="TRANSCRIPTION_WRITE_ERROR",
                message="Failed to write raw transcript to local storage.",
                guidance="Check filesystem permissions and available disk space, then retry.",
                exit_code=8,
            ) from exc

        session["transcript_file_path"] = transcript_relative_path
        session["transcription_status"] = "succeeded"
        session["transcription_error_category"] = None
        session["transcription_retry_count"] = max(0, attempt - 1)
        session.setdefault("timestamps", {})["transcription_completed_at"] = self._utc_now()

        saved = self._persist_or_raise(session)
        payload = dict(saved)
        payload["transcription_progress"] = {
            "stages": stages,
            "current_stage": "file_write_complete",
            "final_status": "succeeded",
            "attempt": attempt,
            "retry_limit": retry_limit,
            "mode": mode,
            "use_dynaudnorm": self.stt_config.use_dynaudnorm,
            "dynaudnorm_f": self.stt_config.dynaudnorm_f,
            "dynaudnorm_g": self.stt_config.dynaudnorm_g,
            "audio_amplification_applied": self.stt_config.use_dynaudnorm,
            "transcript_file_path": transcript_relative_path,
        }

        report_progress(progress_callback, job_id=job_id, session_id=session_id, stage=stages[3], completed=4, total=4, message="Transcript saved.")
        return CommandResult(
            command="transcription run",
            payload=payload,
            message=f"Transcription completed for session '{session_id}'.",
        )

    def map_capture_failure(self, failure_kind: str) -> SessionCommandError:
        mapping = {
            "dependency": SessionCommandError(
                code="CAPTURE_DEPENDENCY_ERROR",
                message="Audio capture dependencies are unavailable.",
                guidance="Install FFmpeg/PyAudio and retry.",
                exit_code=2,
            ),
            "device": SessionCommandError(
                code="CAPTURE_DEVICE_ERROR",
                message="No accessible audio input device was detected.",
                guidance="Check audio permissions and selected device.",
                exit_code=3,
            ),
            "runtime": SessionCommandError(
                code="CAPTURE_RUNTIME_ERROR",
                message="Capture failed during runtime.",
                guidance="Inspect logs and restart capture.",
                exit_code=4,
            ),
            "permission": SessionCommandError(
                code="CAPTURE_PERMISSION_DENIED",
                message="Capture permission was denied by the operating system.",
                guidance="Grant microphone/system-audio permission and retry.",
                exit_code=5,
            ),
            "interrupted": SessionCommandError(
                code="CAPTURE_INTERRUPTED",
                message="Capture was interrupted before completion.",
                guidance="Run 'capture stop' then restart capture when ready.",
                exit_code=6,
            ),
        }
        if failure_kind not in mapping:
            return SessionCommandError(
                code="CAPTURE_UNKNOWN_ERROR",
                message="Capture failed due to an unknown error.",
                guidance="Retry the command and verify the local environment.",
                exit_code=7,
            )
        return mapping[failure_kind]

    def map_transcription_failure(
        self,
        failure_kind: str,
        *,
        detail: str | None = None,
    ) -> SessionCommandError:
        mapping = {
            "configuration": SessionCommandError(
                code="TRANSCRIPTION_CONFIG_ERROR",
                message="Transcription configuration is invalid.",
                guidance="Check STT mode/provider/model settings and retry.",
                exit_code=2,
            ),
            "provider_auth": SessionCommandError(
                code="TRANSCRIPTION_PROVIDER_AUTH_ERROR",
                message="STT provider authentication failed.",
                guidance="Verify API key/provider settings and retry.",
                exit_code=3,
            ),
            "network/transient": SessionCommandError(
                code="TRANSCRIPTION_NETWORK_TRANSIENT_ERROR",
                message="Transient network/provider failure during transcription.",
                guidance="Retry later or verify provider/network availability.",
                exit_code=4,
            ),
            "audio_decode": SessionCommandError(
                code="TRANSCRIPTION_AUDIO_DECODE_ERROR",
                message="Audio format or decoding failed during transcription.",
                guidance="Verify session audio format/quality and retry.",
                exit_code=5,
            ),
            "runtime": SessionCommandError(
                code="TRANSCRIPTION_RUNTIME_ERROR",
                message="Transcription failed due to an unknown runtime error.",
                guidance="Inspect logs and retry transcription.",
                exit_code=6,
            ),
        }
        result = mapping.get(
            failure_kind,
            SessionCommandError(
                code="TRANSCRIPTION_RUNTIME_ERROR",
                message="Transcription failed due to an unknown runtime error.",
                guidance="Inspect logs and retry transcription.",
                exit_code=6,
            ),
        )
        if detail and detail.strip():
            return SessionCommandError(
                code=result.code,
                message=result.message,
                guidance=f"{result.guidance} Detail: {detail.strip()}",
                exit_code=result.exit_code,
            )
        return result

    def _persist_or_raise(self, session: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.store.upsert(session)
        except OSError as exc:
            raise SessionCommandError(
                code="METADATA_WRITE_ERROR",
                message="Failed to persist session metadata to local storage.",
                guidance="Check filesystem permissions and available disk space.",
                exit_code=8,
            ) from exc

    def _require_session(self, session_id: str) -> dict[str, Any]:
        found = self.store.get_by_session_id(session_id)
        if not found:
            raise SessionCommandError(
                code="SESSION_NOT_FOUND",
                message=f"Session '{session_id}' was not found.",
                guidance="Run 'session history' to view available sessions.",
                exit_code=1,
            )
        return found

    def _transition_or_raise(self, session: dict[str, Any], target_state: str) -> None:
        current = session["status"]
        if current not in VALID_STATES:
            raise SessionCommandError(
                code="INVALID_SESSION_STATE",
                message=f"Session state '{current}' is invalid.",
                guidance="Recreate the session metadata before retrying.",
                exit_code=1,
            )

        allowed = ALLOWED_TRANSITIONS[current]
        if target_state not in allowed:
            raise SessionCommandError(
                code="INVALID_TRANSITION",
                message=(
                    f"Cannot move session '{session['session_id']}' "
                    f"from '{current}' to '{target_state}'."
                ),
                guidance="Use create -> start -> stop command order.",
                exit_code=1,
            )
        session["status"] = target_state

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _normalize_source_path(self, source_audio_path: str) -> str:
        normalized = source_audio_path.strip()
        if not normalized:
            raise SessionCommandError(
                code="IMPORT_SOURCE_REQUIRED",
                message="Source audio path is required.",
                guidance="Provide a local .wav or .mp3 file path with the import command.",
                exit_code=1,
            )
        return str(Path(normalized).as_posix())

    def _require_supported_import_extension(self, source_audio_path: str) -> str:
        suffix = Path(source_audio_path).suffix.lower().lstrip(".")
        if suffix not in SUPPORTED_IMPORT_EXTENSIONS:
            raise SessionCommandError(
                code="UNSUPPORTED_AUDIO_FORMAT",
                message="Unsupported audio format for import.",
                guidance="Use a .wav or .mp3 file and retry.",
                exit_code=1,
            )
        return suffix

    def _reject_duplicate_import(
        self,
        session: dict[str, Any],
        source_audio_path: str,
        *,
        allow_failed_retry: bool,
    ) -> None:
        if (
            allow_failed_retry
            and session.get("job_status") == "failed"
            and session.get("import_source_audio_path") == source_audio_path
        ):
            return

        if session.get("import_source_audio_path") == source_audio_path:
            raise SessionCommandError(
                code="DUPLICATE_AUDIO_IMPORT",
                message="Duplicate audio import is not allowed for this session.",
                guidance="Use a different file or create a new session.",
                exit_code=1,
            )

    def _transition_job_or_raise(self, session: dict[str, Any], target_state: str) -> None:
        current = session.get("job_status")
        if current not in JOB_ALLOWED_TRANSITIONS:
            raise SessionCommandError(
                code="INVALID_JOB_STATE",
                message=f"Import job state '{current}' is invalid.",
                guidance="Re-run the import command to initialize a new job.",
                exit_code=1,
            )

        if target_state not in JOB_VALID_STATES:
            raise SessionCommandError(
                code="INVALID_JOB_TRANSITION",
                message=f"Unknown import job state '{target_state}'.",
                guidance="Use one of queued/running/succeeded/failed/canceled.",
                exit_code=1,
            )

        allowed = JOB_ALLOWED_TRANSITIONS[current]
        if target_state not in allowed:
            raise SessionCommandError(
                code="INVALID_JOB_TRANSITION",
                message=f"Cannot move import job from '{current}' to '{target_state}'.",
                guidance="Use valid job flow: queued -> running -> succeeded/failed/canceled.",
                exit_code=1,
            )
        session["job_status"] = target_state

    def transcript_search(self, title_query: str) -> CommandResult:
        sessions = self.store.load_all()
        matches = []
        lowered_query = title_query.lower()
        for session in sessions:
            title = session.get("title") or ""
            if lowered_query in title.lower():
                matches.append(session)
        
        matches = sorted(matches, key=lambda row: row["date"], reverse=True)
        return CommandResult(
            command="transcript search",
            payload={"matches": matches, "query": title_query},
            message=f"Found {len(matches)} session(s) matching '{title_query}'."
        )

    def transcript_open(self, session_reference: str) -> CommandResult:
        sessions = self.store.load_all()
        session = None
        for row in sessions:
            title = row.get("title")
            if row["session_id"] == session_reference or \
               (isinstance(title, str) and title.lower() == session_reference.lower()):
                session = row
                break
        
        if not session:
            raise SessionCommandError(
                code="SESSION_NOT_FOUND",
                message=f"Session matching '{session_reference}' was not found.",
                guidance="Run 'lecture search <title>' to find valid sessions.",
                exit_code=1,
            )

        session_id = session["session_id"]
        
        raw_transcript_path_str = session.get("transcript_file_path")
        if not raw_transcript_path_str:
            raise SessionCommandError(
                code="TRANSCRIPT_NOT_FOUND",
                message=f"No transcript found for session '{session_id}'.",
                guidance="Run transcription for this session first.",
                exit_code=1,
            )
        
        raw_transcript_path, edited_transcript_path = self._resolve_transcript_paths(session)

        active_path = edited_transcript_path if edited_transcript_path.exists() else raw_transcript_path
        
        if not active_path.exists():
            raise SessionCommandError(
                code="TRANSCRIPT_FILE_MISSING",
                message=f"Transcript file missing at '{active_path}'.",
                guidance="Ensure the file hasn't been manually deleted.",
                exit_code=1,
            )

        pre_edit_mtime = active_path.stat().st_mtime
        
        typer.launch(str(active_path.resolve()), wait=True)

        post_edit_mtime = active_path.stat().st_mtime
        
        if post_edit_mtime > pre_edit_mtime:
            if active_path == raw_transcript_path:
                import shutil
                shutil.copyfile(raw_transcript_path, edited_transcript_path)
                return CommandResult(
                    command="transcript open",
                    payload={"session_id": session_id, "state": "edited"},
                    message=f"Transcript for '{session_id}' edited and saved as new version."
                )
            else:
                return CommandResult(
                    command="transcript open",
                    payload={"session_id": session_id, "state": "edited"},
                    message=f"Edited transcript for '{session_id}' updated."
                )
        
        return CommandResult(
            command="transcript open",
            payload={"session_id": session_id, "state": "unmodified"},
            message=f"Transcript for '{session_id}' reviewed (no changes)."
        )

    def transcript_refine(
        self,
        session_reference: str,
        *,
        raw: bool = False,
        progress_callback: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
        job_id: str = "transcript-refine",
    ) -> CommandResult:
        token = cancellation_token or CancellationToken()
        token.raise_if_cancelled()
        if not self.llm_adapter:
            raise SessionCommandError(
                code="LLM_NOT_CONFIGURED",
                message="No LLM adapter configured for refinement.",
                guidance="Configure an LLM provider (e.g., Google API) to use the refine command.",
                exit_code=1,
            )

        sessions = self.store.load_all()
        session = next(
            (r for r in sessions if r["session_id"] == session_reference or 
             (isinstance(r.get("title"), str) and r["title"].lower() == session_reference.lower())),
            None
        )

        if not session:
            raise SessionCommandError(
                code="SESSION_NOT_FOUND",
                message=f"Session matching '{session_reference}' was not found.",
                guidance="Run 'lecture search <title>' to find valid sessions.",
                exit_code=1,
            )

        session_id = session["session_id"]
        raw_transcript_path_str = session.get("transcript_file_path")
        if not raw_transcript_path_str:
            raise SessionCommandError(
                code="TRANSCRIPT_NOT_FOUND",
                message=f"No transcript found for session '{session_id}'.",
                guidance="Run transcription for this session first.",
                exit_code=1,
            )

        raw_transcript_path, edited_transcript_path = self._resolve_transcript_paths(session)

        target_path = raw_transcript_path
        if not raw and edited_transcript_path.exists():
            if not raw_transcript_path.exists() or edited_transcript_path.stat().st_mtime > raw_transcript_path.stat().st_mtime:
                target_path = edited_transcript_path

        if not target_path.exists():
            raise SessionCommandError(
                code="TRANSCRIPT_FILE_MISSING",
                message=f"Transcript file missing at '{target_path}'.",
                guidance="Ensure the file hasn't been manually deleted.",
                exit_code=1,
            )

        raw_text = target_path.read_text(encoding="utf-8")
        if not raw_text.strip():
            raise SessionCommandError(
                code="TRANSCRIPT_EMPTY",
                message=f"The selected transcript file is empty.",
                guidance="Cannot refine an empty transcript.",
                exit_code=1,
            )

        context_topic = session.get("title") or session.get("course")
        
        report_progress(progress_callback, job_id=job_id, session_id=session_id, stage="llm_refine", completed=1, total=2, message="Refining transcript.")
        try:
            refined_text = self.llm_adapter.refine_transcript(raw_text, context_topic=context_topic)
        except LLMConfigError as exc:
            raise SessionCommandError(code="LLM_CONFIG_FAILED", message=str(exc), guidance="Check LLM configuration.", exit_code=1)
        except LLMProviderAuthError as exc:
            raise SessionCommandError(code="LLM_AUTH_FAILED", message=str(exc), guidance="Verify your API key.", exit_code=1)
        except LLMTransientNetworkError as exc:
            raise SessionCommandError(code="LLM_NETWORK_ERROR", message=str(exc), guidance="Try again later.", exit_code=1)
        except Exception as exc:
            raise SessionCommandError(code="LLM_UNKNOWN_ERROR", message=f"Unexpected refinement failure: {exc}", guidance="Check debug logs.", exit_code=1)

        token.raise_if_cancelled()
        self._write_transcript_file(
            transcript_relative_path=self.store.build_edited_transcript_path(
                session_id,
                course=session.get("course"),
            ),
            transcript_text=refined_text
        )

        # Output payload logic for formatting
        target_used = "raw" if target_path == raw_transcript_path else "edited"
        report_progress(progress_callback, job_id=job_id, session_id=session_id, stage="complete", completed=2, total=2, message="Refined transcript saved.")
        return CommandResult(
            command="transcript refine",
            payload={"session_id": session_id, "target_used": target_used},
            message=f"Transcript successfully refined from {target_used} source."
        )

    def summarize_session(
        self,
        session_reference: str,
        *,
        template_name: str | None = None,
        preview: bool = False,
        progress_callback: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
        job_id: str = "summarize",
    ) -> CommandResult:
        token = cancellation_token or CancellationToken()
        token.raise_if_cancelled()
        if not self.llm_adapter:
            raise SessionCommandError(
                code="LLM_NOT_CONFIGURED",
                message="No LLM adapter configured for summarize.",
                guidance="Configure an LLM provider (e.g., Google API) to use summarize.",
                exit_code=1,
            )

        session = self._resolve_session_for_reference(session_reference)
        session_id = session["session_id"]
        transcript_text, transcript_source = self._load_summary_transcript(session)
        resolved_template_name, template_text = self._resolve_note_template(template_name)

        context_topic = session.get("title") or session.get("course")
        material_path = None
        if "material_file_path" in session and session["material_file_path"]:
            material_root = self.store.metadata_file.parent.parent
            material_path = str((material_root / session["material_file_path"]).resolve())

        report_progress(progress_callback, job_id=job_id, session_id=session_id, stage="llm_summarize", completed=1, total=2, message="Generating structured notes.")
        try:
            notes = self.llm_adapter.generate_notes(
                transcript=transcript_text,
                template=template_text,
                context_topic=context_topic,
                material_path=material_path,
            )
        except LLMConfigError as exc:
            raise SessionCommandError(
                code="LLM_CONFIG_FAILED",
                message=str(exc),
                guidance="Check LLM configuration.",
                exit_code=1,
            ) from exc
        except LLMProviderAuthError as exc:
            raise SessionCommandError(
                code="LLM_AUTH_FAILED",
                message=str(exc),
                guidance="Verify your API key.",
                exit_code=1,
            ) from exc
        except LLMTransientNetworkError as exc:
            raise SessionCommandError(
                code="LLM_NETWORK_ERROR",
                message=str(exc),
                guidance="Try again later.",
                exit_code=1,
            ) from exc
        except Exception as exc:
            raise SessionCommandError(
                code="LLM_UNKNOWN_ERROR",
                message=f"Unexpected summarize failure: {exc}",
                guidance="Check debug logs.",
                exit_code=1,
            ) from exc

        note_relative_path = self.store.build_note_path(
            session_id,
            course=session.get("course"),
        )
        payload = {
            "session_id": session_id,
            "template": resolved_template_name,
            "preview": preview,
            "source_transcript": transcript_source,
            "note_file_path": note_relative_path,
            "material_file_path": session.get("material_file_path"),
        }

        token.raise_if_cancelled()
        if preview:
            payload["notes"] = notes
            report_progress(progress_callback, job_id=job_id, session_id=session_id, stage="complete", completed=2, total=2, message="Note preview ready.")
            return CommandResult(command="summarize", payload=payload, message=notes)

        self._write_note_file(note_relative_path=note_relative_path, note_text=notes)
        report_progress(progress_callback, job_id=job_id, session_id=session_id, stage="complete", completed=2, total=2, message="Notes saved.")
        return CommandResult(
            command="summarize",
            payload=payload,
            message=(
                f"Summary notes saved for session '{session_id}' at '{note_relative_path}'."
            ),
        )

    def _merge_pdfs(self, existing_pdf_path: str, new_pdf_path: str, output_path: str) -> None:
        try:
            from pypdf import PdfWriter  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pypdf is required to merge PDF files. Run: pip install pypdf") from exc
            
        merger = PdfWriter()
        try:
            merger.append(existing_pdf_path)
            merger.append(new_pdf_path)
            
            # We write to a temporary file first in case output_path is same as existing_pdf_path
            temp_out = output_path + ".tmp"
            merger.write(temp_out)
        finally:
            merger.close()
            
        import shutil
        shutil.move(temp_out, output_path)

    def _copy_import_audio(self, *, source_path: str, destination_relative_path: str) -> None:
        metadata_root = self.store.metadata_file.parent.parent
        destination = metadata_root / destination_relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, destination)

    def _build_progress_payload(self, session: dict[str, Any]) -> dict[str, Any]:
        payload = dict(session)
        job_timestamps = payload.get("job_timestamps") or {}
        payload["progress"] = {
            "started_at": job_timestamps.get("started_at"),
            "ended_at": job_timestamps.get("ended_at"),
            "current_stage": payload.get("job_status"),
            "final_status": payload.get("job_status"),
            "attempt": payload.get("job_attempts", 0),
            "retry_limit": MAX_IMPORT_RETRIES,
        }
        return payload

    def _run_transcription_preflight(self) -> None:
        try:
            self.stt_config.validate()
        except ValueError as exc:
            raise SessionCommandError(
                code="TRANSCRIPTION_CONFIG_ERROR",
                message="Transcription preflight checks failed.",
                guidance=str(exc),
                exit_code=2,
            ) from exc

    def _build_stt_adapter(
        self,
        *,
        progress_callback: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
        job_id: str = "transcription",
        session_id: str | None = None,
    ) -> STTRuntimeAdapter:
        if self.stt_config.mode == "local":
            if self._local_stt_adapter is not None:
                return self._local_stt_adapter
            from lecture_auto.local_worker_adapter import WorkerWhisperSTTRuntimeAdapter
            def runtime_progress(stage, completed, total, message) -> None:
                report_progress(
                    progress_callback,
                    job_id=job_id,
                    session_id=session_id,
                    stage=stage,
                    completed=int(completed) if isinstance(completed, int) else None,
                    total=int(total) if isinstance(total, int) else None,
                    message=message,
                )
            return WorkerWhisperSTTRuntimeAdapter(
                config=self.stt_config,
                runtime_manager=self.local_runtime_manager or LocalRuntimeManager(),
                progress=runtime_progress,
                cancellation_token=cancellation_token,
            )

        if self._api_stt_adapter is not None:
            return self._api_stt_adapter

        if self.stt_config.api_provider == "deepgram":
            from lecture_auto.deepgram_adapter import DeepgramSTTRuntimeAdapter
            return DeepgramSTTRuntimeAdapter(config=self.stt_config)

        return APISTTRuntimeAdapter(
            provider=self.stt_config.api_provider or "openai-compatible",
            api_key=self.stt_config.api_key or "",
        )

    def _mark_transcription_failure(self, session: dict[str, Any], category: str) -> None:
        session["transcription_status"] = "failed"
        session["transcription_error_category"] = category
        retries = int(session.get("transcription_retry_count", 0))
        session["transcription_retry_count"] = retries + 1
        session.setdefault("timestamps", {})["transcription_failed_at"] = self._utc_now()
        self._persist_or_raise(session)

    def _write_transcript_file(self, *, transcript_relative_path: str, transcript_text: str) -> None:
        metadata_root = self.store.metadata_file.parent.parent
        target = metadata_root / transcript_relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(transcript_text, encoding="utf-8")

    def _write_note_file(self, *, note_relative_path: str, note_text: str) -> None:
        metadata_root = self.store.metadata_file.parent.parent
        target = metadata_root / note_relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(note_text, encoding="utf-8")

    def _resolve_audio_input_path(self, audio_path: str) -> str:
        candidate = Path(audio_path)
        if candidate.is_absolute():
            return str(candidate)

        metadata_root = self.store.metadata_file.parent.parent
        metadata_candidate = (metadata_root / candidate).resolve()
        if metadata_candidate.exists():
            return str(metadata_candidate)

        return str(candidate.resolve())

    def _resolve_session_for_reference(self, session_reference: str) -> dict[str, Any]:
        sessions = self.store.list_recent_first()
        if not sessions:
            raise SessionCommandError(
                code="SESSION_NOT_FOUND",
                message="No sessions are available.",
                guidance="Run 'session create' to create your first session.",
                exit_code=1,
            )

        if not session_reference.strip():
            return sessions[0]

        reference = session_reference.strip().lower()
        for row in sessions:
            if row["session_id"] == session_reference:
                return row
            title = row.get("title")
            if isinstance(title, str) and title.lower() == reference:
                return row

        raise SessionCommandError(
            code="SESSION_NOT_FOUND",
            message=f"Session matching '{session_reference}' was not found.",
            guidance="Run 'session history' to find a valid session id.",
            exit_code=1,
        )

    def _load_summary_transcript(self, session: dict[str, Any]) -> tuple[str, str]:
        session_id = session["session_id"]
        raw_path, edited_path = self._resolve_transcript_paths(session)

        target_path = edited_path if edited_path.exists() else raw_path
        source_name = "edited" if target_path == edited_path else "raw"
        if not target_path.exists():
            raise SessionCommandError(
                code="TRANSCRIPT_NOT_FOUND",
                message=f"No transcript found for session '{session_id}'.",
                guidance="Run transcription for this session first.",
                exit_code=1,
            )

        return target_path.read_text(encoding="utf-8"), source_name

    def _resolve_transcript_paths(self, session: dict[str, Any]) -> tuple[Path, Path]:
        session_id = session["session_id"]
        metadata_root = self.store.metadata_file.parent.parent

        preferred_raw_relative = session.get("transcript_file_path") or self.store.build_raw_transcript_path(
            session_id,
            course=session.get("course"),
        )
        preferred_raw_path = metadata_root / preferred_raw_relative
        legacy_raw_path = metadata_root / f"transcripts/{session_id}-raw.md"

        if preferred_raw_path.exists() or not legacy_raw_path.exists():
            raw_path = preferred_raw_path
        else:
            raw_path = legacy_raw_path

        preferred_edited_path = metadata_root / self.store.build_edited_transcript_path(
            session_id,
            course=session.get("course"),
        )
        legacy_edited_path = metadata_root / f"transcripts/{session_id}-edited.md"

        if preferred_edited_path.exists():
            edited_path = preferred_edited_path
        elif legacy_edited_path.exists():
            edited_path = legacy_edited_path
        elif raw_path == legacy_raw_path:
            edited_path = legacy_edited_path
        else:
            edited_path = preferred_edited_path

        return raw_path, edited_path

    def list_note_templates(self) -> list[str]:
        """List the fixed summary note template."""
        return [DEFAULT_NOTE_TEMPLATE_NAME]

    def _resolve_note_template(self, template_name: str | None) -> tuple[str, str]:
        _ = template_name
        preset_dir = Path(__file__).resolve().parent / "templates"
        template_path = preset_dir / f"{DEFAULT_NOTE_TEMPLATE_NAME}.md"
        if template_path.exists() and template_path.is_file():
            return DEFAULT_NOTE_TEMPLATE_NAME, template_path.read_text(encoding="utf-8")

        raise SessionCommandError(
            code="TEMPLATE_NOT_FOUND",
            message=f"Template '{DEFAULT_NOTE_TEMPLATE_NAME}' was not found.",
            guidance=f"Restore the preset template at {template_path}.",
            exit_code=1,
        )

    def _migrate_legacy_artifact_paths(self) -> None:
        sessions = self.store.load_all()
        if not sessions:
            return

        metadata_root = self.store.metadata_file.parent.parent
        changed = False

        for session in sessions:
            session_id = session.get("session_id")
            if not isinstance(session_id, str) or not session_id.strip():
                continue

            course = session.get("course") if isinstance(session.get("course"), str) else None

            changed = self._migrate_single_session_artifacts(
                session=session,
                metadata_root=metadata_root,
                session_id=session_id,
                course=course,
            ) or changed

        if changed:
            self.store._safe_write(sessions)

    def _migrate_single_session_artifacts(
        self,
        *,
        session: dict[str, Any],
        metadata_root: Path,
        session_id: str,
        course: str | None,
    ) -> bool:
        changed = False

        audio_path = session.get("audio_file_path")
        if isinstance(audio_path, str) and audio_path.startswith("recordings/"):
            filename = Path(audio_path).name
            target_audio = f"recordings/{filename}"
            if "-imported" in filename:
                extension = Path(filename).suffix.lstrip(".")
                target_audio = self.store.build_imported_audio_path(
                    session_id,
                    extension,
                    ordinal=self._extract_import_ordinal(filename),
                    course=course,
                )
            elif filename.startswith(f"{session_id}."):
                extension = Path(filename).suffix.lstrip(".")
                target_audio = self.store.build_recording_path(
                    session_id,
                    extension=extension,
                    course=course,
                )

            changed = self._move_and_update_relative_path(
                metadata_root=metadata_root,
                current_relative=audio_path,
                target_relative=target_audio,
            ) or changed
            if target_audio != audio_path:
                session["audio_file_path"] = target_audio
                changed = True

        transcript_path = session.get("transcript_file_path")
        if isinstance(transcript_path, str) and transcript_path.startswith("transcripts/"):
            ext = Path(transcript_path).suffix.lstrip(".") or "md"
            target_transcript = self.store.build_raw_transcript_path(
                session_id,
                extension=ext,
                course=course,
            )
            changed = self._move_and_update_relative_path(
                metadata_root=metadata_root,
                current_relative=transcript_path,
                target_relative=target_transcript,
            ) or changed
            if target_transcript != transcript_path:
                session["transcript_file_path"] = target_transcript
                changed = True

        note_flat = f"notes/{session_id}.md"
        note_target = self.store.build_note_path(session_id, course=course)
        changed = self._move_and_update_relative_path(
            metadata_root=metadata_root,
            current_relative=note_flat,
            target_relative=note_target,
        ) or changed

        edited_flat = f"transcripts/{session_id}-edited.md"
        edited_target = self.store.build_edited_transcript_path(session_id, course=course)
        changed = self._move_and_update_relative_path(
            metadata_root=metadata_root,
            current_relative=edited_flat,
            target_relative=edited_target,
        ) or changed

        return changed

    def _extract_import_ordinal(self, filename: str) -> int:
        stem = Path(filename).stem
        parts = stem.split("-imported-")
        if len(parts) == 2 and parts[1].isdigit():
            return max(1, int(parts[1]))
        return 1

    def _move_and_update_relative_path(
        self,
        *,
        metadata_root: Path,
        current_relative: str,
        target_relative: str,
    ) -> bool:
        if current_relative == target_relative:
            return False

        current_path = metadata_root / current_relative
        target_path = metadata_root / target_relative

        if not current_path.exists():
            return False

        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            return False

        shutil.move(str(current_path), str(target_path))
        return True
