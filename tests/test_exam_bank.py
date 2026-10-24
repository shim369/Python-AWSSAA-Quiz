import random
from collections import Counter

import pytest

from python_awssaa_quiz.exam_bank import (
    MOCK_EXAM_SIZE,
    ExamBankError,
    ExamMode,
    ExamSettings,
    allocate_by_domain,
    generate_exam,
    load_exam_file,
    lint_question,
    load_exam_questions,
    make_answer,
    missed_keyword_nos,
    parse_question,
    present,
    scaled_score,
    time_limit_seconds,
)
from python_awssaa_quiz.exam_guide import TASKS, Domain
from python_awssaa_quiz.quiz_engine import ItemStats, QuizMode


def raw_question(**overrides):
    q = {
        "id": "E9001",
        "domain": "secure",
        "task": "1.1",
        "question": "問題文",
        "choices": [
            {"text": "正解", "correct": True, "reason": "理由A"},
            {"text": "誤答1", "reason": "理由B"},
            {"text": "誤答2", "reason": "理由C"},
            {"text": "誤答3", "reason": "理由D"},
        ],
        "explanation": "解説",
        "related_keywords": [84],
    }
    q.update(overrides)
    return q


def multi_choices(n_correct=2, n=5):
    return [
        {"text": f"選択肢{i}", "correct": i < n_correct, "reason": f"理由{i}"} for i in range(n)
    ]


def synthetic_bank(per_domain: dict[Domain, int]):
    task_of = {d: next(t.id for t in TASKS.values() if t.domain is d) for d in Domain}
    return [
        parse_question(raw_question(id=f"E{d_i}{i:03}", domain=d.value, task=task_of[d]))
        for d_i, (d, n) in enumerate(per_domain.items(), start=1)
        for i in range(n)
    ]


# ---------------------------------------------------------------- 同梱の問題データ


@pytest.fixture(scope="module")
def bank():
    return load_exam_questions()


def test_bundled_bank_is_valid(bank):
    assert bank, "data/exam_questions/ に問題がありません"
    assert len({q.id for q in bank}) == len(bank)


def test_bundled_bank_covers_every_domain(bank):
    assert {q.domain for q in bank} == set(Domain)


def test_bundled_bank_passes_content_checks(bank, keywords):
    # キーワード集にないNoや、問題文の「〇つ選択」がないか(exam-questions check と同じ確認)
    nos = {k.no for k in keywords}
    for q in bank:
        assert not lint_question(q, nos).errors, q.id


# ---------------------------------------------------------------- 検証


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": "1"}, "id は"),
        ({"domain": "security"}, "domain は"),
        ({"task": "3.1"}, "task は"),
        ({"task": "9.9"}, "task は"),
        ({"choices": multi_choices(0, 4)}, "正解"),
        ({"choices": multi_choices(1, 5)}, "4つ"),
        ({"choices": multi_choices(2, 4)}, "5択以上"),
        ({"choices": multi_choices(3, 5)}, "誤答を3つ以上"),
        ({"related_keywords": ["S3"]}, "related_keywords"),
        ({"answer": "A"}, "知らない項目"),
    ],
)
def test_parse_question_rejects_invalid(overrides, message):
    with pytest.raises(ExamBankError, match=message):
        parse_question(raw_question(**overrides))


def test_parse_question_rejects_choice_without_reason():
    choices = raw_question()["choices"]
    choices[1] = {"text": "誤答1"}
    with pytest.raises(ExamBankError, match="reason"):
        parse_question(raw_question(choices=choices))


def test_parse_question_rejects_duplicate_choice_text():
    choices = raw_question()["choices"]
    choices[2]["text"] = choices[1]["text"]
    with pytest.raises(ExamBankError, match="同じ文"):
        parse_question(raw_question(choices=choices))


def test_multi_answer_question_is_accepted():
    q = parse_question(raw_question(choices=multi_choices(2, 5)))
    assert q.answer_count == 2


def test_load_reports_file_name_and_duplicate_ids(tmp_path):
    (tmp_path / "a.yaml").write_text("- id: E0001\n  domain: nope\n", encoding="utf-8")
    with pytest.raises(ExamBankError, match="a.yaml"):
        load_exam_file(tmp_path / "a.yaml")

    import yaml

    text = yaml.safe_dump([raw_question()], allow_unicode=True)
    (tmp_path / "a.yaml").write_text(text, encoding="utf-8")
    (tmp_path / "b.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ExamBankError, match="重複"):
        load_exam_questions(tmp_path)


def test_drafts_folder_and_missing_folder_are_ignored(tmp_path):
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts" / "x.yaml").write_text("壊れたファイル: [", encoding="utf-8")
    assert load_exam_questions(tmp_path) == []
    assert load_exam_questions(tmp_path / "none") == []


# ---------------------------------------------------------------- 出題


def test_present_keeps_answers_after_shuffle():
    q = parse_question(raw_question(choices=multi_choices(2, 5)))
    for seed in range(20):
        pq = present(q, random.Random(seed))
        assert sorted(pq.order) == list(range(5))
        assert {pq.choices[i].text for i in pq.answer} == {"選択肢0", "選択肢1"}
        assert pq.is_correct(pq.answer)
        assert not pq.is_correct(list(pq.answer)[:1])  # 片方だけでは不正解
        assert pq.original_indices(pq.answer) == (0, 1)


def test_make_answer_stores_original_positions():
    q = parse_question(raw_question())
    pq = present(q, random.Random(3))
    shown = list(pq.answer)
    a = make_answer("s", 0, pq, shown, ExamMode.PRACTICE)
    assert a.selected == (0,) and a.is_correct and a.domain == "secure"


def test_allocate_follows_domain_weights():
    alloc = allocate_by_domain({d: 100 for d in Domain}, MOCK_EXAM_SIZE)
    assert alloc == {
        Domain.SECURE: 19,
        Domain.RESILIENT: 17,
        Domain.PERFORMANT: 16,
        Domain.COST: 13,
    }


def test_allocate_fills_shortage_from_other_domains():
    available = {Domain.SECURE: 3, Domain.RESILIENT: 100, Domain.PERFORMANT: 100, Domain.COST: 0}
    alloc = allocate_by_domain(available, 65)
    assert sum(alloc.values()) == 65
    assert alloc[Domain.SECURE] == 3 and alloc[Domain.COST] == 0
    assert allocate_by_domain({d: 2 for d in Domain}, 65) == {d: 2 for d in Domain}


def test_mock_exam_mixes_domains_and_is_reproducible():
    bank = synthetic_bank({d: 30 for d in Domain})
    settings = ExamSettings(mode=ExamMode.MOCK, count=None)
    exam = generate_exam(bank, settings, seed=1)
    assert len(exam) == MOCK_EXAM_SIZE
    assert len({pq.question.id for pq in exam}) == MOCK_EXAM_SIZE
    assert Counter(pq.question.domain for pq in exam)[Domain.SECURE] == 19
    assert [pq.question.domain for pq in exam[:19]] != [Domain.SECURE] * 19  # 分野ごとに固まらない
    assert generate_exam(bank, settings, seed=1) == exam


def test_practice_filters_and_review_mode():
    bank = synthetic_bank({d: 5 for d in Domain})
    settings = ExamSettings(domains=(Domain.COST,), count=None)
    assert {pq.question.domain for pq in generate_exam(bank, settings, seed=0)} == {Domain.COST}

    target = bank[0].task.id
    by_task = generate_exam(bank, ExamSettings(tasks=(target,), count=None), seed=0)
    assert {pq.question.task.id for pq in by_task} == {target}

    stats = {bank[0].id: ItemStats((False,)), bank[1].id: ItemStats((True, True))}
    review = ExamSettings(order=QuizMode.REVIEW_MISTAKES, count=None)
    assert [pq.question.id for pq in generate_exam(bank, review, stats, seed=0)] == [bank[0].id]


def test_weak_first_prefers_missed_questions():
    bank = synthetic_bank({Domain.SECURE: 40})
    weak = {q.id for q in bank[:5]}
    stats = {q.id: ItemStats((False, False, False) if q.id in weak else (True,)) for q in bank}
    settings = ExamSettings(order=QuizMode.WEAK_FIRST, count=5)
    hits = sum(
        len(weak & {pq.question.id for pq in generate_exam(bank, settings, stats, seed=s)})
        for s in range(30)
    )
    assert hits > 30 * 5 * 0.5


def test_score_and_time_limit():
    assert scaled_score(47, 65) == 723
    assert scaled_score(0, 0) == 0
    assert time_limit_seconds(65) == 130 * 60


def test_missed_keyword_nos_uses_latest_answer():
    q1 = parse_question(raw_question(id="E9001", related_keywords=[1, 2]))
    q2 = parse_question(raw_question(id="E9002", related_keywords=[3]))
    stats = {"E9001": ItemStats((False, True)), "E9002": ItemStats((True, False))}
    assert missed_keyword_nos([q1, q2], stats) == {1, 2}


def test_lint_question_reports_problems():
    q = parse_question(raw_question(question="どれか。(2つ選択)", related_keywords=[1, 9999]))
    lint = lint_question(q, {1})
    assert len(lint.errors) == 2

    choices = raw_question()["choices"]
    choices[0]["text"] = "とても長くて詳しい説明が付いた、明らかに目立つ正解の選択肢"
    lint = lint_question(parse_question(raw_question(choices=choices, explanation="")), {84})
    assert not lint.errors
    assert any("長く" in w for w in lint.warnings) and any("explanation" in w for w in lint.warnings)
