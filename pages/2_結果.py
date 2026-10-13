"""結果画面。"""

import random

import pandas as pd
import streamlit as st

from python_awssaa_quiz.quiz_engine import questions_for
from python_awssaa_quiz.ui import current_quiz, get_items, md_escape, setup_page, start_quiz

setup_page()
st.title("結果")

quiz = current_quiz()
if quiz is None or not quiz.answers:
    st.info("まだ回答した問題がありません。")
    if st.button("出題設定へ", type="primary"):
        st.switch_page("app.py")
    st.stop()

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
    st.switch_page("pages/1_クイズ.py")
if c2.button("出題設定へ", width="stretch"):
    st.switch_page("app.py")
if c3.button("ダッシュボード", width="stretch"):
    st.switch_page("pages/3_ダッシュボード.py")
