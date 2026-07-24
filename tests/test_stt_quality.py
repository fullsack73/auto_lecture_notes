from lecture_auto.stt_quality import assess_stt_quality
from lecture_auto.stt_runtime import DiarizedSegment


def test_assess_stt_quality_flags_confidence_rate_and_repetition() -> None:
    result = assess_stt_quality(
        [
            DiarizedSegment(
                speaker="Speaker",
                start_time=10,
                end_time=11,
                text="반복 반복 반복 반복 매우 긴 문자율입니다",
                avg_logprob=-1.2,
                compression_ratio=2.5,
                no_speech_prob=0.8,
            )
        ],
        max_characters_per_second=5,
    )

    assert result["suspect_segment_count"] == 1
    assert result["reason_counts"] == {
        "low_logprob": 1,
        "high_compression_ratio": 1,
        "speech_on_high_no_speech_probability": 1,
        "excessive_character_rate": 1,
        "repetition_loop": 1,
    }


def test_assess_stt_quality_keeps_normal_segment() -> None:
    result = assess_stt_quality(
        [
            DiarizedSegment(
                speaker="Speaker",
                start_time=0,
                end_time=4,
                text="정상적인 강의 문장입니다",
                avg_logprob=-0.2,
                compression_ratio=1.2,
                no_speech_prob=0.01,
            )
        ]
    )

    assert result["suspect_segment_count"] == 0
    assert result["suspect_segments"] == []
