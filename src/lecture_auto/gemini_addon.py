from __future__ import annotations

from dataclasses import asdict
from typing import Any

from lecture_auto.llm_config import LLMConfig
from lecture_auto.local_runtime import LocalRuntimeManager


class GeminiAddonAdapter:
    """Runs Gemini work in the separately installed managed Python runtime."""

    def __init__(self, config: LLMConfig, runtime_manager: LocalRuntimeManager) -> None:
        self.config = config
        self.runtime_manager = runtime_manager

    def _run(self, action: str, **payload: Any) -> str:
        result = self.runtime_manager.run_feature(
            "gemini",
            {
                "action": action,
                "config": asdict(self.config),
                **payload,
            },
            timeout=None,
        )
        return str(result.get("text") or "")

    def refine_transcript(
        self,
        raw_text: str,
        context_topic: str | None = None,
        evidence: dict[str, object] | None = None,
    ) -> str:
        return self._run(
            "gemini_refine_transcript",
            raw_text=raw_text,
            context_topic=context_topic,
            evidence=evidence,
        )

    def generate_notes(
        self,
        transcript: str,
        template: str,
        context_topic: str | None = None,
        material_path: str | None = None,
    ) -> str:
        return self._run(
            "gemini_generate_notes",
            transcript=transcript,
            template=template,
            context_topic=context_topic,
            material_path=material_path,
        )
