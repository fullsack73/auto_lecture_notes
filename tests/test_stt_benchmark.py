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
