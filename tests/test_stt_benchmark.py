from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_local_stt.py"
SPEC = importlib.util.spec_from_file_location("benchmark_local_stt", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


def test_edit_distance_matches_known_examples() -> None:
    assert benchmark.edit_distance("", "") == 0
    assert benchmark.edit_distance("", "abc") == 3
    assert benchmark.edit_distance("kitten", "sitting") == 3
    assert benchmark.edit_distance("강의자동화", "강의 자동") == 2


def test_repetition_summary_detects_token_and_ngram_loops() -> None:
    summary = benchmark.repetition_summary(
        "정상 발화 가 나 다 가 나 다 반복 반복 반복 반복 반복".split()
    )

    assert summary["max_consecutive_token_run"] == 5
    assert summary["repeated_token_excess"] == 2
    assert summary["immediate_repeated_ngram_count"] >= 1
    assert 0 < summary["unique_word_ratio"] < 1


def test_normalization_is_korean_and_term_friendly() -> None:
    text = "OpenGL의 레스터라이제이션(Rasterization), 3-D!"

    assert benchmark.normalize_words(text) == [
        "opengl의",
        "레스터라이제이션",
        "rasterization",
        "3",
        "d",
    ]
    assert benchmark.normalize_characters(text) == (
        "opengl의레스터라이제이션rasterization3d"
    )


def test_discover_pairs_ignores_unpaired_audio(tmp_path: Path) -> None:
    (tmp_path / "test-graphics.mp3").write_bytes(b"audio")
    (tmp_path / "transcript-graphics.md").write_text("reference", encoding="utf-8")
    (tmp_path / "test-no-reference.wav").write_bytes(b"audio")

    pairs = benchmark.discover_pairs(tmp_path)

    assert [pair.name for pair in pairs] == ["graphics"]


def test_extended_metrics_cover_omission_terms_numbers_and_refine_safety() -> None:
    reference = "CUDA 모델은 batch 16에서 정확도 95%를 기록했다."
    hypothesis = "CUDA 모델은 정확도 95%를 기록했다."
    metrics = benchmark.evaluate_text(
        reference,
        hypothesis,
        glossary=["CUDA", "batch"],
    )
    audit = benchmark.audit_refinement(
        hypothesis,
        "CUDA 모델은 정확도 99%를 기록했다.",
    )

    assert metrics["omission_rate"] > 0
    assert metrics["term_recall"] == 0.5
    assert metrics["numeric_formula_recall"] == 0.5
    assert audit.inserted_numbers == ("99%",)
    assert audit.removed_numbers == ("95%",)


def test_benchmark_merges_retry_payloads_by_timestamp() -> None:
    primary = [
        {"start_time": 0, "end_time": 2, "text": "keep"},
        {"start_time": 2, "end_time": 4, "text": "replace"},
    ]
    retry = [{"start_time": 1.5, "end_time": 4.5, "text": "better"}]

    merged = benchmark.merge_segment_payloads(primary, retry, [(1.5, 4.5)])

    assert [value["text"] for value in merged] == ["keep", "better"]
