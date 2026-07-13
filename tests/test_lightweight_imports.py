from __future__ import annotations

import os
import subprocess
import sys


def test_gui_import_does_not_require_local_ai_packages() -> None:
    code = r'''
import builtins
blocked = {"torch", "torchaudio", "faster_whisper", "ctranslate2", "df", "onnxruntime", "google"}
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split(".", 1)[0] in blocked:
        raise AssertionError(f"base app imported local AI package: {name}")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import lecture_auto.gui.app
print("ok")
'''
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"

    completed = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, env=env)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"
