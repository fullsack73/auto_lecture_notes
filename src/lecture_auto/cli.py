from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import typer

from lecture_auto.cli_output import format_command_error, format_command_output
from lecture_auto.llm_adapter import GeminiLLMAdapter, OllamaLLMAdapter
from lecture_auto.llm_config import (
    GEMINI_MODEL_CHOICES,
    normalize_gemini_model_name,
)
from lecture_auto.session_metadata_store import SessionMetadataStore
from lecture_auto.session_service import SessionCommandError, SessionService
from lecture_auto.stt_config import (
    STTConfig,
    SUPPORTED_API_PROVIDERS,
    SUPPORTED_COMPUTE_TYPES,
    SUPPORTED_LOCAL_DEVICES,
)
from lecture_auto.library_service import LibraryService

app = typer.Typer(help="Lecture automation CLI", invoke_without_command=True)
session_app = typer.Typer(help="Session commands")
capture_app = typer.Typer(help="Capture commands")
transcription_app = typer.Typer(help="Transcription commands")
config_app = typer.Typer(help="Configuration commands")
library_app = typer.Typer(help="Library commands")
runtime_app = typer.Typer(help="Managed local AI runtime commands")


def _get_global_config_path() -> Path:
    return Path.home() / ".lecture_auto" / "config.json"


@app.callback()
def app_callback(
    ctx: typer.Context,
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Custom workspace directory (default: ~/.lecture_auto)",
        envvar="LECTURE_AUTO_WORKSPACE",
    ),
) -> None:
    if workspace:
        os.environ["LECTURE_AUTO_WORKSPACE"] = str(Path(workspace).expanduser().resolve())
    if ctx.invoked_subcommand is None:
        from lecture_auto.tui import run_tui
        service = _build_service()
        try:
            run_tui(service, service_factory=_build_service)
        except (KeyboardInterrupt, EOFError):
            typer.echo("\nBye! 👋")
        raise typer.Exit()


def _build_service() -> SessionService:
    from lecture_auto.application import ConfigRepository, build_service_container

    return build_service_container(
        ConfigRepository().load(),
        gemini_adapter_cls=GeminiLLMAdapter,
        ollama_adapter_cls=OllamaLLMAdapter,
    ).session

from typing import Callable, Any

def _run_or_exit(command: str, as_json: bool, action: Callable[..., Any]) -> None:
    try:
        result = action()
    except SessionCommandError as exc:
        typer.echo(format_command_error(command, exc, as_json=as_json))
        raise typer.Exit(code=exc.exit_code)
    typer.echo(format_command_output(result, as_json=as_json))


@session_app.command("create")
def session_create(
    session_id: str = typer.Option(..., "--session-id", help="Session id"),
    date: str = typer.Option(..., "--date", help="Session date YYYY-MM-DD"),
    title: str | None = typer.Option(None, "--title", help="Session title"),
    course: str | None = typer.Option(None, "--course", help="Course name"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    service = _build_service()
    _run_or_exit(
        "session create",
        as_json,
        lambda: service.session_create(
            session_id=session_id,
            date=date,
            title=title,
            course=course,
        ),
    )


@session_app.command("refine-audio")
def session_refine_audio(
    session_id: str = typer.Argument(..., help="Session id"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    service = _build_service()
    _run_or_exit(
        "session refine-audio",
        as_json,
        lambda: service.refine_audio_volume(session_id=session_id),
    )


@session_app.command("refine-noise")
def session_refine_noise(
    session_id: str = typer.Argument(..., help="Session id"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    service = _build_service()
    _run_or_exit(
        "session refine-noise",
        as_json,
        lambda: service.refine_audio_noise(session_id=session_id),
    )


@session_app.command("history")
def session_history(
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    service = _build_service()
    _run_or_exit("session history", as_json, service.session_history)


@session_app.command("detail")
def session_detail(
    session_id: str = typer.Argument(..., help="Session id"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    service = _build_service()
    _run_or_exit("session detail", as_json, lambda: service.session_detail(session_id=session_id))


@session_app.command("delete")
def session_delete_cmd(
    session_id: str = typer.Argument(..., help="Session id to delete"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    service = _build_service()
    _run_or_exit("session delete", as_json, lambda: service.session_delete(session_id=session_id))


@session_app.command("update")
def session_update_cmd(
    session_id: str = typer.Argument(..., help="Session id to update"),
    new_id: str | None = typer.Option(None, "--new-id", help="New session ID (rename)"),
    title: str | None = typer.Option(None, "--title", help="New title (empty string to clear)"),
    course: str | None = typer.Option(None, "--course", help="New course (empty string to clear)"),
    date: str | None = typer.Option(None, "--date", help="New date YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    from lecture_auto.session_service import _UNSET  # type: ignore[attr-defined]

    if new_id is None and title is None and course is None and date is None:
        typer.echo(
            "Error: At least one of --new-id, --title, --course, or --date must be provided."
        )
        raise typer.Exit(code=1)

    service = _build_service()
    kwargs: dict = {}
    if new_id is not None:
        kwargs["new_session_id"] = new_id
    if title is not None:
        kwargs["title"] = title
    if course is not None:
        kwargs["course"] = course
    if date is not None:
        kwargs["date"] = date

    _run_or_exit(
        "session update",
        as_json,
        lambda: service.session_update_metadata(session_id=session_id, **kwargs),
    )


@session_app.command("import-material")
def session_import_material(
    session_id: str = typer.Argument(..., help="Session ID to import material into"),
    material_path: str = typer.Argument(..., help="Path to the PDF material file"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    """Import a PDF lecture material into a session."""
    service = _build_service()
    _run_or_exit(
        "material import",
        as_json,
        lambda: service.import_material(session_id=session_id, material_path=material_path),
    )


@capture_app.command("start")
def capture_start(
    session_id: str = typer.Argument(..., help="Session id"),
    audio_file_path: str | None = typer.Option(
        None,
        "--audio-file-path",
        help="Optional output path",
    ),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    service = _build_service()
    _run_or_exit(
        "capture start",
        as_json,
        lambda: service.capture_start(session_id=session_id, audio_file_path=audio_file_path),
    )


@capture_app.command("stop")
def capture_stop(
    session_id: str = typer.Argument(..., help="Session id"),
    failed: bool = typer.Option(False, "--failed", help="Mark capture as failed"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    service = _build_service()
    _run_or_exit(
        "capture stop",
        as_json,
        lambda: service.capture_stop(session_id=session_id, success=not failed),
    )


@transcription_app.command("run")
def transcription_run(
    session_id: str = typer.Argument(..., help="Session id"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    service = _build_service()
    _run_or_exit(
        "transcription run",
        as_json,
        lambda: service.transcribe_session(session_id=session_id),
    )


@app.command("summarize")
def summarize(
    session_id: str | None = typer.Option(None, "--id", help="Target session id"),
    template: str | None = typer.Option(
        None,
        "--template",
        help="Deprecated; structured-notes is always used",
    ),
    preview: bool = typer.Option(False, "--preview", help="Preview notes without saving"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    service = _build_service()
    session_reference = session_id or ""
    _run_or_exit(
        "summarize",
        as_json,
        lambda: service.summarize_session(
            session_reference=session_reference,
            template_name=template,
            preview=preview,
        ),
    )


@config_app.command("set")
def config_set(
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Default workspace directory"),
    stt_language: str | None = typer.Option(None, "--stt-language", "-stt", help="Default language for STT transcription (e.g. korean)"),
    llm_language: str | None = typer.Option(None, "--llm-language", "-llm", help="Default language for summaries and generated notes (e.g. korean)"),
    stt_api_provider: str | None = typer.Option(None, "--stt-api-provider", help="STT API provider (e.g. deepgram)"),
    stt_api_key: str | None = typer.Option(None, "--stt-api-key", help="STT API key"),
    stt_mode: str | None = typer.Option(None, "--stt-mode", help="STT mode (api or local)"),
    stt_local_model: str | None = typer.Option(None, "--stt-local-model", help="Local Whisper model name (e.g. base, medium, large-v3)"),
    stt_local_device: str | None = typer.Option(None, "--stt-device", help="Local STT device (auto, cpu, cuda)"),
    stt_compute_type: str | None = typer.Option(None, "--stt-compute-type", help="Local STT compute type"),
    stt_batch_size: int | None = typer.Option(None, "--stt-batch-size", help="Local STT batch size (1 to 64)"),
    stt_beam_size: int | None = typer.Option(None, "--stt-beam-size", help="Local STT beam size (1 to 20)"),
    stt_temperature: float | None = typer.Option(None, "--stt-temperature", help="Local STT temperature (0.0 to 1.0)"),
    stt_vad_filter: bool | None = typer.Option(None, "--stt-vad-filter/--no-stt-vad-filter", help="Enable Silero VAD for local STT"),
    stt_vad_min_silence_ms: int | None = typer.Option(None, "--stt-vad-min-silence-ms", help="VAD minimum silence duration in milliseconds"),
    stt_condition_on_previous_text: bool | None = typer.Option(None, "--stt-condition-on-previous-text/--no-stt-condition-on-previous-text", help="Condition each Whisper window on previous text"),
    stt_word_timestamps: bool | None = typer.Option(None, "--stt-word-timestamps/--no-stt-word-timestamps", help="Collect local STT word timestamps and confidence"),
    stt_hotwords: str | None = typer.Option(None, "--stt-hotwords", help="Whitespace-separated local STT hotwords"),
    stt_cpu_threads: int | None = typer.Option(None, "--stt-cpu-threads", help="Local STT CPU thread count; 0 uses runtime default"),
    stt_num_workers: int | None = typer.Option(None, "--stt-num-workers", help="Local STT parallel worker count"),
    gemini_api_key: str | None = typer.Option(None, "--gemini-api-key", help="Google API key for hosted LLMs"),
    llm_model_name: str | None = typer.Option(None, "--llm-model", help="LLM model name (Gemini or Gemma 4 hosted model ID)"),
    llm_thinking_level: str | None = typer.Option(None, "--llm-thinking-level", help="LLM thinking level (minimal, low, medium, high)"),
    audio_format: str | None = typer.Option(None, "--audio-format", help="Default audio format for recordings (wav or mp3)"),
    capture_source: str | None = typer.Option(None, "--capture-source", help="Capture source (microphone or system_audio)"),
    use_dynaudnorm: bool | None = typer.Option(None, "--use-dynaudnorm/--no-use-dynaudnorm", help="Apply dynaudnorm audio filter during STT pre-processing."),
    dynaudnorm_f: int | None = typer.Option(None, "--dynaudnorm-f", help="dynaudnorm 'f' parameter (10 to 8000)."),
    dynaudnorm_g: int | None = typer.Option(None, "--dynaudnorm-g", help="dynaudnorm 'g' parameter (odd integer 3 to 301)."),
    gain_db: float | None = typer.Option(None, "--gain-db", help="Additional volume gain in dB (-60.0 to 60.0)."),
) -> None:
    config_path = _get_global_config_path()
    config_data = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception:
            pass
    
    updated = False
    stt_perf_updated = False
    if workspace is not None:
        config_data["workspace"] = str(Path(workspace).expanduser().resolve())
        typer.echo(f"Global workspace set to: {config_data['workspace']}")
        updated = True
        
    if stt_language is not None:
        config_data["stt_language"] = stt_language
        typer.echo(f"Global STT language set to: {config_data['stt_language']}")
        updated = True

    if llm_language is not None:
        config_data["llm_language"] = llm_language
        typer.echo(f"Global LLM language set to: {config_data['llm_language']}")
        updated = True

    if stt_api_provider is not None:
        normalized_provider = stt_api_provider.strip().lower()
        if normalized_provider not in SUPPORTED_API_PROVIDERS:
            typer.echo(
                f"STT API provider must be one of {sorted(SUPPORTED_API_PROVIDERS)}.",
                err=True,
            )
            raise typer.Exit(code=1)
        config_data["stt_api_provider"] = normalized_provider
        typer.echo(f"Global STT API provider set to: {config_data['stt_api_provider']}")
        updated = True

    if stt_api_key is not None:
        from lecture_auto.application import ConfigRepository
        ConfigRepository().set_secret("stt_api_key", stt_api_key)
        config_data.pop("stt_api_key", None)
        typer.echo(f"Global STT API key configured.")
        updated = True

    if stt_mode is not None:
        normalized_mode = stt_mode.strip().lower()
        if normalized_mode not in {"api", "local"}:
            typer.echo("STT mode must be 'api' or 'local'.", err=True)
            raise typer.Exit(code=1)
        config_data["stt_mode"] = normalized_mode
        typer.echo(f"Global STT mode set to: {config_data['stt_mode']}")
        updated = True

    if stt_local_model is not None:
        normalized_model = stt_local_model.strip()
        if normalized_model:
            config_data["stt_local_model"] = normalized_model
            typer.echo(f"Global STT local model set to: {config_data['stt_local_model']}")
            updated = True
        elif "stt_local_model" in config_data:
            del config_data["stt_local_model"]
            typer.echo("Global STT local model cleared.")
            updated = True

    if stt_local_device is not None:
        normalized_device = stt_local_device.strip().lower()
        if normalized_device not in SUPPORTED_LOCAL_DEVICES:
            typer.echo(
                f"STT device must be one of {sorted(SUPPORTED_LOCAL_DEVICES)}.",
                err=True,
            )
            raise typer.Exit(code=1)
        config_data["stt_local_device"] = normalized_device
        typer.echo(f"Global STT device set to: {normalized_device}")
        updated = stt_perf_updated = True

    if stt_compute_type is not None:
        normalized_compute_type = stt_compute_type.strip().lower()
        if normalized_compute_type not in SUPPORTED_COMPUTE_TYPES:
            typer.echo(
                f"STT compute type must be one of {sorted(SUPPORTED_COMPUTE_TYPES)}.",
                err=True,
            )
            raise typer.Exit(code=1)
        config_data["stt_compute_type"] = normalized_compute_type
        typer.echo(f"Global STT compute type set to: {normalized_compute_type}")
        updated = stt_perf_updated = True

    numeric_stt_options = (
        ("stt_batch_size", stt_batch_size),
        ("stt_beam_size", stt_beam_size),
        ("stt_vad_min_silence_duration_ms", stt_vad_min_silence_ms),
        ("stt_cpu_threads", stt_cpu_threads),
        ("stt_num_workers", stt_num_workers),
    )
    for key, value in numeric_stt_options:
        if value is not None:
            config_data[key] = value
            typer.echo(f"Global {key} set to: {value}")
            updated = stt_perf_updated = True

    if stt_temperature is not None:
        config_data["stt_temperature"] = stt_temperature
        typer.echo(f"Global stt_temperature set to: {stt_temperature}")
        updated = stt_perf_updated = True

    boolean_stt_options = (
        ("stt_vad_filter", stt_vad_filter),
        ("stt_condition_on_previous_text", stt_condition_on_previous_text),
        ("stt_word_timestamps", stt_word_timestamps),
    )
    for key, value in boolean_stt_options:
        if value is not None:
            config_data[key] = value
            typer.echo(f"Global {key} set to: {value}")
            updated = stt_perf_updated = True

    if stt_hotwords is not None:
        config_data["stt_hotwords"] = stt_hotwords.strip() or None
        typer.echo("Global STT hotwords updated.")
        updated = stt_perf_updated = True

    if stt_perf_updated:
        candidate = STTConfig(
            mode="local",
            local_model_name=str(config_data.get("stt_local_model") or "base"),
            local_device=str(config_data.get("stt_local_device") or "cpu"),  # type: ignore[arg-type]
            compute_type=str(config_data.get("stt_compute_type") or "int8"),
            batch_size=int(config_data.get("stt_batch_size") or 1),
            beam_size=int(config_data.get("stt_beam_size") or 5),
            temperature=(
                float(config_data["stt_temperature"])
                if config_data.get("stt_temperature") is not None
                else None
            ),
            vad_filter=bool(config_data.get("stt_vad_filter", False)),
            vad_min_silence_duration_ms=int(
                config_data.get("stt_vad_min_silence_duration_ms", 2000)
            ),
            condition_on_previous_text=bool(
                config_data.get("stt_condition_on_previous_text", True)
            ),
            word_timestamps=bool(config_data.get("stt_word_timestamps", False)),
            hotwords=str(config_data.get("stt_hotwords") or "") or None,
            cpu_threads=int(config_data.get("stt_cpu_threads") or 0),
            num_workers=int(config_data.get("stt_num_workers") or 1),
        )
        try:
            candidate.validate()
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

    if gemini_api_key is not None:
        from lecture_auto.application import ConfigRepository
        ConfigRepository().set_secret("gemini_api_key", gemini_api_key)
        config_data.pop("gemini_api_key", None)
        typer.echo(f"Global Google API key configured.")
        updated = True

    if llm_model_name is not None:
        normalized_model = normalize_gemini_model_name(llm_model_name)
        valid_models = set(GEMINI_MODEL_CHOICES)
        if normalized_model not in valid_models:
            typer.echo(
                f"LLM model must be one of {valid_models}.",
                err=True,
            )
            raise typer.Exit(code=1)
        config_data["llm_model_name"] = normalized_model
        typer.echo(f"Global LLM model set to: {config_data['llm_model_name']}")
        updated = True

    if llm_thinking_level is not None:
        normalized_level = llm_thinking_level.strip().lower()
        valid_levels = {"minimal", "low", "medium", "high"}
        if normalized_level not in valid_levels:
            typer.echo(
                f"LLM thinking level must be one of {valid_levels}.",
                err=True,
            )
            raise typer.Exit(code=1)
        config_data["llm_thinking_level"] = normalized_level
        typer.echo(f"Global LLM thinking level set to: {config_data['llm_thinking_level']}")
        updated = True

    if audio_format is not None:
        if audio_format not in ("wav", "mp3"):
            typer.echo("Audio format must be 'wav' or 'mp3'.", err=True)
            raise typer.Exit(code=1)
        config_data["audio_format"] = audio_format
        typer.echo(f"Global audio format set to: {config_data['audio_format']}")
        updated = True

    if capture_source is not None:
        normalized_source = capture_source.strip().lower()
        if normalized_source not in ("microphone", "system_audio"):
            typer.echo("Capture source must be 'microphone' or 'system_audio'.", err=True)
            raise typer.Exit(code=1)
        config_data["capture_source"] = normalized_source
        typer.echo(f"Global capture source set to: {config_data['capture_source']}")
        updated = True

    if use_dynaudnorm is not None:
        config_data["use_dynaudnorm"] = use_dynaudnorm
        typer.echo(f"Global use_dynaudnorm set to: {config_data['use_dynaudnorm']}")
        updated = True

    if dynaudnorm_f is not None:
        if dynaudnorm_f < 10 or dynaudnorm_f > 8000:
            typer.echo("dynaudnorm_f must be between 10 and 8000.", err=True)
            raise typer.Exit(code=1)
        config_data["dynaudnorm_f"] = dynaudnorm_f
        typer.echo(f"Global dynaudnorm_f set to: {config_data['dynaudnorm_f']}")
        updated = True

        if dynaudnorm_g is not None:
            if dynaudnorm_g < 3 or dynaudnorm_g > 301 or dynaudnorm_g % 2 == 0:
                typer.echo("dynaudnorm_g must be an odd integer between 3 and 301.", err=True)
                raise typer.Exit(code=1)
            config_data["dynaudnorm_g"] = dynaudnorm_g
            typer.echo(f"Global dynaudnorm_g set to: {config_data['dynaudnorm_g']}")
            updated = True

        if gain_db is not None:
            if gain_db < -60.0 or gain_db > 60.0:
                typer.echo("gain_db must be between -60.0 and 60.0.", err=True)
                raise typer.Exit(code=1)
            config_data["gain_db"] = gain_db
            typer.echo(f"Global gain_db set to: {config_data['gain_db']}")
            updated = True

    if not updated:
        typer.echo("No configuration options provided to set.")
        return

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)


@config_app.command("show")
def config_show() -> None:
    from lecture_auto.application import ConfigRepository

    repository = ConfigRepository()
    if not repository.exists():
        typer.echo("No global configuration found.")
        return
    typer.echo(json.dumps(repository.masked_dict(), indent=2))


@library_app.command("list")
def library_list(
    from_date: str | None = typer.Option(None, "--from", help="Start date (YYYY-MM-DD)"),
    to_date: str | None = typer.Option(None, "--to", help="End date (YYYY-MM-DD)"),
    status: str | None = typer.Option(None, "--status", help="Filter by status"),
    sort: str | None = typer.Option(None, "--sort", help="Sort by 'recent'"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    store = SessionMetadataStore(metadata_file=(Path(os.environ.get("LECTURE_AUTO_WORKSPACE") or Path.home() / ".lecture_auto") / "metadata" / "sessions.json"))
    library_service = LibraryService(store=store, base_dir=Path(os.environ.get("LECTURE_AUTO_WORKSPACE") or Path.home() / ".lecture_auto"))
    _run_or_exit(
        "library list",
        as_json,
        lambda: library_service.library_list(
            from_date=from_date,
            to_date=to_date,
            status_filter=status,
            sort_recent=(sort == "recent"),
        ),
    )


@library_app.command("search")
def library_search(
    query: str = typer.Argument(..., help="Search query"),
    from_date: str | None = typer.Option(None, "--from", help="Start date (YYYY-MM-DD)"),
    to_date: str | None = typer.Option(None, "--to", help="End date (YYYY-MM-DD)"),
    status: str | None = typer.Option(None, "--status", help="Filter by status"),
    sort: str | None = typer.Option(None, "--sort", help="Sort by 'recent'"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    workspace = Path(os.environ.get("LECTURE_AUTO_WORKSPACE") or Path.home() / ".lecture_auto")
    store = SessionMetadataStore(metadata_file=workspace / "metadata" / "sessions.json")
    library_service = LibraryService(store=store, base_dir=workspace)
    _run_or_exit(
        "library search",
        as_json,
        lambda: library_service.library_search(
            query=query,
            from_date=from_date,
            to_date=to_date,
            status_filter=status,
            sort_recent=(sort == "recent"),
        ),
    )


@library_app.command("open")
def library_open(
    session_id: str = typer.Argument(..., help="Session ID"),
    transcript: bool = typer.Option(False, "--transcript", help="Open transcripts folder"),
    recordings: bool = typer.Option(False, "--recordings", help="Open recordings folder"),
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    workspace = Path(os.environ.get("LECTURE_AUTO_WORKSPACE") or Path.home() / ".lecture_auto")
    store = SessionMetadataStore(metadata_file=workspace / "metadata" / "sessions.json")
    library_service = LibraryService(store=store, base_dir=workspace)
    _run_or_exit(
        "library open",
        as_json,
        lambda: library_service.library_open(
            session_id=session_id,
            open_transcript=transcript,
            open_recordings=recordings,
        ),
    )


@runtime_app.command("status")
def runtime_status(
    as_json: bool = typer.Option(False, "--json", help="Render output as JSON"),
) -> None:
    from lecture_auto.local_runtime import LocalRuntimeManager

    status = asdict(LocalRuntimeManager().probe())
    if as_json:
        typer.echo(json.dumps(status, ensure_ascii=False, separators=(",", ":")))
        return
    typer.echo(f"Python: {status['python_path'] or 'not installed'}")
    typer.echo(f"Version: {status['python_version'] or '-'} ({status['architecture'] or '-'})")
    typer.echo(f"Whisper: {'installed' if status['whisper_installed'] else 'not installed'}")
    typer.echo(f"DeepFilterNet: {'installed' if status['deepfilter_installed'] else 'not installed'}")
    typer.echo(f"Gemini add-on: {'installed' if status['gemini_installed'] else 'not installed'}")
    if status.get("error"):
        typer.echo(f"Error: {status['error']}")


@runtime_app.command("install")
def runtime_install(
    feature: str = typer.Option("all", "--feature", help="whisper, deepfilter, gemini, or all"),
) -> None:
    from lecture_auto.local_runtime import LocalRuntimeManager

    normalized = feature.strip().lower()
    if normalized not in {"whisper", "deepfilter", "gemini", "all"}:
        raise typer.BadParameter("feature must be whisper, deepfilter, gemini, or all")
    manager = LocalRuntimeManager()

    def progress(stage, completed, total, message) -> None:
        suffix = f" ({completed}/{total})" if completed is not None and total is not None else ""
        typer.echo(f"[{stage}] {message}{suffix}")

    if normalized == "whisper":
        status = manager.install_whisper(progress=progress)
    elif normalized == "deepfilter":
        status = manager.install_deepfilter(progress=progress)
    elif normalized == "gemini":
        status = manager.install_gemini(progress=progress)
    else:
        status = manager.install_all(progress=progress)
    typer.echo(f"Runtime ready: {status.python_path}")


@runtime_app.command("remove")
def runtime_remove(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    from lecture_auto.local_runtime import LocalRuntimeManager

    if not yes and not typer.confirm("Remove the managed local AI runtime?"):
        raise typer.Abort()
    LocalRuntimeManager().remove()
    typer.echo("Managed local AI runtime removed.")


@runtime_app.command("repair")
def runtime_repair() -> None:
    from lecture_auto.local_runtime import LocalRuntimeManager

    status = LocalRuntimeManager().repair(
        progress=lambda stage, completed, total, message: typer.echo(f"[{stage}] {message}")
    )
    typer.echo(f"Runtime repaired: {status.python_path}")


app.add_typer(session_app, name="session")
app.add_typer(capture_app, name="capture")
app.add_typer(transcription_app, name="transcription")
app.add_typer(config_app, name="config")
app.add_typer(library_app, name="library")
app.add_typer(runtime_app, name="runtime")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
