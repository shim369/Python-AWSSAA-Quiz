"""トップ画面(出題設定)。起動: uv run streamlit run app.py"""

import streamlit as st

from python_awssaa_quiz.quiz_engine import (
    QuestionFormat,
    QuizMode,
    QuizSettings,
    filter_items,
    generate_quiz,
    needs_review,
)
from python_awssaa_quiz.ui import (
    APP_TITLE,
    current_quiz,
    exam_missed_nos,
    get_items,
    get_store,
    setup_page,
    start_quiz,
)

setup_page()
st.title(APP_TITLE)
st.caption("AWS 認定ソリューションアーキテクト – アソシエイト(SAA-C03)キーワード4択クイズ")

items = get_items()
store = get_store()

quiz = current_quiz()
if quiz is not None and not quiz.finished:
    st.info(f"出題中のクイズがあります({len(quiz.answers)}/{len(quiz.questions)}問回答済み)")
    if st.button("続きから解く", type="primary"):
        st.switch_page("pages/1_クイズ.py")

st.page_link(
    "pages/4_本番形式.py",
    label="本番形式の問題(シナリオ問題・模擬試験)はこちら",
    icon="📝",
)

categories = list(dict.fromkeys(it.category for it in items))
STAR_OPTIONS = {"★★★": 3, "★★": 2, "★": 1}
COUNT_OPTIONS = {"10問": 10, "20問": 20, "50問": 50, "全問": None}

st.subheader("出題設定")

selected_categories = st.multiselect(
    "分野", categories, placeholder="すべての分野(絞り込む場合は選択)"
)
selected_stars = st.pills(
    "重要度", list(STAR_OPTIONS), selection_mode="multi", default=list(STAR_OPTIONS)
)
selected_formats = st.pills(
    "出題形式",
    list(QuestionFormat),
    selection_mode="multi",
    default=[QuestionFormat.SUMMARY_TO_KEYWORD],
    format_func=lambda f: f.label,
    help="複数選ぶと、問題ごとにランダムで形式が決まります",
)
count_label = st.segmented_control("問題数", list(COUNT_OPTIONS), default="10問")
mode = st.radio(
    "出題モード",
    list(QuizMode),
    format_func=lambda m: m.label,
    horizontal=True,
    captions=[
        "条件に合う問題からランダムに出題",
        "不正解が多い・理解度△・★★★・未回答・本番形式で間違えた関連キーワードを優先",
        "直近3回の回答に不正解がある問題だけ",
    ],
)
with st.expander("詳細設定"):
    seed_text = st.text_input("乱数シード(空欄ならランダム)", value="")

settings = QuizSettings(
    categories=tuple(selected_categories),
    importances=tuple(STAR_OPTIONS[s] for s in selected_stars or []),
    formats=tuple(selected_formats or []),
    count=COUNT_OPTIONS[count_label or "10問"],
    mode=mode,
)

matching = filter_items(items, settings) if settings.formats else []
stats = store.item_stats()
if mode is QuizMode.REVIEW_MISTAKES:
    matching = [it for it in matching if needs_review(stats.get(it.item_id))]
n_questions = len(matching) if settings.count is None else min(settings.count, len(matching))
st.caption(f"条件に合う問題: {len(matching)}問 → 今回の出題: {n_questions}問")

problems = []
if not settings.formats:
    problems.append("出題形式を1つ以上選んでください。")
if not settings.importances:
    problems.append("重要度を1つ以上選んでください。")
if settings.formats and settings.importances and not matching:
    problems.append(
        "復習対象の問題がありません。まずは他のモードで解いてみましょう。"
        if mode is QuizMode.REVIEW_MISTAKES
        else "条件に合う問題がありません。"
    )
seed = None
if seed_text.strip():
    try:
        seed = int(seed_text)
    except ValueError:
        problems.append("乱数シードは整数で入力してください。")
for p in problems:
    st.warning(p)

if st.button("クイズを始める", type="primary", width="stretch", disabled=bool(problems)):
    missed = exam_missed_nos() if mode is QuizMode.WEAK_FIRST else frozenset()
    start_quiz(generate_quiz(items, settings, stats, seed=seed, exam_missed_nos=missed), settings)
    st.switch_page("pages/1_クイズ.py")
