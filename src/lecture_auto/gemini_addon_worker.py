"""One-shot worker for the optional Gemini SDK add-on runtime."""
from __future__ import annotations

import os
import sys

_WORKER_DIR = os.path.normcase(os.path.abspath(os.path.dirname(__file__)))
if sys.path and os.path.normcase(os.path.abspath(sys.path[0])) == _WORKER_DIR:
    sys.path.pop(0)

import json
import traceback
from pathlib import Path
from typing import Any


def emit(event_type: str, **payload: Any) -> None:
    print(json.dumps({"type": event_type, **payload}, ensure_ascii=False), flush=True)


def _add_bundled_source_to_path() -> None:
    bundled = Path(__file__).resolve().parent / "addon_source"
    source_root = bundled if bundled.is_dir() else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(source_root))


def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    _add_bundled_source_to_path()
    from lecture_auto.llm_adapter import GeminiLLMAdapter
    from lecture_auto.llm_config import LLMConfig

    config = LLMConfig(**dict(request.get("config") or {}))
    adapter = GeminiLLMAdapter(config, use_addon=False)
    action = request.get("action")
    if action == "gemini_refine_transcript":
        text = adapter.refine_transcript(
            str(request.get("raw_text") or ""),
            context_topic=request.get("context_topic"),
            evidence=request.get("evidence"),
        )
    elif action == "gemini_generate_notes":
        text = adapter.generate_notes(
            str(request.get("transcript") or ""),
            str(request.get("template") or ""),
            context_topic=request.get("context_topic"),
            material_path=request.get("material_path"),
        )
    else:
        raise ValueError(f"Unknown Gemini worker action: {action}")
    return {"text": text}


def main() -> None:
    line = sys.stdin.readline()
    if not line:
        emit("error", code="EMPTY_REQUEST", message="Worker request was not provided.")
        raise SystemExit(2)
    try:
        emit("progress", stage="gemini", completed=0, total=1, message="Calling Gemini add-on")
        result = dispatch(json.loads(line))
        emit("progress", stage="complete", completed=1, total=1, message="Gemini add-on complete")
        emit("result", result=result)
    except BaseException as exc:
        emit(
            "error",
            code=type(exc).__name__,
            message=str(exc),
            traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:],
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
