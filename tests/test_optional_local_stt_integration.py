from __future__ import annotations

import os
from pathlib import Path

import pytest

from lecture_auto.local_runtime import LocalRuntimeManager


pytestmark = pytest.mark.skipif(
    os.environ.get("LECTURE_AUTO_RUN_LARGE_STT_INTEGRATION") != "1",
    reason=(
        "Requires an explicitly provisioned local model/GPU runtime and "
        "LECTURE_AUTO_STT_INTEGRATION_AUDIO."
    ),
)


def test_optional_large_model_or_gpu_transcription() -> None:
    audio = Path(os.environ["LECTURE_AUTO_STT_INTEGRATION_AUDIO"]).expanduser().resolve()
    model = os.environ.get("LECTURE_AUTO_STT_INTEGRATION_MODEL", "large-v3")
    device = os.environ.get("LECTURE_AUTO_STT_INTEGRATION_DEVICE", "cuda")
    compute_type = os.environ.get(
        "LECTURE_AUTO_STT_INTEGRATION_COMPUTE_TYPE",
        "float16",
    )
    result = LocalRuntimeManager().run_feature(
        "whisper",
        {
            "action": "whisper",
            "audio_path": str(audio),
            "model": model,
            "language": "ko",
            "device": device,
            "compute_type": compute_type,
            "batch_size": 1,
            "beam_size": 5,
            "vad_filter": True,
            "quality_retry_enabled": False,
        },
        timeout=None,
    )

    assert result["segments"]
    assert result["metadata"]["model"] == model
    assert result["metadata"]["device"] == device
