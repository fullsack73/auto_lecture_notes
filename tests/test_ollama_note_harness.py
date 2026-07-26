from __future__ import annotations

import json
from unittest.mock import MagicMock

from lecture_auto.llm_adapter import OllamaLLMAdapter
from lecture_auto.llm_config import LLMConfig


def _adapter() -> OllamaLLMAdapter:
    adapter = OllamaLLMAdapter(
        LLMConfig(provider="ollama", model_name="test-model", language="Korean")
    )
    adapter.ollama = MagicMock()
    return adapter


def _ollama_response(payload: dict) -> dict:
    return {"message": {"content": json.dumps(payload, ensure_ascii=False)}}


def _ollama_raw_response(content: str) -> dict:
    return {"message": {"content": content}}


def _six_core_concepts(seed: str) -> list[str]:
    return [f"{seed} 핵심 개념 {index}는 강의 이해에 필요한 구체 항목이다." for index in range(1, 7)]


def _detailed_sections() -> list[dict[str, list[str] | str]]:
    return [
        {
            "title": "정렬 알고리즘 비교",
            "bullets": [
                "정렬 알고리즘은 데이터를 기준에 맞게 재배열하는 절차다.",
                "버블 정렬은 인접 원소를 반복 비교해 위치를 바꾼다.",
                "병합 정렬은 배열을 나눈 뒤 정렬된 부분 결과를 합친다.",
                "입력 크기가 커질수록 시간 복잡도 차이가 선택 기준이 된다.",
            ],
        },
        {
            "title": "시간 복잡도 해석",
            "bullets": [
                "시간 복잡도는 입력 크기 증가에 따른 실행 시간 증가율을 설명한다.",
                "복잡도 비교는 같은 문제를 푸는 여러 알고리즘의 효율을 구분한다.",
                "최악의 경우 분석은 성능 보장을 이해하는 데 중요하다.",
                "강의는 정렬 방식의 구조와 비용을 함께 비교한다.",
            ],
        },
    ]


def test_ollama_notes_harness_repairs_json_and_renders_structured_markdown() -> None:
    adapter = _adapter()
    adapter.ollama.chat.side_effect = [
        _ollama_response({"topic_overview": ["머신러닝의 기본 학습 방식 비교"]}),
        _ollama_response({"core_concepts": ["지도학습은 레이블이 있는 데이터로 모델을 학습한다."]}),
        _ollama_response(
            {"detailed_explanations": [{"title": "Sub Topic 1", "bullets": ["지도학습과 비지도학습을 구분한다."]}]}
        ),
        _ollama_response({"examples_mentioned": ["Not mentioned."]}),
        _ollama_response({"questions_to_review": ["지도학습이란 무엇인가?"]}),
        _ollama_response({"exam_related_mentions": ["Not mentioned."]}),
        _ollama_response(
            {
                "topic_overview": ["머신러닝의 기본 학습 방식 비교"],
                "core_concepts": ["지도학습은 레이블이 있는 데이터로 모델을 학습한다."],
                "detailed_explanations": [
                    {
                        "title": "지도학습과 비지도학습",
                        "bullets": ["지도학습과 비지도학습을 데이터 레이블 기준으로 구분한다."],
                    }
                ],
                "examples_mentioned": ["Not mentioned."],
                "questions_to_review": [
                    "지도학습은 어떤 데이터 조건에서 작동하는가?",
                    "비지도학습은 지도학습과 어떤 점에서 다른가?",
                    "레이블 유무는 모델 학습 방식에 어떤 영향을 주는가?",
                    "두 학습 방식의 차이를 알면 강의의 핵심 구조를 어떻게 재구성할 수 있는가?",
                ],
                "exam_related_mentions": ["Not mentioned."],
            }
        ),
    ]

    notes = adapter.generate_notes(
        "지도학습은 레이블 데이터를 사용하고 비지도학습도 있습니다.",
        "# ignored template",
        context_topic="머신러닝 기초",
    )

    assert "# Structured Lecture Notes" in notes
    assert "### 지도학습과 비지도학습" in notes
    assert "## Questions to Review" in notes
    assert "레이블 유무는 모델 학습 방식에 어떤 영향을 주는가?" in notes
    assert adapter.ollama.chat.call_count == 7
    assert adapter.ollama.chat.call_args_list[0].kwargs["format"] == "json"
    all_prompts = [
        call.kwargs["messages"][1]["content"]
        for call in adapter.ollama.chat.call_args_list
    ]
    system_prompt = adapter.ollama.chat.call_args_list[0].kwargs["messages"][0]["content"]
    assert "Final Markdown template headings" in system_prompt
    assert "# ignored template" in system_prompt
    assert all("# ignored template" not in prompt for prompt in all_prompts)
    assert "Generate only this section: topic_overview" in all_prompts[0]
    assert "Generate only this section: questions_to_review" in all_prompts[4]


def test_ollama_notes_harness_uses_valid_json_without_repair() -> None:
    adapter = _adapter()
    adapter.ollama.chat.side_effect = [
        _ollama_response({"topic_overview": ["정렬 알고리즘의 목적과 비교 기준"]}),
        _ollama_response({"core_concepts": _six_core_concepts("정렬")}),
        _ollama_response({"detailed_explanations": _detailed_sections()}),
        _ollama_response({"examples_mentioned": ["버블 정렬", "병합 정렬"]}),
        _ollama_response(
            {
                "questions_to_review": [
                    "정렬 알고리즘은 어떤 문제를 해결하는가?",
                    "시간 복잡도는 알고리즘 비교에서 왜 중요한가?",
                    "버블 정렬과 병합 정렬의 핵심 차이는 무엇인가?",
                    "입력 크기가 커질 때 정렬 방식 선택은 어떻게 달라지는가?",
                ]
            }
        ),
        _ollama_response({"exam_related_mentions": ["중간고사에 시간 복잡도 비교가 나온다고 언급했다."]}),
    ]

    notes = adapter.generate_notes("정렬 알고리즘 강의", "# ignored template")

    assert adapter.ollama.chat.call_count == 6
    assert "## Topic Overview" in notes
    assert "### 정렬 알고리즘 비교" in notes
    assert "- 버블 정렬" in notes
    assert "중간고사에 시간 복잡도 비교" in notes


def test_ollama_notes_harness_recovers_invalid_backslash_escapes() -> None:
    adapter = _adapter()
    adapter.ollama.chat.side_effect = [
        _ollama_response({"topic_overview": ["미분 기호와 최적화 개요"]}),
        _ollama_raw_response(
            r'{"core_concepts":["\alpha는 학습률을 나타낸다.","최적화는 손실을 줄이는 방향으로 파라미터를 조정한다.","기울기는 손실 함수가 증가하는 방향을 나타낸다.","업데이트 식은 기울기와 학습률을 함께 사용한다.","학습률이 크면 발산 위험이 커질 수 있다.","학습률이 작으면 수렴 속도가 느려질 수 있다."]}'
        ),
        _ollama_response(
            {
                "detailed_explanations": [
                    {
                        "title": "학습률과 업데이트",
                        "bullets": [
                            r"가중치 업데이트는 \alpha 값에 영향을 받는다.",
                            "학습률은 한 번의 업데이트에서 이동하는 크기를 정한다.",
                            "기울기는 손실을 줄이기 위한 조정 방향 계산에 쓰인다.",
                            "학습률 선택은 수렴 속도와 안정성 사이의 균형이다.",
                        ],
                    },
                    {
                        "title": "최적화 안정성",
                        "bullets": [
                            "너무 큰 학습률은 최솟값 주변을 지나치게 만들 수 있다.",
                            "너무 작은 학습률은 많은 반복을 요구할 수 있다.",
                            "업데이트 규칙을 이해하면 최적화 흐름을 재구성할 수 있다.",
                            "강의는 기호와 실제 학습 동작을 연결한다.",
                        ],
                    },
                ]
            }
        ),
        _ollama_response({"examples_mentioned": ["Not mentioned."]}),
        _ollama_response(
            {
                "questions_to_review": [
                    "학습률은 최적화 과정에서 어떤 역할을 하는가?",
                    "학습률이 너무 크면 어떤 문제가 생기는가?",
                    "학습률이 너무 작으면 학습 과정은 어떻게 달라지는가?",
                    "업데이트 식에서 학습률을 이해하면 강의 흐름을 어떻게 재구성할 수 있는가?",
                ]
            }
        ),
        _ollama_response({"exam_related_mentions": ["Not mentioned."]}),
    ]

    notes = adapter.generate_notes("학습률 alpha 강의", "# ignored template")

    assert r"\alpha는 학습률을 나타낸다." in notes
    assert r"가중치 업데이트는 \alpha 값에 영향을 받는다." in notes


def test_ollama_notes_harness_repairs_malformed_json_syntax() -> None:
    adapter = _adapter()
    core_concepts = _six_core_concepts("자료구조")
    malformed_core_concepts = (
        '{"core_concepts":['
        f'{json.dumps(core_concepts[0], ensure_ascii=False)}\n'
        f'{json.dumps(core_concepts[1], ensure_ascii=False)},'
        + ",".join(
            json.dumps(item, ensure_ascii=False) for item in core_concepts[2:]
        )
        + "]}"
    )
    adapter.ollama.chat.side_effect = [
        _ollama_response({"topic_overview": ["자료구조의 목적과 선택 기준"]}),
        _ollama_raw_response(malformed_core_concepts),
        _ollama_response({"core_concepts": core_concepts}),
        _ollama_response({"detailed_explanations": _detailed_sections()}),
        _ollama_response({"examples_mentioned": ["버블 정렬", "병합 정렬"]}),
        _ollama_response(
            {
                "questions_to_review": [
                    "자료구조는 어떤 문제를 해결하는가?",
                    "자료구조 선택에서 시간 복잡도는 왜 중요한가?",
                    "배열과 연결 구조의 핵심 차이는 무엇인가?",
                    "입력 특성에 따라 자료구조 선택은 어떻게 달라지는가?",
                ]
            }
        ),
        _ollama_response({"exam_related_mentions": ["Not mentioned."]}),
    ]

    notes = adapter.generate_notes("자료구조 강의", "# ignored template")

    assert "## Core Concepts" in notes
    assert core_concepts[0] in notes
    assert adapter.ollama.chat.call_count == 7
    syntax_repair_prompt = (
        adapter.ollama.chat.call_args_list[2].kwargs["messages"][1]["content"]
    )
    assert "syntactically invalid" in syntax_repair_prompt
    assert "Expecting ',' delimiter" in syntax_repair_prompt
