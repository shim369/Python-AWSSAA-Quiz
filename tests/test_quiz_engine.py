import pytest

from python_awssaa_quiz.quiz_engine import (
    MASK,
    ItemStats,
    QuestionFormat,
    QuizMode,
    QuizSettings,
    are_related,
    contains_alias,
    generate_quiz,
    is_format_applicable,
    make_question,
    mask_text,
)
import random

SEEDS = range(5)


def all_questions(items):
    """全出題単位 × 適用可能な全形式 × 複数シードの問題を作る。"""
    for seed in SEEDS:
        rng = random.Random(seed)
        for item in items:
            for fmt in QuestionFormat:
                if is_format_applicable(item, fmt):
                    yield make_question(item, fmt, items, rng)


def by_id(items):
    return {it.item_id: it for it in items}


# ---------------------------------------------------------------- 必須の確認項目


def test_prompt_does_not_contain_answer(items):
    for q in all_questions(items):
        if q.format is QuestionFormat.KEYWORD_TO_SUMMARY:
            # 問題文はキーワードそのもの。正解の選択肢(概要)側にキーワード名が出ないこと
            assert not contains_alias(q.choices[q.answer_index], q.item.name), q
        else:
            assert not contains_alias(q.prompt, q.item.name), q


def test_choices_are_four_unique_with_exactly_one_answer(items):
    lookup = by_id(items)
    for q in all_questions(items):
        assert len(q.choices) == 4
        assert len(set(q.choices)) == 4
        assert len(set(q.choice_item_ids)) == 4
        assert q.choice_item_ids.count(q.item.item_id) == 1
        assert q.choice_item_ids[q.answer_index] == q.item.item_id
        for text, cid in zip(q.choices, q.choice_item_ids):
            if q.format is QuestionFormat.KEYWORD_TO_SUMMARY:
                assert not contains_alias(text, lookup[cid].name)
            else:
                assert text == lookup[cid].name


# ---------------------------------------------------------------- 伏せ字


@pytest.mark.parametrize(
    "text, name, expected",
    [
        ("RIより柔軟", "リザーブドインスタンス(RI)", f"{MASK}より柔軟"),
        ("DLQに隔離", "デッドレターキュー(DLQ)", f"{MASK}に隔離"),
        ("→Fargate", "AWS Fargate", f"→{MASK}"),
        ("Database Migration Service。", "AWS DMS", f"{MASK}。"),
        ("Compute Savings Plansは", "Savings Plans", f"Compute {MASK}は"),
        ("別リージョン(CRR)", "S3レプリケーション(CRR/SRR)", f"別リージョン({MASK})"),
    ],
)
def test_mask_text(text, name, expected):
    assert mask_text(text, name) == expected


def test_mask_does_not_hit_inside_other_words():
    # 「RI」が英単語の一部(PRICE)に誤って一致しない
    assert mask_text("PRICE", "リザーブドインスタンス(RI)") == "PRICE"


def test_japanese_parenthetical_is_not_masked():
    # 「パブリック/プライベート」まで伏せると問題文が読めなくなる
    text = "ルートがあればパブリック"
    assert mask_text(text, "サブネット(パブリック/プライベート)") == text


# ---------------------------------------------------------------- 誤答の選び方


def test_multi_service_keyword_is_split(items):
    split = [it for it in items if it.no == 142]
    assert [it.name for it in split] == [
        "Amazon Comprehend",
        "Amazon Textract",
        "Amazon Transcribe",
        "Amazon Translate",
        "Amazon Polly",
    ]
    assert split[1].summary == "文書からのテキスト抽出"
    assert all("/" not in it.name for it in items if it.no == 142)


def test_distractors_prefer_same_category(items):
    for q in all_questions(items):
        same = [
            it for it in items
            if it.category == q.item.category and not are_related(q.item, it)
        ]
        if len(same) >= 4 + 3:  # 関連の除外を考えても十分な候補がある分野
            cats = {by_id(items)[cid].category for cid in q.choice_item_ids}
            assert cats == {q.item.category}, q


def test_small_category_is_filled_from_others(items):
    rng = random.Random(0)
    target = next(it for it in items if it.name == "AWS Cost Explorer")  # コスト管理は4件
    q = make_question(target, QuestionFormat.SUMMARY_TO_KEYWORD, items, rng)
    assert len(q.choices) == 4


def test_related_items_are_never_together(items):
    lookup = by_id(items)
    for q in all_questions(items):
        opts = [lookup[c] for c in q.choice_item_ids]
        for i, a in enumerate(opts):
            for b in opts[i + 1 :]:
                assert not are_related(a, b), (a.name, b.name)


def test_elb_and_alb_are_related(items):
    elb = next(it for it in items if it.name.startswith("Elastic Load Balancing"))
    alb = next(it for it in items if it.name.startswith("Application Load Balancer"))
    s3 = next(it for it in items if it.name == "Amazon S3")
    lifecycle = next(it for it in items if it.name == "S3ライフサイクルポリシー")
    assert are_related(elb, alb)
    assert are_related(s3, lifecycle)


# ---------------------------------------------------------------- 出題設定・モード


def test_same_seed_reproduces_quiz(items):
    settings = QuizSettings(formats=tuple(QuestionFormat), count=20)
    assert generate_quiz(items, settings, seed=42) == generate_quiz(items, settings, seed=42)
    assert generate_quiz(items, settings, seed=42) != generate_quiz(items, settings, seed=43)


def test_filters(items):
    settings = QuizSettings(categories=("移行",), importances=(2,), count=None)
    qs = generate_quiz(items, settings, seed=0)
    assert {q.item.name for q in qs} == {"AWS DMS", "AWS SCT"}


def test_scenario_excludes_generic_items(items):
    settings = QuizSettings(formats=(QuestionFormat.SCENARIO_TO_KEYWORD,), count=None)
    qs = generate_quiz(items, settings, seed=0)
    assert all(q.item.no not in {58, 142, 143} for q in qs)
    assert len(qs) == len({q.item.item_id for q in qs})


def test_review_mode_only_uses_mistakes(items):
    stats = {
        "1": ItemStats((False, True)),
        "2": ItemStats((True, True, True)),
        "3": ItemStats((True, True, False)),
    }
    settings = QuizSettings(mode=QuizMode.REVIEW_MISTAKES, count=None)
    qs = generate_quiz(items, settings, stats, seed=0)
    assert sorted(q.item.item_id for q in qs) == ["1", "3"]


def test_weak_first_prefers_weak_items(items):
    weak_ids = {it.item_id for it in items[:10]}
    stats = {it.item_id: ItemStats((False, False, False)) for it in items[:10]}
    stats |= {it.item_id: ItemStats((True, True, True)) for it in items[10:]}
    settings = QuizSettings(mode=QuizMode.WEAK_FIRST, count=10)
    hits = [
        len(weak_ids & {q.item.item_id for q in generate_quiz(items, settings, stats, seed=s)})
        for s in range(20)
    ]
    # 弱点10件(重み1+9+2+α)は、全問正解の他の問題(重み1〜2)より明らかに多く選ばれる
    # (一様ランダムなら 10×10/全件数 件程度。キーワードの追加で件数が変わっても成り立つよう比で見る)
    random_hits = 10 * 10 / len(items)
    assert sum(hits) / len(hits) > random_hits * 3


def test_exam_missed_keywords_raise_weight(items):
    from python_awssaa_quiz.quiz_engine import weakness_weight

    item = items[0]
    assert weakness_weight(item, None, exam_missed=True) == weakness_weight(item, None) + 2

    # 本番形式で間違えた関連キーワード(全問正解済み)が、他の全問正解済みより選ばれやすい
    missed = frozenset(it.no for it in items[:10])
    stats = {it.item_id: ItemStats((True, True, True)) for it in items}
    settings = QuizSettings(mode=QuizMode.WEAK_FIRST, count=10)

    def hits(**kwargs):
        return sum(
            sum(q.item.no in missed for q in generate_quiz(items, settings, stats, seed=s, **kwargs))
            for s in range(100)
        )

    # 重みは1→3(★★★なら2→4)になるので、2〜3倍程度選ばれやすくなる
    assert hits(exam_missed_nos=missed) > hits() * 1.5
