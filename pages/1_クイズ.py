"""クイズ画面。"""

import streamlit as st

from python_awssaa_quiz.quiz_engine import FORMAT_INSTRUCTIONS, QuestionFormat
from python_awssaa_quiz.ui import (
    current_quiz,
    get_items,
    go_next,
    md_escape,
    setup_page,
    submit_answer,
)

setup_page()

quiz = current_quiz()
if quiz is None or not quiz.questions:
    st.info("出題中のクイズはありません。トップ画面で出題設定をしてください。")
    if st.button("出題設定へ", type="primary"):
        st.switch_page("app.py")
    st.stop()

if quiz.index >= len(quiz.questions):
    st.switch_page("pages/2_結果.py")

total = len(quiz.questions)
idx = quiz.index
q = quiz.questions[idx]
LETTERS = "ABCD"

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
    st.stop()

# ---------------------------------------------------------------- 回答後
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

if idx + 1 < total:
    st.button("次の問題へ →", type="primary", width="stretch", on_click=go_next)
else:
    if st.button("結果を見る", type="primary", width="stretch"):
        go_next()
        st.switch_page("pages/2_結果.py")
