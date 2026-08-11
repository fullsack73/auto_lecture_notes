from __future__ import annotations

import sys
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import lecture_auto.local_ai_worker as worker
from lecture_auto.local_runtime import LocalRuntimeManager
from lecture_auto.llm_adapter import LLMProviderAdapter
from lecture_auto.session_metadata_store import SessionMetadataStore
from lecture_auto.session_service import SessionService
from lecture_auto.stt_audio_policy import (
    canonical_audio_input,
    capture_source_recommendation,
    choose_audio_candidate,
    conditional_audio_filters,
)
from lecture_auto.stt_glossary import bounded_glossary, merge_hotwords
from lecture_auto.stt_profiles import (
    LOCAL_STT_PROFILES,
    backend_evaluation_report,
    get_local_stt_profile,
    physical_cpu_count,
)
from lecture_auto.stt_quality import (
    assess_stt_quality,
    build_retry_windows,
    merge_retry_segments,
    should_recommend_full_retry,
)
from lecture_auto.stt_refinement import (
    audit_refinement,
    build_refinement_evidence,
    segment_chunks,
)
from lecture_auto.stt_runtime import DiarizedSegment


def test_profiles_and_backend_evaluations_are_explicit() -> None:
    assert get_local_stt_profile("cpu-fast").compute_type == "int8"
    assert get_local_stt_profile("nvidia-balanced").model == "turbo"
    assert get_local_stt_profile("quality-retry").beam_size == 5
    assert set(LOCAL_STT_PROFILES) == {
        "cpu-fast",
        "cpu-balanced",
        "nvidia-balanced",
        "quality-retry",
    }
    report = {row["backend"]: row for row in backend_evaluation_report()}
    assert report["faster-whisper"]["status"] == "adopted"
    assert report["distil-whisper"]["status"] == "excluded"
    assert "Apple Metal/Core ML" in report["whisper.cpp"]["acceleration"]
    assert physical_cpu_count() >= 1


def test_glossary_is_deduplicated_and_bounded() -> None:
    terms = bounded_glossary(
        [
            "OpenGL Rasterization CUDA",
            "CUDA 그래픽스 파이프라인 그래픽스",
        ],
        max_terms=4,
        max_characters=40,
    )
    hotwords = merge_hotwords("BFS CUDA", terms)

    assert "그래픽스" in terms
    assert hotwords is not None
    assert hotwords.casefold().count("cuda") == 1
    assert len(hotwords) <= 1000


def test_retry_windows_are_contextual_bounded_and_merge_by_timestamp() -> None:
    primary = [
        DiarizedSegment("S", 0, 4, "정상", avg_logprob=-0.2),
        DiarizedSegment("S", 4, 6, "반복 반복 반복 반복", avg_logprob=-1.5),
        DiarizedSegment("S", 6, 9, "뒤 문맥", avg_logprob=-0.2),
    ]
    quality = assess_stt_quality(primary)
    windows = build_retry_windows(
        primary,
        quality,
        context_seconds=1,
        maximum_windows=2,
        maximum_total_seconds=5,
    )
    retry = [DiarizedSegment("S", 3, 7, "교정된 문장", avg_logprob=-0.1)]

    assert windows == [(3, 7)]
    assert [segment.text for segment in merge_retry_segments(primary, retry, windows)] == [
        "정상",
        "교정된 문장",
        "뒤 문맥",
    ]
    assert should_recommend_full_retry(quality) is False


def test_audio_policy_only_applies_evidence_backed_filters_and_preserves_raw() -> None:
    filters = conditional_audio_filters(
        {"low_loudness": True, "clipping_risk": False},
        persistent_noise=True,
        low_frequency_rumble=True,
    )
    decision = choose_audio_candidate(
        {
            "raw": {"cer": 0.20, "term_recall": 0.8},
            "denoised": {"cer": 0.22, "term_recall": 0.9},
        }
    )

    assert filters == (
        "loudnorm=I=-20:LRA=11:TP=-1.5",
        "highpass=f=80",
        "deepfilternet",
    )
    assert decision.selected == "raw"
    assert capture_source_recommendation(
        capture_source="microphone",
        playback_audio_expected=True,
    )


def test_canonical_audio_skips_conversion_for_single_use(tmp_path: Path) -> None:
    source = tmp_path / "source.mp3"
    source.write_bytes(b"not decoded when expected_uses is one")

    with canonical_audio_input(
        audio_path=source,
        cache_dir=tmp_path / "cache",
        expected_uses=1,
        ffmpeg_bin="missing-ffmpeg",
    ) as selected:
        assert selected == source.resolve()

    assert not (tmp_path / "cache").exists()


def test_refinement_audit_detects_numbers_and_named_terms_and_chunks_safely() -> None:
    audit = audit_refinement(
        "CUDA batch는 4입니다.",
        "OpenGL batch는 8입니다.",
    )
    chunks = segment_chunks("첫 문장입니다. " * 30, chunk_size=80, overlap_characters=0)

    assert audit.inserted_numbers == ("8",)
    assert audit.removed_numbers == ("4",)
    assert set(audit.changed_named_terms) == {"cuda", "opengl"}
    assert len(chunks) > 1
    assert all(len(chunk) <= 81 for chunk in chunks)


def test_refinement_evidence_allows_contextual_asr_correction() -> None:
    evidence = build_refinement_evidence(
        {
            "segments": [
                {
                    "start_time": 10,
                    "end_time": 12,
                    "text": "자섭의 섹이",
                    "avg_logprob": -1.2,
                }
            ]
        }
    )

    assert "Low confidence alone does not make a span unclear" in evidence["rule"]
    assert "multiple plausible readings remain" in evidence["rule"]


def test_persistent_worker_reuses_process_and_supports_unload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "worker.py"
    script.write_text(
        "import json,sys\n"
        "count=0\n"
        "for line in sys.stdin:\n"
        " request=json.loads(line)\n"
        " if request['action']=='unload_whisper':\n"
        "  print(json.dumps({'type':'result','result':{'unloaded_model_count':count}}),flush=True)\n"
        "  count=0\n"
        " else:\n"
        "  count+=1\n"
        "  print(json.dumps({'type':'result','result':{'count':count}}),flush=True)\n",
        encoding="utf-8",
    )
    manager = LocalRuntimeManager(
        tmp_path / "runtime",
        worker_script=script,
        warm_worker_idle_timeout_seconds=60,
    )
    monkeypatch.setattr(manager, "python_for", lambda _feature: Path(sys.executable))

    first = manager.run_feature("whisper", {"action": "whisper"})
    second = manager.run_feature("whisper", {"action": "whisper"})
    unloaded = manager.unload_whisper()
    manager.close()

    assert first["count"] == 1
    assert second["count"] == 2
    assert unloaded == 2
    assert manager._warm_workers == {}


def test_worker_quality_retry_is_bounded_and_reuses_loaded_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeWhisperModel:
        def __init__(self, _model_source, **_kwargs) -> None:
            pass

        def transcribe(self, _audio_path, **kwargs):
            calls.append(kwargs)
            if "clip_timestamps" in kwargs:
                segment = SimpleNamespace(
                    text=" 교정 ",
                    start=0.0,
                    end=1.0,
                    avg_logprob=-0.1,
                    compression_ratio=1.0,
                    no_speech_prob=0.01,
                    temperature=0.0,
                    words=[],
                )
            else:
                segment = [
                    SimpleNamespace(
                        text=" 정상 발화 ",
                        start=0.0,
                        end=2.0,
                        avg_logprob=-0.1,
                        compression_ratio=1.0,
                        no_speech_prob=0.01,
                        temperature=0.0,
                        words=[],
                    ),
                    SimpleNamespace(
                        text=" 반복 반복 반복 반복 ",
                        start=2.0,
                        end=3.0,
                        avg_logprob=-1.5,
                        compression_ratio=1.0,
                        no_speech_prob=0.01,
                        temperature=0.0,
                        words=[],
                    ),
                ]
                return segment, SimpleNamespace(duration=10.0, language="ko")
            return [segment], SimpleNamespace(duration=10.0, language="ko")

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(
            WhisperModel=FakeWhisperModel,
            BatchedInferencePipeline=object,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "ctranslate2",
        SimpleNamespace(
            get_cuda_device_count=lambda: 0,
            get_supported_compute_types=lambda _device: {"int8"},
        ),
    )

    result = worker.whisper(
        {
            "audio_path": str(tmp_path / "audio.wav"),
            "model": "base",
            "device": "cpu",
            "compute_type": "int8",
            "batch_size": 1,
            "vad_filter": False,
            "quality_retry_enabled": True,
            "quality_retry_max_windows": 1,
            "quality_retry_max_seconds": 5,
        }
    )

    assert len(result["retry_windows"]) == 1
    assert result["retry_segments"][0]["text"] == "교정"
    assert "clip_timestamps" in calls[1]


def test_session_refine_passes_asr_evidence_and_writes_audit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    store = SessionMetadataStore(workspace / "metadata" / "sessions.json")
    store.metadata_file.parent.mkdir(parents=True)
    transcript_path = workspace / "transcripts" / "s1-raw.md"
    metadata_path = workspace / "transcripts" / "s1-raw.stt.json"
    transcript_path.parent.mkdir(parents=True)
    transcript_path.write_text("CUDA batch는 4입니다.", encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "metadata": {"quality": {"suspect_segment_count": 1}},
                "segments": [
                    {
                        "start_time": 10,
                        "end_time": 12,
                        "text": "CUDA batch는 4입니다.",
                        "avg_logprob": -1.2,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store.upsert(
        {
            "session_id": "s1",
            "date": "2026-07-26",
            "title": "CUDA",
            "course": "CS",
            "status": "completed",
            "transcript_file_path": "transcripts/s1-raw.md",
            "transcript_metadata_file_path": "transcripts/s1-raw.stt.json",
            "timestamps": {"created_at": "2026-07-26T00:00:00Z"},
            "naming_pending": False,
        }
    )
    adapter = MagicMock(spec=LLMProviderAdapter)
    adapter.refine_transcript.return_value = "CUDA batch는 8입니다."
    service = SessionService(store=store, llm_adapter=adapter)

    result = service.transcript_refine("s1")

    evidence = adapter.refine_transcript.call_args.kwargs["evidence"]
    assert evidence["segments"][0]["start_time"] == 10
    audit_path = workspace / result.payload["refinement_audit_file_path"]
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["inserted_numbers"] == ["8"]
    assert audit["removed_numbers"] == ["4"]
