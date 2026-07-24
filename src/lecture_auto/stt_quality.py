from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from lecture_auto.stt_runtime import DiarizedSegment


@dataclass(frozen=True)
class SuspectSTTSegment:
    start_time: float
    end_time: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "reasons": list(self.reasons),
        }


def assess_stt_quality(
    segments: Sequence[DiarizedSegment],
    *,
    logprob_threshold: float = -1.0,
    compression_ratio_threshold: float = 2.4,
    no_speech_threshold: float = 0.6,
    max_characters_per_second: float = 15.0,
) -> dict[str, object]:
    suspects: list[SuspectSTTSegment] = []
    reason_counts: dict[str, int] = {}

    for segment in segments:
        reasons: list[str] = []
        text = segment.text.strip()
        duration = max(0.0, segment.end_time - segment.start_time)
        if segment.avg_logprob is not None and segment.avg_logprob < logprob_threshold:
            reasons.append("low_logprob")
        if (
            segment.compression_ratio is not None
            and segment.compression_ratio > compression_ratio_threshold
        ):
            reasons.append("high_compression_ratio")
        if (
            text
            and segment.no_speech_prob is not None
            and segment.no_speech_prob > no_speech_threshold
        ):
            reasons.append("speech_on_high_no_speech_probability")
        if duration > 0 and len(_normalized_characters(text)) / duration > max_characters_per_second:
            reasons.append("excessive_character_rate")
        if _has_repetition_loop(text):
            reasons.append("repetition_loop")

        if reasons:
            suspect = SuspectSTTSegment(
                start_time=segment.start_time,
                end_time=segment.end_time,
                reasons=tuple(reasons),
            )
            suspects.append(suspect)
            for reason in reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

    suspect_duration = sum(
        max(0.0, suspect.end_time - suspect.start_time) for suspect in suspects
    )
    total_duration = max(
        (segment.end_time for segment in segments),
        default=0.0,
    )
    return {
        "segment_count": len(segments),
        "suspect_segment_count": len(suspects),
        "suspect_duration_seconds": suspect_duration,
        "suspect_duration_ratio": (
            min(1.0, suspect_duration / total_duration) if total_duration else 0.0
        ),
        "reason_counts": reason_counts,
        "suspect_segments": [suspect.to_dict() for suspect in suspects],
        "thresholds": {
            "avg_logprob": logprob_threshold,
            "compression_ratio": compression_ratio_threshold,
            "no_speech_probability": no_speech_threshold,
            "characters_per_second": max_characters_per_second,
        },
    }


def _normalized_characters(text: str) -> str:
    return "".join(re.findall(r"[\w가-힣]", text.lower(), flags=re.UNICODE))


def _has_repetition_loop(text: str) -> bool:
    words = re.findall(r"[\w가-힣]+", text.lower(), flags=re.UNICODE)
    if not words:
        return False

    run = 1
    for previous, current in zip(words, words[1:]):
        if current == previous:
            run += 1
            if run >= 4:
                return True
        else:
            run = 1

    for size in range(2, min(6, len(words) // 2 + 1)):
        for end in range(size * 2, len(words) + 1):
            if words[end - size * 2 : end - size] == words[end - size : end]:
                return True
    return False
