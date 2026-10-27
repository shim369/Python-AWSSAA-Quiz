"""問題の下書き生成(APIは呼ばず、偽のクライアントで確かめる)。"""

import json
from collections import Counter
from types import SimpleNamespace

import pytest
import yaml

from python_awssaa_quiz.exam_bank import load_exam_file, load_exam_questions
from python_awssaa_quiz.exam_drafting import (
    RESPONSE_SCHEMA,
    DraftError,
    build_user_prompt,
    finalize_drafts,
    least_covered_tasks,
    next_ids,
    request_drafts,
    response_text,
    write_drafts,
)
from python_awssaa_quiz.exam_guide import TASKS


def draft(task="3.4", n_correct=1, n=4, related=(79, 9999)):
    return {
        "task": task,
        "question": "ある企業は…\nどれか。",
        "choices": [
            {"text": f"案{i}", "correct": i < n_correct, "reason": f"理由{i}"} for i in range(n)
        ],
        "explanation": "ポイント",
        "related_keywords": list(related),
    }


def message(blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


def text_block(text):
    return SimpleNamespace(type="text", text=text)


class FakeClient:
    """client.beta.messages.stream(...) の呼び出しを記録し、決まった応答を返す。"""

    def __init__(self, response):
        self.response = response
        self.kwargs = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.kwargs = kwargs
        response = self.response

        class _Stream:
            def __enter__(self):
                return SimpleNamespace(get_final_message=lambda: response)

            def __exit__(self, *exc):
                return False

        return _Stream()


def test_request_drafts_sends_schema_and_parses(keywords):
    payload = {"questions": [draft()]}
    client = FakeClient(message([text_block(json.dumps(payload, ensure_ascii=False))]))
    result = request_drafts(
        client, keywords=keywords, tasks=[TASKS["3.4"]], count=1, existing=load_exam_questions()
    )
    assert result == payload["questions"]
    kw = client.kwargs
    assert kw["model"] == "claude-opus-5-5"
    assert kw["fallbacks"] == "default"
    assert kw["output_config"]["format"]["schema"] is RESPONSE_SCHEMA
    assert "Amazon CloudFront" in kw["system"][0]["text"]  # キーワード集を渡している
    assert "3.4" in kw["messages"][0]["content"]


def test_response_text_uses_output_after_fallback():
    blocks = [text_block('{"partial'), SimpleNamespace(type="fallback"), text_block('{"ok": 1}')]
    assert response_text(message(blocks)) == '{"ok": 1}'


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_response_text_reports_stop_reasons(stop):
    with pytest.raises(DraftError):
        response_text(message([text_block("{}")], stop_reason=stop))


def test_finalize_assigns_ids_and_validates():
    drafts = [draft(), draft(task="1.1", n_correct=2, n=5), draft(n_correct=0)]
    result = finalize_drafts(drafts, {"E0001", "E0014", "bad"}, {79})
    assert [r["id"] for r in result.accepted] == ["E0015", "E0016"]
    assert result.accepted[0]["domain"] == "performant"
    assert result.accepted[0]["related_keywords"] == [79]  # キーワード集にないNoは除く
    assert len(result.rejected) == 1 and "正解" in result.rejected[0][1]


def test_written_drafts_load_like_handwritten_questions(tmp_path):
    result = finalize_drafts([draft(), draft(task="4.4")], set(), {79})
    path = write_drafts(result.accepted, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "question: |" in text  # 複数行はブロックで書かれる
    assert "correct: false" not in text  # 手書きと同じく、誤答の correct は省く
    questions = load_exam_file(path)
    assert [q.id for q in questions] == ["E0001", "E0002"]
    assert yaml.safe_load(text)[0]["choices"][0]["correct"] is True


def test_least_covered_tasks_and_prompt():
    bank = load_exam_questions()
    tasks = least_covered_tasks(bank, 2)
    counts = Counter(q.task.id for q in bank)
    others = [t for t in TASKS.values() if t not in tasks]
    # 収録の少ないタスクが先に選ばれる
    assert max(counts[t.id] for t in tasks) <= min(counts[t.id] for t in others)
    prompt = build_user_prompt([TASKS["2.2"]], 3, bank, note="DR中心")
    assert "合計3問" in prompt and "DR中心" in prompt and "すでにある問題" in prompt


def test_next_ids():
    assert next_ids([], 2) == ["E0001", "E0002"]
    assert next_ids(["E0009", "x"], 1) == ["E0010"]
