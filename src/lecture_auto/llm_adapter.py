from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from lecture_auto.llm_config import LLMConfig, normalize_gemini_model_name

logger = logging.getLogger(__name__)

STRUCTURED_NOTE_SCHEMA_KEYS = (
    "topic_overview",
    "core_concepts",
    "detailed_explanations",
    "examples_mentioned",
    "questions_to_review",
    "exam_related_mentions",
)

STRUCTURED_NOTE_SCHEMA_DESCRIPTION = (
    '{"note_title":"...",'
    '"topic_overview":["..."],'
    '"core_concepts":["..."],'
    '"detailed_explanations":[{"title":"...","bullets":["..."]}],'
    '"examples_mentioned":["..."],'
    '"questions_to_review":["..."],'
    '"exam_related_mentions":["..."]}'
)

STRUCTURED_NOTE_TITLE_INSTRUCTION = (
    "Return one concise, content-specific title that identifies this lecture's central subject. "
    "Use the requested output language, preserve essential proper nouns or technical terms, "
    "and do not use generic titles such as 'Structured Lecture Notes' or 'Lecture Notes'."
)

STRUCTURED_NOTE_SECTION_INSTRUCTIONS = {
    "topic_overview": (
        "Return 3-5 bullets capturing lecture scope, main arc, and why the lecture matters. "
        "Each bullet should be specific to this lecture, not a generic course summary."
    ),
    "core_concepts": (
        "Return 6-12 bullets defining key terms, concepts, formulas, named methods, and relationships "
        "needed to understand the lecture."
    ),
    "detailed_explanations": (
        "Return 2-6 subtopics. Each subtopic needs a meaningful title and 4-8 bullets covering reasoning, "
        "mechanisms, steps, formulas, tradeoffs, caveats, speaker emphasis, and important distinctions. "
        "Bullets should be self-contained enough to study from without the transcript."
    ),
    "examples_mentioned": (
        "Return only examples explicitly mentioned in the transcript. If none, return ['Not mentioned.']."
    ),
    "questions_to_review": (
        "Return 4-8 core questions. If a student answers and explores these questions well, "
        "they should be able to reconstruct the lecture's main content, logic, and implications. "
        "Cover central concepts, causal relationships, mechanisms, assumptions, examples, contrasts, "
        "and why ideas matter. Avoid trivia, narrow recall, and generic questions."
    ),
    "exam_related_mentions": (
        "Return only explicit grading, exam, homework, assignment, or assessment cues. "
        "If none, return ['Not mentioned.']."
    ),
}


def _format_structured_note_section_requirements() -> str:
    return " ".join(
        f"{section_key}: {instruction}"
        for section_key, instruction in STRUCTURED_NOTE_SECTION_INSTRUCTIONS.items()
    )


def _build_transcript_refinement_system_instruction(
    *,
    context_topic: str | None,
    language: str | None,
) -> str:
    topic_prompt = f"The lecture topic or subject is '{context_topic}'. " if context_topic else ""
    lang_prompt = (
        f"Write the refined transcript in {language}, while preserving proper nouns, "
        "technical terms, equations, code, and quoted phrases as spoken. "
        if language
        else ""
    )
    return (
        f"You are a precise lecture transcript editor. {topic_prompt}"
        "Convert the raw ASR transcript into a clean, readable transcript, not a summary. "
        "Preserve the speaker's meaning, order of ideas, examples, terminology, numbers, formulas, and named entities. "
        "Fix transcription mistakes, including phonetically plausible word substitutions and awkward wording caused by ASR, "
        "when the lecture topic and surrounding sentences make the intended wording clear. "
        "Also fix spacing, punctuation, capitalization, sentence boundaries, and paragraph breaks. "
        "Remove meaningless filler, duplicated starts, and accidental repetitions only when they do not change the lecture content. "
        "Keep uncertainty, emphasis, questions, and instructor cues when they affect meaning. "
        "Use neighboring sentences and alternative ASR candidates as correction evidence. Lecture materials and glossary terms "
        "may validate a contextually supported spelling, but their presence alone does not prove that a word was spoken. "
        "Low ASR confidence alone is not a reason to leave clearly corrupted wording unchanged. "
        "Do not invent omitted sentences, facts, explanations, headings, bullets, numbers, formulas, named entities, timestamps, "
        "speaker labels, or commentary. Correct numbers, formulas, and named entities only when the source and context strongly support them. "
        "Only when multiple plausible readings remain after using the available context, preserve the span as '[불명확 mm:ss]' "
        "using its evidence timestamp. Without a timestamp, keep the closest original wording instead of guessing. "
        f"{lang_prompt}"
        "Output only the refined transcript text."
    )


def _build_transcript_refinement_prompt(
    chunk: str,
    *,
    evidence: dict[str, object] | None = None,
) -> str:
    from lecture_auto.stt_refinement import format_refinement_evidence

    return (
        "Refine this transcript chunk according to the system instructions. "
        "Return only the refined transcript chunk.\n\n"
        "Transcript chunk:\n"
        "<<<\n"
        f"{chunk}\n"
        ">>>"
        f"{format_refinement_evidence(evidence)}"
    )


def _build_structured_notes_json_system_instruction(
    *,
    context_topic: str | None,
    language: str | None,
    material_note: str = "",
    template_note: str = "",
) -> str:
    topic_prompt = f"Lecture topic: {context_topic}. " if context_topic else ""
    lang_prompt = f"Write all JSON string values in {language}. " if language else ""
    return (
        "You extract structured lecture-note data from transcripts. "
        f"{topic_prompt}"
        f"{lang_prompt}"
        "Return valid JSON only. No markdown. No code fence. No explanation. "
        "If a string contains a literal backslash, escape it as a double backslash. "
        "Use transcript evidence only; do not invent facts. "
        "Preserve proper nouns, technical terms, equations, code, and quoted phrases from the transcript. "
        "Prefer dense study notes over broad summaries: capture definitions, mechanisms, assumptions, dependencies, "
        "formulas, code behavior, examples, caveats, contrasts, misconceptions, and instructor emphasis when present. "
        f"Schema exactly: {STRUCTURED_NOTE_SCHEMA_DESCRIPTION}. "
        f"note_title: {STRUCTURED_NOTE_TITLE_INSTRUCTION} "
        f"Section requirements: {_format_structured_note_section_requirements()} "
        "topic_overview: lecture scope and main arc. "
        "core_concepts: key terms, definitions, relationships. "
        "detailed_explanations: main mechanisms, reasoning, steps, formulas, tradeoffs, caveats. "
        "examples_mentioned: examples explicitly stated. If none, use ['Not mentioned.']. "
        "questions_to_review: 4-8 core questions that let a student reconstruct lecture content, logic, and implications if answered well. "
        "Questions must cover central concepts, causal relationships, mechanisms, assumptions, examples, contrasts, and why ideas matter. "
        "Avoid trivia, narrow recall, and generic questions. "
        "exam_related_mentions: explicit grading, test, homework, assessment cues only. If none, use ['Not mentioned.']. "
        "All bullet arrays must contain strings. detailed_explanations must be an array of objects with title and bullets. "
        "Detailed explanation titles must be meaningful, never placeholders like 'Sub Topic 1'. "
        "Do not copy placeholder text from templates. "
        f"{template_note}"
        f"{material_note}"
    )


def _build_template_note(template: str) -> str:
    template = (template or "").strip()
    if not template:
        return ""
    headings = [
        line.strip()
        for line in template.splitlines()
        if line.lstrip().startswith("#")
    ]
    if not headings:
        return ""
    heading_text = "; ".join(headings[:12])
    return (
        " Final Markdown template headings for organization: "
        f"{heading_text}. Use these as layout guidance only; still return the JSON schema exactly."
    )


def _build_structured_notes_json_prompt(*, transcript: str) -> str:
    return (
        "Generate complete structured lecture-note JSON for this transcript. "
        "Return every schema key exactly once. Return JSON only.\n\n"
        f"JSON shape: {STRUCTURED_NOTE_SCHEMA_DESCRIPTION}\n\n"
        "Transcript:\n"
        "<<<\n"
        f"{transcript}\n"
        ">>>"
    )


def _build_structured_notes_chunk_prompt(
    *,
    transcript: str,
    chunk_index: int,
    chunk_count: int,
) -> str:
    return (
        "Extract candidate structured lecture-note JSON from this transcript chunk. "
        "Use only evidence in this chunk. Preserve order, terminology, formulas, examples, and instructor cues. "
        "Sparse sections may be concise, but keep concrete details for later merging. "
        "Return every schema key exactly once. Return JSON only.\n\n"
        f"Chunk: {chunk_index} of {chunk_count}\n"
        f"JSON shape: {STRUCTURED_NOTE_SCHEMA_DESCRIPTION}\n\n"
        "Transcript chunk:\n"
        "<<<\n"
        f"{transcript}\n"
        ">>>"
    )


def _build_structured_notes_merge_prompt(*, chunk_notes: list[dict[str, Any]]) -> str:
    return (
        "Merge these chunk-level lecture-note JSON objects into one complete study-note JSON object. "
        "Deduplicate repeated ideas, preserve lecture order, keep important details, and synthesize related points. "
        "Do not invent facts beyond the chunk notes. "
        "Return every schema key exactly once. Return JSON only.\n\n"
        f"JSON shape: {STRUCTURED_NOTE_SCHEMA_DESCRIPTION}\n\n"
        "Chunk notes:\n"
        f"{json.dumps(chunk_notes, ensure_ascii=False)}"
    )


def _structured_note_section_schema(section_key: str) -> str:
    if section_key == "detailed_explanations":
        return '{"detailed_explanations":[{"title":"...","bullets":["..."]}]}'
    if section_key == "topic_overview":
        return '{"note_title":"...","topic_overview":["..."]}'
    return f'{{"{section_key}":["..."]}}'


def _build_structured_note_section_prompt(*, transcript: str, section_key: str) -> str:
    schema = _structured_note_section_schema(section_key)
    title_instruction = (
        f"Title instruction: {STRUCTURED_NOTE_TITLE_INSTRUCTION}\n"
        if section_key == "topic_overview"
        else ""
    )

    return (
        f"Generate only this section: {section_key}.\n"
        f"{title_instruction}"
        f"Instruction: {STRUCTURED_NOTE_SECTION_INSTRUCTIONS[section_key]}\n"
        f"Return JSON exactly matching this shape: {schema}\n\n"
        "Transcript:\n"
        "<<<\n"
        f"{transcript}\n"
        ">>>"
    )


def _build_structured_notes_repair_prompt(
    *,
    transcript: str,
    previous_json: dict[str, Any],
    issues: list[str],
) -> str:
    return (
        "Repair this JSON so it satisfies the schema and fixes all issues. "
        "Return valid JSON only.\n\n"
        f"Issues:\n{json.dumps(issues, ensure_ascii=False)}\n\n"
        f"Previous JSON:\n{json.dumps(previous_json, ensure_ascii=False)}\n\n"
        "Transcript evidence:\n"
        "<<<\n"
        f"{transcript}\n"
        ">>>"
    )


def _build_json_syntax_repair_prompt(
    *,
    invalid_json: str,
    expected_schema: str,
    parser_error: str,
) -> str:
    return (
        "The previous response was intended to be JSON but is syntactically invalid. "
        "Repair JSON syntax only, preserve all original content, and return valid JSON only. "
        "Do not add markdown, code fences, or explanations.\n\n"
        f"Required JSON shape: {expected_schema}\n"
        f"Parser error: {parser_error}\n\n"
        f"Invalid response as a JSON string:\n{json.dumps(invalid_json, ensure_ascii=False)}"
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if not stripped:
        raise ValueError("empty model response")

    parsed = _load_json_object_candidate(stripped)
    if parsed is None:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            json.loads(stripped)
        parsed = _load_json_object_candidate(stripped[start : end + 1])
        if parsed is None:
            json.loads(stripped[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("model response JSON must be an object")
    return parsed


def _load_json_object_candidate(candidate: str) -> Any:
    latex_safe_candidate = _escape_latex_json_backslashes(candidate)
    for source in (
        latex_safe_candidate,
        candidate,
        _escape_invalid_json_backslashes(latex_safe_candidate),
        _escape_invalid_json_backslashes(candidate),
    ):
        try:
            return json.loads(source)
        except json.JSONDecodeError:
            continue
    return None


_LATEX_JSON_COMMAND_PREFIXES = (
    "rightarrow",
    "leftarrow",
    "leftrightarrow",
    "epsilon",
    "partial",
    "approx",
    "forall",
    "exists",
    "lambda",
    "nabla",
    "theta",
    "alpha",
    "gamma",
    "delta",
    "omega",
    "sigma",
    "times",
    "sqrt",
    "frac",
    "beta",
    "cdot",
    "leq",
    "geq",
    "neq",
    "phi",
    "sum",
    "int",
    "log",
    "sin",
    "cos",
    "tan",
    "exp",
    "min",
    "max",
    "argmin",
    "argmax",
    "mathbb",
    "mathcal",
    "text",
    "vec",
    "hat",
    "bar",
    "tilde",
    "dot",
    "infty",
    "subset",
    "supset",
    "cup",
    "cap",
    "emptyset",
    "land",
    "lor",
    "neg",
    "pm",
    "mp",
    "div",
    "to",
    "in",
)


def _escape_latex_json_backslashes(candidate: str) -> str:
    """Protect common LaTeX commands before JSON parsing consumes them as escapes."""
    result: list[str] = []
    in_string = False
    i = 0

    while i < len(candidate):
        char = candidate[i]
        if not in_string:
            result.append(char)
            if char == '"':
                in_string = True
            i += 1
            continue

        if char == '"':
            result.append(char)
            in_string = False
            i += 1
            continue

        if char == "\\":
            if _starts_latex_command(candidate, i + 1):
                result.append("\\\\")
                i += 1
                continue

            result.append(char)
            if i + 1 < len(candidate):
                result.append(candidate[i + 1])
                i += 2
            else:
                i += 1
            continue

        result.append(char)
        i += 1

    return "".join(result)


def _starts_latex_command(candidate: str, start_index: int) -> bool:
    remaining = candidate[start_index:]
    return any(
        remaining.startswith(command)
        for command in _LATEX_JSON_COMMAND_PREFIXES
    )


def _escape_invalid_json_backslashes(candidate: str) -> str:
    return re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", candidate)


def _iter_text_chunks(text: str, chunk_size: int) -> list[str]:
    chunks: list[str] = []
    start_idx = 0
    text_length = len(text)
    while start_idx < text_length:
        end_idx = min(start_idx + chunk_size, text_length)

        if end_idx < text_length:
            last_break = max(
                text.rfind("\n\n", start_idx, end_idx),
                text.rfind("\n", start_idx, end_idx),
                text.rfind(" ", start_idx, end_idx),
            )
            if last_break > start_idx + chunk_size // 2:
                end_idx = last_break

        chunk = text[start_idx:end_idx].strip()
        if chunk:
            chunks.append(chunk)

        start_idx = end_idx
        while start_idx < text_length and text[start_idx].isspace():
            start_idx += 1

    return chunks


def _clean_note_item(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    while text.startswith(("-", "*", "•")):
        text = text[1:].strip()
    return text or None


def _normalize_note_list(value: Any) -> list[str]:
    if isinstance(value, str):
        item = _clean_note_item(value)
        return [item] if item else []
    if isinstance(value, list):
        items = [_clean_note_item(item) for item in value]
        return [item for item in items if item]
    return []


def _normalize_detailed_explanations(value: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if isinstance(value, dict):
        iterable = [
            {"title": title, "bullets": bullets}
            for title, bullets in value.items()
        ]
    elif isinstance(value, list):
        iterable = value
    elif isinstance(value, str):
        iterable = [{"title": "Detailed Explanation", "bullets": [value]}]
    else:
        iterable = []

    for index, item in enumerate(iterable, start=1):
        if isinstance(item, dict):
            title = _clean_note_item(item.get("title")) or f"Detailed Topic {index}"
            bullets = _normalize_note_list(item.get("bullets"))
            if not bullets:
                bullets = _normalize_note_list(item.get("content"))
        else:
            title = f"Detailed Topic {index}"
            bullets = _normalize_note_list(item)

        if bullets:
            normalized.append({"title": title, "bullets": bullets})

    return normalized


def _normalize_note_title(value: Any, topic_overview: list[str]) -> str:
    if isinstance(value, list):
        value = value[0] if value else None

    title = _clean_note_item(value)
    if title:
        title = re.sub(r"\s+", " ", title).lstrip("#").strip()

    generic_titles = {
        "structured lecture notes",
        "structured notes",
        "lecture notes",
        "강의 노트",
        "구조화 강의 노트",
    }
    if not title or title.casefold() in generic_titles:
        title = topic_overview[0] if topic_overview else "Lecture Notes"

    if len(title) > 100:
        shortened = title[:97].rsplit(" ", 1)[0].rstrip(".,;:")
        title = f"{shortened or title[:97]}..."
    return title


def _normalize_structured_note_data(raw_data: dict[str, Any]) -> dict[str, Any]:
    topic_overview = _normalize_note_list(raw_data.get("topic_overview"))
    return {
        "note_title": _normalize_note_title(
            raw_data.get("note_title"),
            topic_overview,
        ),
        "topic_overview": topic_overview,
        "core_concepts": _normalize_note_list(raw_data.get("core_concepts")),
        "detailed_explanations": _normalize_detailed_explanations(
            raw_data.get("detailed_explanations")
        ),
        "examples_mentioned": _normalize_note_list(raw_data.get("examples_mentioned")),
        "questions_to_review": _normalize_note_list(raw_data.get("questions_to_review")),
        "exam_related_mentions": _normalize_note_list(raw_data.get("exam_related_mentions")),
    }


def _extract_section_value(parsed: dict[str, Any], section_key: str) -> Any:
    if section_key in parsed:
        return parsed[section_key]
    for fallback_key in ("items", "bullets", "questions", "subtopics", "content"):
        if fallback_key in parsed:
            return parsed[fallback_key]
    return None


def _validate_structured_note_data(note_data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in STRUCTURED_NOTE_SCHEMA_KEYS:
        value = note_data.get(key)
        if key == "detailed_explanations":
            if not value:
                issues.append("detailed_explanations must contain at least one subtopic with bullets")
            continue
        if not value:
            issues.append(f"{key} must contain at least one bullet")

    core_concepts = note_data.get("core_concepts") or []
    if len(core_concepts) < 6:
        issues.append("core_concepts must contain 6-12 concrete study bullets")
    if len(core_concepts) > 12:
        issues.append("core_concepts must contain no more than 12 bullets")

    questions = note_data.get("questions_to_review") or []
    if len([q for q in questions if q and q != "Not mentioned."]) < 4:
        issues.append("questions_to_review must contain 4-8 core reconstruction questions")
    if len(questions) > 8:
        issues.append("questions_to_review must contain no more than 8 questions")

    detailed = note_data.get("detailed_explanations") or []
    if detailed and len(detailed) < 2:
        issues.append("detailed_explanations must contain 2-6 meaningful subtopics")
    if len(detailed) > 6:
        issues.append("detailed_explanations must contain no more than 6 subtopics")
    for item in detailed:
        title = str(item.get("title", "")).strip().lower()
        if (
            title.startswith("sub topic")
            or title.startswith("subtopic")
            or title in {"detailed explanation", "topic", "main topic"}
        ):
            issues.append("detailed_explanations titles must be meaningful, not placeholder subtopic names")
            break
        bullets = _normalize_note_list(item.get("bullets"))
        if len(bullets) < 4:
            issues.append("each detailed_explanations subtopic must contain 4-8 study bullets")
            break
        if len(bullets) > 8:
            issues.append("each detailed_explanations subtopic must contain no more than 8 bullets")
            break
    return issues


def _ensure_note_items(items: list[str], fallback: str = "Not mentioned.") -> list[str]:
    return items if items else [fallback]


def _render_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in _ensure_note_items(items))


def _render_structured_notes_markdown(note_data: dict[str, Any]) -> str:
    note_title = _normalize_note_title(
        note_data.get("note_title"),
        _normalize_note_list(note_data.get("topic_overview")),
    )
    detailed = note_data.get("detailed_explanations") or []
    if not detailed:
        detailed = [{"title": "Detailed Explanation", "bullets": ["Not mentioned."]}]

    detailed_lines = ["## Detailed Explanations"]
    for item in detailed:
        detail_title = _clean_note_item(item.get("title")) or "Detailed Explanation"
        bullets = _normalize_note_list(item.get("bullets"))
        detailed_lines.extend(["", f"### {detail_title}", _render_bullets(bullets)])

    return "\n\n".join(
        [
            f"# {note_title}",
            "## Topic Overview\n" + _render_bullets(note_data.get("topic_overview") or []),
            "## Core Concepts\n" + _render_bullets(note_data.get("core_concepts") or []),
            "\n".join(detailed_lines),
            "## Examples Mentioned\n" + _render_bullets(note_data.get("examples_mentioned") or []),
            "## Questions to Review\n" + _render_bullets(note_data.get("questions_to_review") or []),
            "## Exam related mentions\n" + _render_bullets(note_data.get("exam_related_mentions") or []),
        ]
    )


def _apply_thinking_config(
    config_dict: dict,
    types: object | None,
    model_name: str,
    thinking_level: str,
) -> None:
    if not types:
        return

    normalized_model = normalize_gemini_model_name(model_name)
    if normalized_model.startswith("gemma-4-") and thinking_level != "high":
        return

    config_dict["thinking_config"] = types.ThinkingConfig(  # type: ignore[attr-defined]
        thinking_level=thinking_level
    )


class LLMConfigError(Exception):
    """Configuration missing or invalid."""

class LLMProviderAuthError(Exception):
    """LLM provider authentication failed."""

class LLMTransientNetworkError(Exception):
    """Network connection or timeout error."""


class LLMProviderAdapter(Protocol):
    """Interface for LLM-based transcript refinement."""

    def refine_transcript(
        self,
        raw_text: str,
        context_topic: str | None = None,
        evidence: dict[str, object] | None = None,
    ) -> str:
        """Refines transcript by fixing typos, spacing, and wording, while preserving meaning."""
        ...

    def generate_notes(
        self,
        transcript: str,
        template: str,
        context_topic: str | None = None, material_path: str | None = None,
    ) -> str:
        """Generates notes from transcript text and a markdown template."""
        ...


class GeminiLLMAdapter:
    """Implementation of Gemini API for transcript refinement."""

    def __init__(
        self,
        config: LLMConfig,
        *,
        runtime_manager: Any | None = None,
        use_addon: bool | None = None,
    ) -> None:
        if not config.api_key or not config.api_key.strip():
            raise LLMConfigError("Google API key is required.")
        self.config = config
        self._addon = None

        if use_addon is None:
            use_addon = "__compiled__" in globals()
        if use_addon:
            from lecture_auto.gemini_addon import GeminiAddonAdapter
            from lecture_auto.local_runtime import LocalRuntimeManager

            self._addon = GeminiAddonAdapter(
                config,
                runtime_manager or LocalRuntimeManager(),
            )
            self.client = None
            return

        try:
            from google import genai
        except ImportError as exc:
            raise LLMConfigError(
                "google-genai is not installed. Run: pip install google-genai"
            ) from exc

        self.client = genai.Client(api_key=self.config.api_key)

    def _call_addon(self, method: str, *args: Any, **kwargs: Any) -> str:
        if self._addon is None:
            raise RuntimeError("Gemini add-on adapter is not active.")
        try:
            return str(getattr(self._addon, method)(*args, **kwargs))
        except Exception as exc:
            from lecture_auto.local_runtime import LocalRuntimeError, LocalRuntimeMissingError

            if isinstance(exc, LocalRuntimeMissingError):
                raise LLMConfigError(
                    "Gemini add-on is not installed. Open Settings > Add-ons and install Gemini."
                ) from exc
            if isinstance(exc, LocalRuntimeError):
                raise LLMTransientNetworkError(f"Gemini add-on failed: {exc}") from exc
            raise

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        """Normalizes common Gemini model aliases to API-accepted IDs."""
        return normalize_gemini_model_name(model_name)

    def refine_transcript(
        self,
        raw_text: str,
        context_topic: str | None = None,
        evidence: dict[str, object] | None = None,
    ) -> str:
        """Refines the transcript in chunks using the Gemini model."""
        if not raw_text or not raw_text.strip():
            return raw_text
        if self._addon is not None:
            return self._call_addon(
                "refine_transcript",
                raw_text,
                context_topic=context_topic,
                evidence=evidence,
            )

        try:
            from google.api_core.exceptions import PermissionDenied, DeadlineExceeded  # type: ignore
        except ImportError:
            class PermissionDenied(Exception):  # type: ignore[no-redef]
                pass

            class DeadlineExceeded(Exception):  # type: ignore[no-redef]
                pass

        try:
            from google.genai import types  # type: ignore
        except ImportError:
            types = None  # type: ignore

        system_instructions = _build_transcript_refinement_system_instruction(
            context_topic=context_topic,
            language=self.config.language,
        )

        chunk_size = self.config.resolve_chunk_size(len(raw_text))
        from lecture_auto.stt_refinement import segment_chunks

        chunks = segment_chunks(
            raw_text,
            chunk_size=chunk_size,
            overlap_characters=0,
        )
        refined_chunks = []

        try:
            for chunk in chunks:
                prompt = _build_transcript_refinement_prompt(
                    chunk,
                    evidence=evidence,
                )

                config_dict: dict = {"system_instruction": system_instructions}
                _apply_thinking_config(
                    config_dict,
                    types,
                    self.config.model_name,
                    self.config.thinking_level,
                )

                response = self.client.models.generate_content(
                    model=self._normalize_model_name(self.config.model_name),
                    contents=prompt,
                    config=config_dict,  # type: ignore
                )
                text = (getattr(response, "text", "") or "").strip()
                refined_chunks.append(text)
                
            return "\n".join(refined_chunks)

        except PermissionDenied as exc:
            raise LLMProviderAuthError(f"Gemini authentication failed: {exc}") from exc
        except DeadlineExceeded as exc:
            raise LLMTransientNetworkError(f"Gemini network/timeout error: {exc}") from exc
        except Exception as exc:
            error_msg = str(exc).lower()
            if "404" in error_msg or "model" in error_msg and "not found" in error_msg:
                raise LLMConfigError(f"Gemini model configuration failed: {exc}") from exc
            if "api_key_invalid" in error_msg or "unauthorized" in error_msg or "401" in error_msg or "403" in error_msg:
                raise LLMProviderAuthError(f"Gemini authentication failed: {exc}") from exc
            if "timeout" in error_msg or "connection" in error_msg or "503" in error_msg or "504" in error_msg:
                raise LLMTransientNetworkError(f"Gemini network error: {exc}") from exc
            
            raise LLMTransientNetworkError(f"Gemini LLM request failed: {exc}") from exc

    def generate_notes(
        self,
        transcript: str,
        template: str,
        context_topic: str | None = None, material_path: str | None = None,
    ) -> str:
        """Generates structured notes through provider-neutral JSON data."""
        if not transcript or not transcript.strip():
            return transcript
        if self._addon is not None:
            return self._call_addon(
                "generate_notes",
                transcript,
                template,
                context_topic=context_topic,
                material_path=material_path,
            )

        try:
            from google.api_core.exceptions import PermissionDenied, DeadlineExceeded  # type: ignore
        except ImportError:
            class PermissionDenied(Exception):  # type: ignore[no-redef]
                pass

            class DeadlineExceeded(Exception):  # type: ignore[no-redef]
                pass

        try:
            from google.genai import types  # type: ignore
        except ImportError:
            types = None  # type: ignore

        try:
            template_note = _build_template_note(template)
            uploaded_file = None
            material_note = ""

            if material_path:
                import os
                if os.path.exists(material_path):
                    upload_kwargs: dict = {"file": material_path}
                    if types:
                        upload_kwargs["config"] = types.UploadFileConfig(
                            mime_type="application/pdf"
                        )
                    uploaded_file = self.client.files.upload(**upload_kwargs)
                    material_note = (
                        " A lecture material PDF has been provided as supporting context. "
                        "Use it to verify terminology, structure, formulas, and examples, while prioritizing the transcript."
                    )

            system_instructions = _build_structured_notes_json_system_instruction(
                context_topic=context_topic,
                language=self.config.language,
                material_note=material_note,
                template_note=template_note,
            )

            config_dict: dict = {
                "system_instruction": system_instructions,
                "response_mime_type": "application/json",
            }
            _apply_thinking_config(
                config_dict,
                types,
                self.config.model_name,
                self.config.thinking_level,
            )

            try:
                note_chunk_size = self.config.resolve_chunk_size(len(transcript))
                chunks = _iter_text_chunks(transcript, note_chunk_size)
                chunk_notes: list[dict[str, Any]] = []

                if len(chunks) > 1:
                    for index, chunk in enumerate(chunks, start=1):
                        chunk_contents: list = [
                            _build_structured_notes_chunk_prompt(
                                transcript=chunk,
                                chunk_index=index,
                                chunk_count=len(chunks),
                            )
                        ]
                        if uploaded_file:
                            chunk_contents.append(uploaded_file)
                        chunk_response = self.client.models.generate_content(
                            model=self._normalize_model_name(self.config.model_name),
                            contents=chunk_contents,
                            config=config_dict,  # type: ignore
                        )
                        chunk_text = (getattr(chunk_response, "text", "") or "").strip()
                        chunk_notes.append(
                            _normalize_structured_note_data(_extract_json_object(chunk_text))
                        )

                    merge_contents: list = [
                        _build_structured_notes_merge_prompt(chunk_notes=chunk_notes)
                    ]
                    if uploaded_file:
                        merge_contents.append(uploaded_file)
                    response = self.client.models.generate_content(
                        model=self._normalize_model_name(self.config.model_name),
                        contents=merge_contents,
                        config=config_dict,  # type: ignore
                    )
                else:
                    contents: list = [_build_structured_notes_json_prompt(transcript=transcript)]
                    if uploaded_file:
                        contents.append(uploaded_file)
                    response = self.client.models.generate_content(
                        model=self._normalize_model_name(self.config.model_name),
                        contents=contents,
                        config=config_dict,  # type: ignore
                    )

                raw_text = (getattr(response, "text", "") or "").strip()
                note_data = _normalize_structured_note_data(_extract_json_object(raw_text))
                issues = _validate_structured_note_data(note_data)

                if issues:
                    repair_evidence = (
                        json.dumps(chunk_notes, ensure_ascii=False)
                        if chunk_notes
                        else transcript
                    )
                    repair_contents: list = [
                        _build_structured_notes_repair_prompt(
                            transcript=repair_evidence,
                            previous_json=note_data,
                            issues=issues,
                        )
                    ]
                    if uploaded_file:
                        repair_contents.append(uploaded_file)
                    repair_response = self.client.models.generate_content(
                        model=self._normalize_model_name(self.config.model_name),
                        contents=repair_contents,
                        config=config_dict,  # type: ignore
                    )
                    repair_text = (getattr(repair_response, "text", "") or "").strip()
                    note_data = _normalize_structured_note_data(
                        _extract_json_object(repair_text)
                    )
            finally:
                if uploaded_file and hasattr(uploaded_file, "name") and uploaded_file.name:
                    try:
                        self.client.files.delete(name=uploaded_file.name)
                    except Exception:
                        pass # Best effort cleanup

            return _render_structured_notes_markdown(note_data)

        except PermissionDenied as exc:
            raise LLMProviderAuthError(f"Gemini authentication failed: {exc}") from exc
        except DeadlineExceeded as exc:
            raise LLMTransientNetworkError(f"Gemini network/timeout error: {exc}") from exc
        except Exception as exc:
            error_msg = str(exc).lower()
            if "404" in error_msg or "model" in error_msg and "not found" in error_msg:
                raise LLMConfigError(f"Gemini model configuration failed: {exc}") from exc
            if (
                "api_key_invalid" in error_msg
                or "unauthorized" in error_msg
                or "401" in error_msg
                or "403" in error_msg
            ):
                raise LLMProviderAuthError(f"Gemini authentication failed: {exc}") from exc
            if (
                "timeout" in error_msg
                or "connection" in error_msg
                or "503" in error_msg
                or "504" in error_msg
            ):
                raise LLMTransientNetworkError(f"Gemini network error: {exc}") from exc

            raise LLMTransientNetworkError(f"Gemini LLM request failed: {exc}") from exc


class OllamaLLMAdapter:
    """Implementation of Ollama API for transcript refinement using local models."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        
        # Check if ollama package is available
        try:
            import ollama
            client_type = getattr(ollama, "Client", None)
            self.ollama = client_type(host=config.ollama_base_url) if client_type else ollama
        except ImportError as exc:
            raise LLMConfigError(
                "ollama package is not installed. Run: pip install ollama"
            ) from exc

    def refine_transcript(
        self,
        raw_text: str,
        context_topic: str | None = None,
        evidence: dict[str, object] | None = None,
    ) -> str:
        """Refines the transcript in chunks using the Ollama model."""
        if not raw_text or not raw_text.strip():
            return raw_text

        system_instructions = _build_transcript_refinement_system_instruction(
            context_topic=context_topic,
            language=self.config.language,
        )

        chunk_size = self.config.resolve_chunk_size(len(raw_text))
        from lecture_auto.stt_refinement import segment_chunks

        chunks = segment_chunks(
            raw_text,
            chunk_size=chunk_size,
            overlap_characters=0,
        )
        refined_chunks = []

        try:
            for chunk in chunks:
                prompt = _build_transcript_refinement_prompt(
                    chunk,
                    evidence=evidence,
                )

                try:
                    response = self.ollama.chat(
                        model=self.config.model_name,
                        messages=[
                            {"role": "system", "content": system_instructions},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    text = response.get("message", {}).get("content", "").strip()
                    refined_chunks.append(text)
                except Exception as exc:
                    error_msg = str(exc).lower()
                    if "connection" in error_msg or "refused" in error_msg:
                        raise LLMTransientNetworkError(
                            f"Cannot connect to Ollama server at {self.config.ollama_base_url}. "
                            f"Make sure Ollama is running: {exc}"
                        ) from exc
                    if "not found" in error_msg or "model" in error_msg:
                        raise LLMConfigError(
                            f"Model '{self.config.model_name}' not found. "
                            f"Available models: {self._get_available_models()}"
                        ) from exc
                    raise LLMTransientNetworkError(f"Ollama request failed: {exc}") from exc
                
            return "\n".join(refined_chunks)

        except (LLMConfigError, LLMProviderAuthError, LLMTransientNetworkError):
            raise
        except Exception as exc:
            raise LLMTransientNetworkError(f"Ollama LLM request failed: {exc}") from exc

    def _chat_for_structured_json(
        self,
        *,
        system_instructions: str,
        prompt: str,
        expected_schema: str,
    ) -> dict[str, Any]:
        response = self.ollama.chat(
            model=self.config.model_name,
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": prompt},
            ],
            format="json",
        )
        raw_text = response.get("message", {}).get("content", "").strip()

        try:
            return _extract_json_object(raw_text)
        except (TypeError, ValueError) as parse_error:
            repair_response = self.ollama.chat(
                model=self.config.model_name,
                messages=[
                    {"role": "system", "content": system_instructions},
                    {
                        "role": "user",
                        "content": _build_json_syntax_repair_prompt(
                            invalid_json=raw_text,
                            expected_schema=expected_schema,
                            parser_error=str(parse_error),
                        ),
                    },
                ],
                format="json",
            )
            repaired_text = (
                repair_response.get("message", {}).get("content", "").strip()
            )
            try:
                return _extract_json_object(repaired_text)
            except (TypeError, ValueError) as repair_error:
                raise ValueError(
                    "Ollama returned invalid JSON after one syntax repair attempt: "
                    f"{repair_error}"
                ) from repair_error

    def generate_notes(
        self,
        transcript: str,
        template: str,
        context_topic: str | None = None, 
        material_path: str | None = None,
    ) -> str:
        """Generates lecture notes from transcript text through a JSON harness."""
        if not transcript or not transcript.strip():
            return transcript

        material_note = " (Note: PDF material attachment is not supported for Ollama.)" if material_path else ""
        template_note = _build_template_note(template)

        system_instructions = _build_structured_notes_json_system_instruction(
            context_topic=context_topic,
            language=self.config.language,
            material_note=material_note,
            template_note=template_note,
        )

        try:
            raw_note_data: dict[str, Any] = {}
            note_chunk_size = self.config.resolve_chunk_size(len(transcript))
            chunks = _iter_text_chunks(transcript, note_chunk_size)
            chunk_notes: list[dict[str, Any]] = []

            if len(chunks) > 1:
                for index, chunk in enumerate(chunks, start=1):
                    parsed_chunk = self._chat_for_structured_json(
                        system_instructions=system_instructions,
                        prompt=_build_structured_notes_chunk_prompt(
                            transcript=chunk,
                            chunk_index=index,
                            chunk_count=len(chunks),
                        ),
                        expected_schema=STRUCTURED_NOTE_SCHEMA_DESCRIPTION,
                    )
                    chunk_notes.append(
                        _normalize_structured_note_data(parsed_chunk)
                    )

                raw_note_data = self._chat_for_structured_json(
                    system_instructions=system_instructions,
                    prompt=_build_structured_notes_merge_prompt(
                        chunk_notes=chunk_notes
                    ),
                    expected_schema=STRUCTURED_NOTE_SCHEMA_DESCRIPTION,
                )
            else:
                for section_key in STRUCTURED_NOTE_SCHEMA_KEYS:
                    prompt = _build_structured_note_section_prompt(
                        transcript=transcript,
                        section_key=section_key,
                    )
                    expected_schema = _structured_note_section_schema(section_key)
                    parsed = self._chat_for_structured_json(
                        system_instructions=system_instructions,
                        prompt=prompt,
                        expected_schema=expected_schema,
                    )
                    if section_key == "topic_overview":
                        raw_note_data["note_title"] = parsed.get("note_title")
                    raw_note_data[section_key] = _extract_section_value(parsed, section_key)

            note_data = _normalize_structured_note_data(raw_note_data)
            issues = _validate_structured_note_data(note_data)

            if issues:
                repair_evidence = (
                    json.dumps(chunk_notes, ensure_ascii=False)
                    if chunk_notes
                    else transcript
                )
                repair_prompt = _build_structured_notes_repair_prompt(
                    transcript=repair_evidence,
                    previous_json=note_data,
                    issues=issues,
                )
                repaired_data = self._chat_for_structured_json(
                    system_instructions=system_instructions,
                    prompt=repair_prompt,
                    expected_schema=STRUCTURED_NOTE_SCHEMA_DESCRIPTION,
                )
                note_data = _normalize_structured_note_data(repaired_data)

            return _render_structured_notes_markdown(note_data)

        except Exception as exc:
            error_msg = str(exc).lower()
            if "connection" in error_msg or "refused" in error_msg:
                raise LLMTransientNetworkError(
                    f"Cannot connect to Ollama server at {self.config.ollama_base_url}. "
                    f"Make sure Ollama is running: {exc}"
                ) from exc
            if "not found" in error_msg or "model" in error_msg:
                raise LLMConfigError(
                    f"Model '{self.config.model_name}' not found. "
                    f"Available models: {self._get_available_models()}"
                ) from exc
            raise LLMTransientNetworkError(f"Ollama note generation harness failed: {exc}") from exc

    def _get_available_models(self) -> str:
        """Helper to list available Ollama models for error messages."""
        try:
            models_list = self.ollama.list()
            model_names = [m.get("name", "") for m in models_list.get("models", [])]
            return ", ".join(model_names) if model_names else "none"
        except Exception:
            return "unknown"
