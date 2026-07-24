import json
from pathlib import Path
from subprocess import CompletedProcess

from lecture_auto.audio_preflight import analyze_audio_for_stt


def test_audio_preflight_returns_conditional_recommendations(
    tmp_path: Path, monkeypatch
) -> None:
    audio = tmp_path / "lecture.mp3"
    audio.write_bytes(b"audio")
    probe_payload = {
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "mp3",
                "sample_rate": "44100",
                "channels": 2,
            }
        ],
        "format": {"duration": "100.0"},
    }
    responses = iter(
        [
            CompletedProcess([], 0, json.dumps(probe_payload), ""),
            CompletedProcess(
                [],
                0,
                "",
                "mean_volume: -33.0 dB\nmax_volume: -2.0 dB\n"
                "silence_duration: 12.5\n",
            ),
        ]
    )
    monkeypatch.setattr(
        "lecture_auto.audio_preflight.resolve_ffprobe_bin",
        lambda: "ffprobe",
    )
    monkeypatch.setattr(
        "lecture_auto.audio_preflight.resolve_ffmpeg_bin",
        lambda: "ffmpeg",
    )
    monkeypatch.setattr(
        "lecture_auto.audio_preflight.subprocess.run",
        lambda *_args, **_kwargs: next(responses),
    )

    result = analyze_audio_for_stt(audio)

    assert result.silence_ratio == 0.125
    assert result.low_loudness is True
    assert result.clipping_risk is False
    assert result.recommendations == (
        "enable_vad",
        "benchmark_loudness_normalization",
        "let_whisper_resample_or_cache_16khz_mono_only_for_reuse",
    )
