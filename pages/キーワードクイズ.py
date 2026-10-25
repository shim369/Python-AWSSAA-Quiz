"""キーワードクイズ: 出題設定 → 出題 → 結果 を1つの画面で切り替える。"""

import random

import pandas as pd
import streamlit as st

from python_awssaa_quiz.quiz_engine import (
    FORMAT_INSTRUCTIONS,
    QuestionFormat,
    QuizMode,
    QuizSettings,
    filter_items,
    generate_quiz,
    needs_review,
    questions_for,
)
from python_awssaa_quiz.ui import (
    APP_TITLE,
    QuizState,
    clear_quiz,
    current_quiz,
    end_quiz,
    exam_missed_nos,
    get_items,
    get_store,
    go_next,
    md_escape,
    start_quiz,
    submit_answer,
)

LETTERS = "ABCD"

# ---------------------------------------------------------------- 出題設定


def render_settings() -> None:
    st.title(APP_TITLE)
    st.caption("AWS 認定ソリューションアーキテクト – アソシエイト(SAA-C03)キーワード4択クイズ")

    items = get_items()
    store = get_store()

    c1, c2 = st.columns(2)
    c1.page_link(
        "pages/本番形式.py",
        label="本番形式の問題(シナリオ問題・模擬試験)はこちら",
        icon="📝",
    )
    c2.page_link("pages/使い方.py", label="使い方", icon="❓")

    categories = list(dict.fromkeys(it.category for it in items))
    star_options = {"★★★": 3, "★★": 2, "★": 1}
    count_options = {"10問": 10, "20問": 20, "50問": 50, "全問": None}

    st.subheader("出題設定")

    selected_categories = st.multiselect(
        "分野", categories, placeholder="すべての分野(絞り込む場合は選択)"
    )
    selected_stars = st.pills(
        "重要度", list(star_options), selection_mode="multi", default=list(star_options)
    )
    selected_formats = st.pills(
        "出題形式",
        list(QuestionFormat),
        selection_mode="multi",
        default=[QuestionFormat.SUMMARY_TO_KEYWORD],
        format_func=lambda f: f.label,
        help="複数選ぶと、問題ごとにランダムで形式が決まります",
    )
    count_label = st.segmented_control("問題数", list(count_options), default="10問")
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
        importances=tuple(star_options[s] for s in selected_stars or []),
        formats=tuple(selected_formats or []),
        count=count_options[count_label or "10問"],
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
        st.rerun()


# ---------------------------------------------------------------- 出題


def render_quiz(quiz: QuizState) -> None:
    total = len(quiz.questions)
    idx = quiz.index
    q = quiz.questions[idx]

    st.progress(idx / total, text=f"{idx + 1} / {total} 問 ・ 正解 {quiz.correct_count()} 問")
    st.caption(f"{q.item.category} ・ {'★' * q.item.importance} ・ {q.format.label}")

    st.markdown(f"**{FORMAT_INSTRUCTIONS[q.format]}**")
    with st.container(border=True):
        st.markdown(f'<div class="quiz-prompt">{md_escape(q.prompt)}</div>', unsafe_allow_html=True)

    chosen = quiz.answers.get(idx)

    if chosen is None:
        # 選択肢(キーにセッションIDと問題番号を含め、別の問題のボタンと混ざらないようにする)
        with st.container(key=f"choices_{quiz.session_id}_{idx}"):
            for i, text in enumerate(q.choices):
                st.button(
                    f"{LETTERS[i]}. {md_escape(text)}",
                    key=f"choice_{quiz.session_id}_{idx}_{i}",
                    on_click=submit_answer,
                    args=(idx, i),
                    width="stretch",
                )
    else:
        render_answer(quiz, idx, chosen)
        if idx + 1 < total:
            st.button("次の問題へ →", type="primary", width="stretch", on_click=go_next)
        else:
            st.button("結果を見る", type="primary", width="stretch", on_click=end_quiz)

    st.divider()
    c1, c2 = st.columns(2)
    if quiz.answers and not (chosen is not None and idx + 1 == total):
        c1.button("ここで終了して結果を見る", width="stretch", on_click=end_quiz)
    c2.button("中断して出題設定へ", width="stretch", on_click=clear_quiz)


def render_answer(quiz: QuizState, idx: int, chosen: int) -> None:
    """回答後の正誤と、そのキーワードの概要・頻出ポイント。"""
    q = quiz.questions[idx]
    items_by_id = {it.item_id: it for it in get_items()}

    if q.is_correct(chosen):
        st.success(f"正解! 答えは **{LETTERS[q.answer_index]}. {md_escape(q.item.name)}**", icon="✅")
    else:
        st.error(
            f"不正解… 正解は **{LETTERS[q.answer_index]}**(あなたの回答: {LETTERS[chosen]})",
            icon="❌",
        )

    lines = []
    for i, (text, cid) in enumerate(zip(q.choices, q.choice_item_ids)):
        mark = "✅" if i == q.answer_index else ("❌" if i == chosen else "・")
        line = f"{mark} {LETTERS[i]}. {md_escape(text)}"
        if q.format is QuestionFormat.KEYWORD_TO_SUMMARY and cid in items_by_id:
            line += f" ― *{md_escape(items_by_id[cid].name)}*"
        lines.append(line)
    st.markdown("  \n".join(lines))

    with st.container(border=True):
        st.markdown(f"#### {md_escape(q.item.name)}")
        st.caption(f"No.{q.item.no} ・ {q.item.category} ・ {'★' * q.item.importance}")
        st.markdown(f"**概要**  \n{md_escape(q.item.summary)}")
        st.markdown(f"**試験での頻出ポイント**  \n{md_escape(q.item.exam_point)}")


# ---------------------------------------------------------------- 結果


def render_result(quiz: QuizState) -> None:
    st.title("結果")

    answered = [(quiz.questions[i], c) for i, c in sorted(quiz.answers.items())]
    correct = sum(q.is_correct(c) for q, c in answered)
    total = len(answered)

    if not quiz.finished:
        st.warning(f"途中までの結果です({total}/{len(quiz.questions)}問回答)")

    col1, col2 = st.columns(2)
    col1.metric("正答率", f"{correct / total:.0%}")
    col2.metric("正解数", f"{correct} / {total} 問")

    st.subheader("分野別の正答率")
    df = pd.DataFrame(
        {"分野": q.item.category, "正解": q.is_correct(c)} for q, c in answered
    )
    by_cat = (
        df.groupby("分野", sort=False)["正解"].agg(回答数="count", 正解数="sum").reset_index()
    )
    by_cat["正答率"] = by_cat["正解数"] / by_cat["回答数"]
    st.dataframe(
        by_cat,
        hide_index=True,
        width="stretch",
        column_config={
            "正答率": st.column_config.ProgressColumn("正答率", format="percent", min_value=0, max_value=1)
        },
    )

    st.subheader("間違えた問題")
    wrong = [(q, c) for q, c in answered if not q.is_correct(c)]
    if not wrong:
        st.success("全問正解です!", icon="🎉")
    for q, c in wrong:
        with st.expander(f"{md_escape(q.item.name)}({q.item.category})"):
            st.caption(f"{q.format.label} ・ あなたの回答: {md_escape(q.choices[c])}")
            st.markdown(f"**問題文**  \n{md_escape(q.prompt)}")
            st.markdown(f"**概要**  \n{md_escape(q.item.summary)}")
            st.markdown(f"**試験での頻出ポイント**  \n{md_escape(q.item.exam_point)}")

    st.divider()
    c1, c2, c3 = st.columns(3)
    if wrong and c1.button("間違えた問題をもう一度", type="primary", width="stretch"):
        rng = random.Random()
        selected = [q.item for q, _ in wrong]
        rng.shuffle(selected)
        start_quiz(questions_for(selected, get_items(), quiz.settings.formats, rng), quiz.settings)
        st.rerun()
    c2.button("出題設定へ", width="stretch", on_click=clear_quiz)
    if c3.button("ダッシュボード", width="stretch"):
        st.switch_page("pages/ダッシュボード.py")


# ---------------------------------------------------------------- 画面の切り替え

quiz = current_quiz()
if quiz is None or not quiz.questions:
    render_settings()
elif quiz.ended:
    render_result(quiz)
else:
    render_quiz(quiz)
