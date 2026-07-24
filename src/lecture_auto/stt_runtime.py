from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import os
import tempfile
import math

from lecture_auto.capture_runtime import resolve_ffmpeg_bin, resolve_ffprobe_bin


class STTRuntimeError(RuntimeError):
    """Base class for transcription runtime failures."""


class STTConfigError(STTRuntimeError):
    """Raised when STT mode/provider config is invalid."""


class STTProviderAuthError(STTRuntimeError):
    """Raised when STT provider credentials are invalid."""


class STTTransientNetworkError(STTRuntimeError):
    """Raised for retryable provider/network failures."""


class STTAudioDecodeError(STTRuntimeError):
    """Raised when the audio input cannot be decoded by STT runtime."""


@dataclass
class WordTimestamp:
    """A word-level timing and confidence emitted by an STT provider."""

    word: str
    start_time: float
    end_time: float
    probability: float | None = None


@dataclass
class DiarizedSegment:
    """A single speaker-attributed segment of transcription."""

    speaker: str
    start_time: float
    end_time: float
    text: str
    avg_logprob: float | None = None
    compression_ratio: float | None = None
    no_speech_prob: float | None = None
    temperature: float | None = None
    words: list[WordTimestamp] = field(default_factory=list)


@dataclass
class STTResult:
    transcript_text: str
    provider: str
    mode: str
    language: str | None = None
    segments: list[DiarizedSegment] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_plain_text(self) -> str:
        """Return a horizontal plain-text transcript."""
        if not self.segments:
            return self.transcript_text

        text_parts = [seg.text.strip() for seg in self.segments if seg.text.strip()]
        return " ".join(text_parts).strip()

    def to_diarized_markdown(self) -> str:
        """Format transcription with speaker diarization as Markdown."""
        if not self.segments:
            return self.transcript_text

        lines: list[str] = []
        current_speaker: str | None = None
        for seg in self.segments:
            if seg.speaker != current_speaker:
                current_speaker = seg.speaker
                lines.append(f"\n**{current_speaker}**\n")
            timestamp = f"[{_format_ts(seg.start_time)} - {_format_ts(seg.end_time)}]"
            lines.append(f"{timestamp} {seg.text}")

        return "\n".join(lines).strip()

    def to_metadata_dict(self) -> dict[str, object]:
        """Return a JSON-safe sidecar without changing transcript text formats."""
        return {
            "schema_version": 1,
            "provider": self.provider,
            "mode": self.mode,
            "language": self.language,
            "metadata": self.metadata,
            "segments": [
                {
                    "speaker": segment.speaker,
                    "start_time": segment.start_time,
                    "end_time": segment.end_time,
                    "text": segment.text,
                    "avg_logprob": segment.avg_logprob,
                    "compression_ratio": segment.compression_ratio,
                    "no_speech_prob": segment.no_speech_prob,
                    "temperature": segment.temperature,
                    "words": [
                        {
                            "word": word.word,
                            "start_time": word.start_time,
                            "end_time": word.end_time,
                            "probability": word.probability,
                        }
                        for word in segment.words
                    ],
                }
                for segment in self.segments
            ],
        }


def _format_ts(seconds: float) -> str:
    """Convert seconds to MM:SS format."""
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes:02d}:{secs:02d}"


def _get_audio_duration(file_path: str) -> float:
    """Get audio duration using ffprobe."""
    try:
        result = subprocess.run(
            [
                resolve_ffprobe_bin(),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception as e:
        raise STTAudioDecodeError(f"Failed to get audio duration: {e}")


def _split_audio(file_path: str, chunk_duration: int = 600) -> list[str]:
    """Split audio into chunks using ffmpeg."""
    duration = _get_audio_duration(file_path)
    chunks = []
    num_chunks = math.ceil(duration / chunk_duration)

    base_dir = tempfile.mkdtemp(prefix="stt_chunks_")

    for i in range(num_chunks):
        start_time = i * chunk_duration
        out_path = os.path.join(base_dir, f"chunk_{i:03d}.wav")
        try:
            subprocess.run(
                [
                    resolve_ffmpeg_bin(),
                    "-y",
                    "-i",
                    file_path,
                    "-ss",
                    str(start_time),
                    "-t",
                    str(chunk_duration),
                    "-c",
                    "copy",
                    out_path,
                ],
                capture_output=True,
                check=True,
            )
            chunks.append(out_path)
        except subprocess.CalledProcessError as e:
            raise STTAudioDecodeError(f"Failed to split audio: {e.stderr.decode()}")

    return chunks


class STTRuntimeAdapter(Protocol):
    def transcribe(self, *, audio_path: str) -> STTResult:
        ...


class LocalSTTRuntimeAdapter:
    """Deterministic local adapter used for non-device/unit-test environments."""

    def __init__(self, model_name: str = "base") -> None:
        self.model_name = model_name

    def transcribe(self, *, audio_path: str) -> STTResult:
        if not audio_path.strip():
            raise STTConfigError("Audio path is required for transcription.")
        return STTResult(
            transcript_text=f"[local:{self.model_name}] transcript for {audio_path}",
            provider="local-model",
            mode="local",
        )

    def batch_transcribe(self, *, audio_paths: list[str]) -> dict[str, STTResult]:
        """Transcribe multiple audio files in parallel."""
        if not audio_paths:
            raise STTConfigError("Audio paths are required for batch transcription.")

        results: dict[str, STTResult] = {}
        with ThreadPoolExecutor() as executor:
            future_to_audio = {
                executor.submit(self.transcribe, audio_path=path): path for path in audio_paths
            }
            for future in as_completed(future_to_audio):
                audio_path = future_to_audio[future]
                try:
                    results[audio_path] = future.result()
                except Exception as e:
                    results[audio_path] = STTResult(
                        transcript_text=f"Error: {e}",
                        provider="local-model",
                        mode="local",
                    )

        return results

    def transcribe_parallel(self, *, audio_path: str, chunk_duration: int = 600, max_workers: int = 4) -> STTResult:
        """Transcribe a single audio file by splitting it into chunks and processing them in parallel."""
        if not audio_path.strip():
            raise STTConfigError("Audio path is required for transcription.")

        chunks = _split_audio(audio_path, chunk_duration=chunk_duration)
        chunk_results: dict[int, STTResult] = {}

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_idx = {
                    executor.submit(self.transcribe, audio_path=chunk): idx
                    for idx, chunk in enumerate(chunks)
                }

                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        chunk_results[idx] = future.result()
                    except Exception as e:
                        # Depending on requirements, we could fail the whole process or just insert an error mark
                        chunk_results[idx] = STTResult(
                            transcript_text=f"[Error processing chunk {idx}: {e}]",
                            provider=self.model_name,
                            mode="local"
                        )

            # Combine results in correct order
            combined_text = ""
            combined_segments = []

            for i in range(len(chunks)):
                res = chunk_results[i]

                # Append text
                if combined_text:
                    combined_text += " "
                combined_text += res.transcript_text

                # Offset segment timestamps
                offset = i * chunk_duration
                for seg in res.segments:
                    # Create a new segment to avoid mutating the original
                    new_seg = DiarizedSegment(
                        speaker=seg.speaker,
                        start_time=seg.start_time + offset,
                        end_time=seg.end_time + offset,
                        text=seg.text
                    )
                    combined_segments.append(new_seg)

            return STTResult(
                transcript_text=combined_text,
                provider="local-model",
                mode="local",
                segments=combined_segments
            )

        finally:
            # Clean up chunks
            for chunk in chunks:
                try:
                    os.remove(chunk)
                except OSError:
                    pass
            try:
                os.rmdir(os.path.dirname(chunks[0]))
            except (OSError, IndexError):
                pass


class APISTTRuntimeAdapter:
    """Deterministic API adapter placeholder for contract and tests."""

    def __init__(self, provider: str, api_key: str) -> None:
        self.provider = provider
        self.api_key = api_key

    def transcribe(self, *, audio_path: str) -> STTResult:
        if not self.provider.strip():
            raise STTConfigError("API provider is required.")
        if not self.api_key.strip():
            raise STTProviderAuthError("API key is missing.")
        if not audio_path.strip():
            raise STTConfigError("Audio path is required for transcription.")

        return STTResult(
            transcript_text=f"[api:{self.provider}] transcript for {audio_path}",
            provider=self.provider,
            mode="api",
        )
