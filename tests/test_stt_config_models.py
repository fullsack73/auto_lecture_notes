"""Focused tests for STTConfig and STTResult config-layer changes (Task Group 1)."""
from __future__ import annotations

import pytest

from lecture_auto.stt_config import (
    LOCAL_MODEL_RECOMMENDATIONS,
    LOCAL_STT_HARDWARE_GUIDE,
    STTConfig,
    SUPPORTED_API_PROVIDERS,
)
from lecture_auto.stt_runtime import DiarizedSegment, STTResult


def test_stt_config_language_defaults_to_none() -> None:
    config = STTConfig()
    assert config.language is None


def test_stt_config_language_can_be_set() -> None:
    config = STTConfig(language="english")
    assert config.language == "english"


def test_stt_config_diarization_defaults_to_false() -> None:
    config = STTConfig()
    assert config.diarization is False


def test_stt_config_diarization_enabled() -> None:
    config = STTConfig(diarization=True)
    assert config.diarization is True


def test_stt_config_dynaudnorm_defaults_to_false() -> None:
    config = STTConfig()
    assert config.use_dynaudnorm is False


def test_stt_config_dynaudnorm_accepts_valid_params() -> None:
    config = STTConfig(mode="local", local_model_name="base", use_dynaudnorm=True, dynaudnorm_f=100, dynaudnorm_g=31)
    config.validate()


def test_stt_config_accepts_optimized_local_options() -> None:
    config = STTConfig(
        mode="local",
        local_model_name="base",
        local_device="auto",
        compute_type="auto",
        batch_size=4,
        beam_size=1,
        temperature=0.0,
        vad_filter=True,
        vad_min_silence_duration_ms=1000,
        condition_on_previous_text=False,
        word_timestamps=True,
        hotwords="OpenGL rasterization",
        cpu_threads=8,
        num_workers=2,
    )

    config.validate()


def test_stt_config_rejects_batch_without_vad() -> None:
    config = STTConfig(
        mode="local",
        local_model_name="base",
        batch_size=4,
        vad_filter=False,
    )

    with pytest.raises(ValueError, match="requires vad_filter"):
        config.validate()


def test_stt_config_rejects_unknown_device() -> None:
    config = STTConfig(
        mode="local",
        local_model_name="base",
        local_device="metal",  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="Unsupported local STT device"):
        config.validate()


def test_hardware_recommendations_cover_supported_model_presets() -> None:
    assert [name for name, _description in LOCAL_MODEL_RECOMMENDATIONS] == [
        "base",
        "small",
        "medium",
        "large-v3",
    ]
    assert "자동 적용 아님" in LOCAL_STT_HARDWARE_GUIDE
    assert "Apple Silicon" in LOCAL_STT_HARDWARE_GUIDE
    assert "NVIDIA 16GB+" in LOCAL_STT_HARDWARE_GUIDE


def test_stt_config_dynaudnorm_rejects_invalid_f() -> None:
    config = STTConfig(mode="local", local_model_name="base", dynaudnorm_f=5)
    with pytest.raises(ValueError, match="10 and 8000"):
        config.validate()


def test_stt_config_dynaudnorm_rejects_invalid_g_even() -> None:
    config = STTConfig(mode="local", local_model_name="base", dynaudnorm_g=30)
    with pytest.raises(ValueError, match="odd integer"):
        config.validate()


def test_stt_config_deepgram_provider_is_supported() -> None:
    assert "deepgram" in SUPPORTED_API_PROVIDERS


def test_stt_config_validation_passes_with_deepgram_provider() -> None:
    config = STTConfig(mode="api", api_provider="deepgram", api_key="dg-key-123")
    config.validate()


def test_stt_result_segments_default_empty() -> None:
    result = STTResult(transcript_text="hello", provider="test", mode="api")
    assert result.segments == []
    assert result.language is None


def test_stt_result_diarized_markdown_formatting() -> None:
    segments = [
        DiarizedSegment(speaker="Speaker 1", start_time=0.0, end_time=5.0, text="Hello there."),
        DiarizedSegment(speaker="Speaker 2", start_time=5.5, end_time=10.0, text="Hi back!"),
        DiarizedSegment(speaker="Speaker 1", start_time=10.5, end_time=15.0, text="How are you?"),
    ]
    result = STTResult(
        transcript_text="plaintext fallback",
        provider="test",
        mode="api",
        language="en",
        segments=segments,
    )
    markdown = result.to_diarized_markdown()
    assert "**Speaker 1**" in markdown
    assert "**Speaker 2**" in markdown
    assert "[00:00 - 00:05] Hello there." in markdown
    assert "[00:05 - 00:10] Hi back!" in markdown
    assert "[00:10 - 00:15] How are you?" in markdown


def test_stt_result_plain_text_joins_segments_horizontally() -> None:
    segments = [
        DiarizedSegment(speaker="Speaker 1", start_time=0.0, end_time=5.0, text="Hello there."),
        DiarizedSegment(speaker="Speaker 2", start_time=5.5, end_time=10.0, text="Hi back!"),
        DiarizedSegment(speaker="Speaker 1", start_time=10.5, end_time=15.0, text="How are you?"),
    ]
    result = STTResult(
        transcript_text="plaintext fallback",
        provider="test",
        mode="api",
        language="en",
        segments=segments,
    )

    assert result.to_plain_text() == "Hello there. Hi back! How are you?"
