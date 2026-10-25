"""本番形式の問題: 出題設定 → 出題 → 結果 を1つの画面で切り替える。"""

import random
import time

import pandas as pd
import streamlit as st

from python_awssaa_quiz.exam_bank import (
    MOCK_EXAM_SIZE,
    PASSING_SCORE,
    SECONDS_PER_QUESTION,
    ExamMode,
    ExamSettings,
    filter_questions,
    generate_exam,
    present,
    scaled_score,
)
from python_awssaa_quiz.exam_guide import GUIDE_URL, TASKS, Domain
from python_awssaa_quiz.quiz_engine import QuizMode
from python_awssaa_quiz.ui import (
    ExamState,
    clear_exam,
    current_exam,
    exam_widget_key,
    finish_exam,
    get_exam_questions,
    get_keywords,
    get_store,
    go_to_exam_question,
    judge_practice,
    md_escape,
    save_multi_choice,
    save_single_choice,
    start_exam,
)

LETTERS = "ABCDEF"


def multiline(text: str) -> str:
    """改行を保ったままMarkdownで表示する。"""
    return "  \n".join(md_escape(line) for line in text.splitlines())


def format_seconds(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}"


def letters(indices) -> str:
    return "・".join(LETTERS[i] for i in sorted(indices)) or "未回答"


# ---------------------------------------------------------------- 出題設定


def render_settings() -> None:
    st.title("本番形式")
    st.caption(
        "試験ガイドのタスクに沿った、シナリオ形式の問題です。"
        "正解が複数の問題(複数選択)も本番と同じく含まれます。"
    )
    st.page_link("pages/使い方.py", label="使い方(練習と模擬試験の違い、タイマーなど)", icon="❓")
    questions = get_exam_questions()
    if not questions:
        st.info(
            "問題がまだありません。`data/exam_questions/` にYAMLで問題を追加してください"
            "(書き方は README を参照)。"
        )
        st.stop()

    stats = get_store().exam_stats()

    with st.expander(f"収録されている問題: {len(questions)}問(タスク別の内訳)"):
        rows = [
            {
                "タスク": t.label,
                "問題数": sum(q.task.id == t.id for q in questions),
                "回答済み": sum(q.task.id == t.id and q.id in stats for q in questions),
            }
            for t in TASKS.values()
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption(f"タスクの区分は [SAA-C03 試験ガイド]({GUIDE_URL}) に沿っています。")

    mode = st.radio(
        "出題モード",
        list(ExamMode),
        format_func=lambda m: m.label,
        horizontal=True,
    )

    if mode is ExamMode.PRACTICE:
        domains = st.multiselect(
            "分野",
            list(Domain),
            format_func=lambda d: d.label,
            placeholder="すべての分野(絞り込む場合は選択)",
        )
        task_options = [t for t in TASKS.values() if not domains or t.domain in domains]
        tasks = st.multiselect(
            "タスク",
            [t.id for t in task_options],
            format_func=lambda tid: TASKS[tid].label,
            placeholder="すべてのタスク(絞り込む場合は選択)",
        )
        count_options = {"10問": 10, "20問": 20, "全問": None}
        count_label = st.segmented_control("問題数", list(count_options), default="10問")
        order = st.radio(
            "問題の選び方",
            list(QuizMode),
            format_func=lambda m: m.label,
            horizontal=True,
            captions=[
                "条件に合う問題からランダムに出題",
                "直近の不正解が多い問題・未回答の問題を優先",
                "直近3回の回答に不正解がある問題だけ",
            ],
        )
        settings = ExamSettings(
            mode=mode,
            domains=tuple(domains),
            tasks=tuple(tasks),
            count=count_options[count_label or "10問"],
            order=order,
        )
        matching = filter_questions(questions, settings, stats)
        n = len(matching) if settings.count is None else min(settings.count, len(matching))
    else:
        count_options = {f"{MOCK_EXAM_SIZE}問(本番と同じ)": MOCK_EXAM_SIZE, "30問": 30, "10問": 10}
        count_label = st.segmented_control(
            "問題数", list(count_options), default=list(count_options)[0]
        )
        timer = st.toggle(
            f"タイマーを使う(1問あたり{SECONDS_PER_QUESTION // 60}分、時間切れで自動的に採点)",
            value=True,
        )
        settings = ExamSettings(
            mode=mode, count=count_options[count_label or list(count_options)[0]], timer=timer
        )
        n = min(settings.count or MOCK_EXAM_SIZE, len(questions))
        matching = questions
        st.caption(
            "全分野から試験ガイドの出題比率(30% / 26% / 24% / 20%)に沿って選び、"
            "分野を混ぜて出題します。途中で答え合わせはせず、最後にまとめて採点します。"
        )

    st.caption(f"今回の出題: {n}問")
    if settings.mode is ExamMode.MOCK and settings.count and n < settings.count:
        st.caption(f"(収録されている問題が{len(questions)}問のため、{settings.count}問より少なくなります)")

    with st.expander("詳細設定"):
        seed_text = st.text_input("乱数シード(空欄ならランダム)", value="", key="exam_seed")

    problems = []
    if not matching:
        problems.append(
            "復習対象の問題がありません。まずは他の選び方で解いてみましょう。"
            if settings.order is QuizMode.REVIEW_MISTAKES and mode is ExamMode.PRACTICE
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

    if st.button("開始する", type="primary", width="stretch", disabled=bool(problems)):
        start_exam(generate_exam(questions, settings, stats, seed=seed), settings)
        st.rerun()


# ---------------------------------------------------------------- 出題


def render_choices(exam: ExamState, idx: int, disabled: bool) -> None:
    pq = exam.questions[idx]
    selected = exam.selected(idx)
    with st.container(key=f"exam_choices_{exam.session_id}_{idx}"):
        if pq.question.answer_count == 1:
            st.radio(
                "選択肢",
                list(range(len(pq.choices))),
                index=selected[0] if selected else None,
                format_func=lambda i: f"{LETTERS[i]}. {md_escape(pq.choices[i].text)}",
                key=exam_widget_key(exam, idx),
                on_change=save_single_choice,
                args=(idx,),
                disabled=disabled,
                label_visibility="collapsed",
            )
        else:
            for i, choice in enumerate(pq.choices):
                st.checkbox(
                    f"{LETTERS[i]}. {md_escape(choice.text)}",
                    value=i in selected,
                    key=exam_widget_key(exam, idx, i),
                    on_change=save_multi_choice,
                    args=(idx, i),
                    disabled=disabled,
                )


def render_question_text(exam: ExamState, idx: int) -> None:
    q = exam.questions[idx].question
    with st.container(border=True):
        st.markdown(multiline(q.question))
    if q.answer_count > 1:
        st.markdown(f"**({q.answer_count}つ選択)**")


def render_review(exam: ExamState, idx: int) -> None:
    """正解と、各選択肢が正解・不正解である理由、解説、関連キーワード。"""
    pq = exam.questions[idx]
    q = pq.question
    selected = set(exam.selected(idx))
    lines = []
    for i, c in enumerate(pq.choices):
        mark = "✅" if c.correct else ("❌" if i in selected else "・")
        lines.append(f"{mark} **{LETTERS[i]}.** {md_escape(c.text)}  \n　→ {md_escape(c.reason)}")
    st.markdown("\n\n".join(lines))
    if q.explanation:
        with st.container(border=True):
            st.markdown(f"**解説**  \n{multiline(q.explanation)}")
    names = {k.no: k.name for k in get_keywords()}
    related = [names[no] for no in q.related_keywords if no in names]
    if related:
        st.caption("関連キーワード: " + " / ".join(md_escape(n) for n in related))


def render_practice(exam: ExamState) -> None:
    total = len(exam.questions)
    idx = exam.index
    pq = exam.questions[idx]
    q = pq.question
    st.progress(
        idx / total,
        text=f"{idx + 1} / {total} 問 ・ 正解 {exam.correct_count()} 問",
    )
    st.caption(f"{q.domain.label} ・ タスク {q.task.label} ・ {q.id}")
    render_question_text(exam, idx)

    judged = idx in exam.judged
    render_choices(exam, idx, disabled=judged)

    if not judged:
        need = q.answer_count
        n_selected = len(exam.selected(idx))
        st.button(
            "回答する",
            type="primary",
            width="stretch",
            on_click=judge_practice,
            args=(idx,),
            disabled=n_selected != need,
            help=None if n_selected == need else f"{need}つ選んでください",
        )
    else:
        if exam.is_correct(idx):
            st.success(f"正解! 答えは **{letters(pq.answer)}**", icon="✅")
        else:
            st.error(
                f"不正解… 正解は **{letters(pq.answer)}**(あなたの回答: {letters(exam.selected(idx))})",
                icon="❌",
            )
        render_review(exam, idx)
        if idx + 1 < total:
            st.button(
                "次の問題へ →",
                type="primary",
                width="stretch",
                on_click=go_to_exam_question,
                args=(idx + 1,),
            )
        else:
            st.button("結果を見る", type="primary", width="stretch", on_click=finish_exam)

    if exam.judged and not (judged and idx + 1 == total):
        st.button("ここで終了して結果を見る", on_click=finish_exam)


@st.fragment(run_every=1)
def render_timer() -> None:
    exam = current_exam()
    if exam is None or exam.finished:
        return
    remaining = exam.remaining_seconds()
    if remaining is None:
        st.caption(f"経過時間 {format_seconds(time.time() - exam.started_at)}(タイマーOFF)")
        return
    if remaining <= 0:
        finish_exam()
        st.rerun()
    text = f"⏱ 残り時間 **{format_seconds(remaining)}**"
    if remaining < 5 * 60:
        st.warning(text)
    else:
        st.markdown(text)


def render_mock(exam: ExamState) -> None:
    total = len(exam.questions)
    idx = exam.index
    answered = sum(1 for i in range(total) if exam.selected(i))

    render_timer()
    st.progress(answered / total, text=f"問題 {idx + 1} / {total} ・ 回答済み {answered} 問")
    render_question_text(exam, idx)
    render_choices(exam, idx, disabled=False)

    c1, c2 = st.columns(2)
    c1.button(
        "← 前へ", width="stretch", disabled=idx == 0,
        on_click=go_to_exam_question, args=(idx - 1,),
    )
    c2.button(
        "次へ →", width="stretch", disabled=idx + 1 == total, type="primary",
        on_click=go_to_exam_question, args=(idx + 1,),
    )

    with st.expander("問題一覧(番号を押すと移動。色付きは回答済み)"):
        per_row = 10
        for start in range(0, total, per_row):
            cols = st.columns(per_row)
            for offset, i in enumerate(range(start, min(start + per_row, total))):
                cols[offset].button(
                    str(i + 1),
                    key=f"jump_{exam.session_id}_{i}",
                    type="primary" if exam.selected(i) else "secondary",
                    on_click=go_to_exam_question,
                    args=(i,),
                    width="stretch",
                )

    st.divider()
    unanswered = total - answered
    if unanswered:
        st.caption(f"未回答が{unanswered}問あります。未回答の問題は不正解として採点されます。")
    st.button("試験を終了して採点する", width="stretch", on_click=finish_exam)


# ---------------------------------------------------------------- 結果


def render_result(exam: ExamState) -> None:
    st.title("本番形式の結果")
    indices = exam.scored_indices()
    if not indices:
        st.info("答え合わせした問題がありません。")
        st.button("出題設定へ", type="primary", on_click=clear_exam)
        return

    correct = exam.correct_count()
    total = len(indices)
    if exam.mode is ExamMode.MOCK:
        score = scaled_score(correct, total)
        c1, c2, c3 = st.columns(3)
        c1.metric("スコア(目安)", f"{score} / 1000")
        c2.metric("正答率", f"{correct / total:.0%}")
        c3.metric("正解数", f"{correct} / {total} 問")
        if score >= PASSING_SCORE:
            st.success(f"合格ライン({PASSING_SCORE}点)を超えています", icon="🎉")
        else:
            st.error(f"合格ライン({PASSING_SCORE}点)まであと {PASSING_SCORE - score} 点", icon="📚")
        st.caption(
            "スコアは正答率からの単純換算です。本番は採点対象50問+採点対象外15問で、"
            "問題ごとの難易度を反映したスケールスコア(100〜1000点)で判定されます。"
        )
    else:
        c1, c2 = st.columns(2)
        c1.metric("正答率", f"{correct / total:.0%}")
        c2.metric("正解数", f"{correct} / {total} 問")

    df = pd.DataFrame(
        {
            "分野": exam.questions[i].question.domain.label,
            "タスク": exam.questions[i].question.task.label,
            "正解": exam.is_correct(i),
        }
        for i in indices
    )
    progress = st.column_config.ProgressColumn("正答率", format="percent", min_value=0, max_value=1)
    for key in ("分野", "タスク"):
        st.subheader(f"{key}別の正答率")
        g = df.groupby(key, sort=False)["正解"].agg(回答数="count", 正解数="sum").reset_index()
        g["正答率"] = g["正解数"] / g["回答数"]
        st.dataframe(g, hide_index=True, width="stretch", column_config={"正答率": progress})

    st.subheader("問題ごとの解説")
    wrong = [i for i in indices if not exam.is_correct(i)]
    only_wrong = st.toggle("間違えた問題だけ表示", value=bool(wrong))
    for i in indices:
        if only_wrong and i not in wrong:
            continue
        q = exam.questions[i].question
        mark = "✅" if exam.is_correct(i) else "❌"
        with st.expander(f"{mark} 問{i + 1}  {q.task.label}"):
            st.markdown(multiline(q.question))
            st.caption(
                f"あなたの回答: {letters(exam.selected(i))} ・ 正解: {letters(exam.questions[i].answer)}"
            )
            render_review(exam, i)

    st.divider()
    c1, c2, c3 = st.columns(3)
    if wrong and c1.button("間違えた問題を練習で解き直す", type="primary", width="stretch"):
        rng = random.Random()
        retry = [exam.questions[i].question for i in wrong]
        rng.shuffle(retry)
        start_exam([present(q, rng) for q in retry], ExamSettings(mode=ExamMode.PRACTICE))
        st.rerun()
    c2.button("出題設定へ", width="stretch", on_click=clear_exam)
    if c3.button("ダッシュボード", width="stretch"):
        st.switch_page("pages/ダッシュボード.py")


# ---------------------------------------------------------------- 画面の切り替え

exam = current_exam()
if exam is not None and not exam.finished:
    remaining = exam.remaining_seconds()
    if remaining is not None and remaining <= 0:
        finish_exam()

if exam is None:
    render_settings()
elif exam.finished:
    render_result(exam)
elif exam.mode is ExamMode.MOCK:
    render_mock(exam)
else:
    render_practice(exam)
