from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from lecture_auto.audio_amplifier import (
    _DEEPFILTER_SITE_CUSTOMIZE,
    AudioAmplificationError,
    amplified_audio_input,
    deepfilter_audio_input,
)


def test_amplified_audio_input_gain_one_is_noop(tmp_path: Path) -> None:
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")

    with patch("lecture_auto.audio_amplifier.subprocess.run") as run_mock:
        with amplified_audio_input(audio_path=str(source), use_dynaudnorm=False) as audio_path:
            assert audio_path == str(source)

    run_mock.assert_not_called()


def test_amplified_audio_input_raises_when_ffmpeg_reports_success_without_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")

    with patch("lecture_auto.audio_amplifier.subprocess.run") as run_mock:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stderr = ""

        try:
            with amplified_audio_input(audio_path=str(source), use_dynaudnorm=True):
                pass
        except AudioAmplificationError as exc:
            assert "did not produce" in str(exc)
        else:
            raise AssertionError("Expected AudioAmplificationError to be raised")


def test_deepfilter_audio_input_yields_filtered_audio_output(tmp_path: Path) -> None:
    source = tmp_path / "sample.wav"
    source.write_bytes(b"source audio")

    def fake_run(command, **kwargs):
        if Path(command[0]).stem == "ffmpeg":
            Path(command[-1]).write_bytes(b"converted wav")
            return SimpleNamespace(returncode=0, stderr="")

        output_dir = Path(command[command.index("-o") + 1])
        assert output_dir.name == "output"
        assert command[-2:] == ["--log-level", "none"]
        filtered = output_dir / "sample_src_DeepFilterNet3.wav"
        filtered.write_bytes(b"filtered wav")
        return SimpleNamespace(returncode=0, stderr="")

    with patch("lecture_auto.audio_amplifier.subprocess.run", side_effect=fake_run):
        with deepfilter_audio_input(
            audio_path=str(source),
            deepfilter_bin="deepFilter",
        ) as audio_path:
            output_path = Path(audio_path)
            assert output_path.name == "sample_src_DeepFilterNet3.wav"
            assert output_path.read_bytes() == b"filtered wav"


def test_deepfilter_torchaudio_compat_shim_installs_info_without_soundfile(
    tmp_path: Path,
) -> None:
    (tmp_path / "sitecustomize.py").write_text(_DEEPFILTER_SITE_CUSTOMIZE)
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{tmp_path}:{env.get('PYTHONPATH', '')}".strip(":")

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            f"path = {str(tmp_path / 'probe.wav')!r}\n"
            "import torchaudio; import torchaudio.backend.common as common; "
            "import torch\n"
            "print(hasattr(torchaudio, 'info')); print(hasattr(torchaudio, 'load')); "
            "print(hasattr(torchaudio, 'save')); "
            "print(common.AudioMetaData(1, 2, 3).num_frames)\n"
            "torchaudio.save("
            "path, torch.tensor([[0, 32767, -32768]], dtype=torch.int16), 8000"
            ")\n"
            "audio, sample_rate = torchaudio.load(path)\n"
            "print(sample_rate); print(round(float(audio[0, 1]), 3)); "
            "print(round(float(audio[0, 2]), 3))",
        ],
        check=False,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "True",
        "True",
        "True",
        "2",
        "8000",
        "1.0",
        "-1.0",
    ]
