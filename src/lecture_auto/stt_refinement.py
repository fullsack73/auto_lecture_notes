from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class RefinementAudit:
    source_sha256: str
    output_sha256: str
    source_characters: int
    output_characters: int
    inserted_numbers: tuple[str, ...]
    removed_numbers: tuple[str, ...]
    changed_named_terms: tuple[str, ...]
    added_lines: int
    removed_lines: int
    unified_diff: str

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        for key in ("inserted_numbers", "removed_numbers", "changed_named_terms"):
            value[key] = list(value[key])  # type: ignore[index]
        return value


def build_refinement_evidence(
    metadata: dict[str, Any] | None,
    *,
    max_segments: int = 80,
) -> dict[str, object]:
    metadata = metadata or {}
    segments = metadata.get("segments") or []
    evidence_segments: list[dict[str, object]] = []
    for value in segments[:max_segments] if isinstance(segments, list) else []:
        if not isinstance(value, dict):
            continue
        evidence_segments.append(
            {
                "start_time": value.get("start_time"),
                "end_time": value.get("end_time"),
                "text": value.get("text"),
                "avg_logprob": value.get("avg_logprob"),
                "no_speech_prob": value.get("no_speech_prob"),
            }
        )
    runtime = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    return {
        "segments": evidence_segments,
        "quality": runtime.get("quality") if isinstance(runtime, dict) else None,
        "asr_passes": runtime.get("asr_passes") if isinstance(runtime, dict) else None,
        "rule": (
            "Use surrounding lecture context and alternative ASR candidates to correct "
            "phonetically plausible recognition errors. Low confidence alone does not "
            "make a span unclear. Material/glossary terms may validate a contextually "
            "supported spelling but are not evidence that a fact was spoken. Use "
            "[불명확 mm:ss] only when multiple plausible readings remain."
        ),
    }


def format_refinement_evidence(evidence: dict[str, object] | None) -> str:
    if not evidence:
        return ""
    return (
        "\n\nASR evidence (use as supporting context for corrections and uncertainty):\n"
        + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    )


def audit_refinement(source: str, output: str) -> RefinementAudit:
    source_numbers = _numbers(source)
    output_numbers = _numbers(output)
    inserted_numbers = tuple(sorted(set(output_numbers) - set(source_numbers)))
    removed_numbers = tuple(sorted(set(source_numbers) - set(output_numbers)))
    source_terms = _named_terms(source)
    output_terms = _named_terms(output)
    changed_terms = tuple(sorted(source_terms.symmetric_difference(output_terms)))
    diff_lines = list(
        difflib.unified_diff(
            source.splitlines(),
            output.splitlines(),
            fromfile="raw",
            tofile="edited",
            lineterm="",
        )
    )
    return RefinementAudit(
        source_sha256=_sha256_text(source),
        output_sha256=_sha256_text(output),
        source_characters=len(source),
        output_characters=len(output),
        inserted_numbers=inserted_numbers,
        removed_numbers=removed_numbers,
        changed_named_terms=changed_terms,
        added_lines=sum(line.startswith("+") and not line.startswith("+++") for line in diff_lines),
        removed_lines=sum(line.startswith("-") and not line.startswith("---") for line in diff_lines),
        unified_diff="\n".join(diff_lines),
    )


def write_refinement_audit(path: Path, audit: RefinementAudit) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(audit.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def segment_chunks(
    text: str,
    *,
    chunk_size: int,
    overlap_characters: int = 240,
) -> list[str]:
    """Split at sentence/space boundaries with bounded overlap for context."""
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        if end < len(text):
            boundary = max(
                text.rfind(marker, start + chunk_size // 2, end)
                for marker in ("\n", ". ", "? ", "! ", "。", "다. ")
            )
            if boundary < start + chunk_size // 2:
                boundary = text.rfind(" ", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(start + 1, end - min(overlap_characters, end - start - 1))
    return chunks


def merge_refined_chunks(chunks: Iterable[str], *, overlap_characters: int = 240) -> str:
    values = [value.strip() for value in chunks if value.strip()]
    if not values:
        return ""
    merged = values[0]
    for value in values[1:]:
        match = _longest_overlap(merged[-overlap_characters:], value[:overlap_characters])
        merged += ("\n" if not match else "") + value[len(match) :]
    return merged


def _longest_overlap(left: str, right: str, minimum: int = 12) -> str:
    maximum = min(len(left), len(right))
    for size in range(maximum, minimum - 1, -1):
        if left[-size:] == right[:size]:
            return right[:size]
    return ""


def _numbers(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"(?<!\w)[+-]?\d+(?:[.,:/-]\d+)*(?:%|[a-zA-Z]+)?", text))


def _named_terms(text: str) -> set[str]:
    return {
        value.casefold()
        for value in re.findall(
            r"\b(?:[A-Z][A-Za-z0-9+.#-]{1,}|[A-Z]{2,}(?:-[A-Z0-9]+)*)\b",
            text,
        )
    }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
