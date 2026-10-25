"""ダッシュボード: 学習状況の集計とExcelへの書き戻し。"""

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from python_awssaa_quiz.exam_bank import PASSING_SCORE, ExamBankError, scaled_score
from python_awssaa_quiz.exam_guide import TASKS, Domain
from python_awssaa_quiz.excel_writer import judge_understanding, write_understanding
from python_awssaa_quiz.loader import DEFAULT_EXCEL_PATH
from python_awssaa_quiz.ui import KEYWORD_PAGE, get_keywords, get_store, load_exam_bank

SERIES_COLOR = "#2a78d6"  # 系列が1つのグラフで共通に使う色

st.title("ダッシュボード")

keywords = get_keywords()
store = get_store()
answers = store.answers_df()
exam_answers = store.exam_answers_df()

if answers.empty and exam_answers.empty:
    st.info("まだ回答履歴がありません。クイズを解くとここに学習状況が表示されます。")
    if st.button("出題設定へ", type="primary"):
        st.switch_page(KEYWORD_PAGE)
    st.stop()


def render_exam_section() -> None:
    """本番形式の学習状況: 模擬試験のスコア推移と、分野・タスク別の正答率。"""
    st.header("本番形式")
    if exam_answers.empty:
        st.info("まだ本番形式の問題に回答していません。")
        return
    try:
        bank = {q.id: q for q in load_exam_bank()}
    except ExamBankError as e:
        st.error(f"本番形式の問題データに誤りがあります: {e}")
        return

    mocks = store.mock_exam_results()
    st.subheader("模擬試験のスコア(目安)")
    if mocks.empty:
        st.caption("まだ模擬試験を受けていません。")
    else:
        mocks["スコア"] = [scaled_score(c, n) for c, n in zip(mocks["正解数"], mocks["問題数"])]
        mocks["回"] = [f"{i + 1}回目" for i in range(len(mocks))]
        c1, c2, c3 = st.columns(3)
        c1.metric("受験回数", f"{len(mocks)} 回")
        c2.metric("最新スコア", f"{mocks['スコア'].iloc[-1]}")
        c3.metric("最高スコア", f"{mocks['スコア'].max()}")
        x_mock = alt.X("回:O", title=None, sort=list(mocks["回"]), axis=alt.Axis(labelAngle=0))
        base = alt.Chart(mocks).encode(
            x=x_mock,
            y=alt.Y("スコア:Q", scale=alt.Scale(domain=[0, 1000]), title="スコア"),
            tooltip=[
                alt.Tooltip("日時:T", format="%Y/%m/%d %H:%M"),
                alt.Tooltip("スコア:Q"),
                alt.Tooltip("正解数:Q"),
                alt.Tooltip("問題数:Q"),
            ],
        )
        passing = (
            alt.Chart(pd.DataFrame({"y": [PASSING_SCORE]}))
            .mark_rule(strokeDash=[4, 4], color="#888")
            .encode(y="y:Q")
        )
        chart = (
            base.mark_line(color=SERIES_COLOR, strokeWidth=2)
            + base.mark_point(color=SERIES_COLOR, filled=True, size=64)
            + passing
        ).properties(height=200)
        st.altair_chart(chart, width="stretch")
        st.caption(f"点線は合格ライン({PASSING_SCORE}点)。スコアは正答率からの単純換算です。")

    known = exam_answers[exam_answers["question_id"].isin(bank)].copy()
    known["分野"] = [bank[q].domain.label for q in known["question_id"]]
    known["タスク"] = [bank[q].task.label for q in known["question_id"]]
    progress = st.column_config.ProgressColumn("正答率", format="percent", min_value=0, max_value=1)

    st.subheader("分野別の正答率")
    by_domain = known.groupby("分野")["is_correct"].agg(回答数="count", 正答率="mean")
    by_domain = by_domain.reindex([d.label for d in Domain]).dropna().reset_index()
    st.dataframe(by_domain, hide_index=True, width="stretch", column_config={"正答率": progress})

    st.subheader("タスク別の正答率と問題の収録状況")
    by_task = known.groupby("タスク")["is_correct"].agg(回答数="count", 正答率="mean")
    rows = []
    for t in TASKS.values():
        n_questions = sum(q.task.id == t.id for q in bank.values())
        stat = by_task.loc[t.label] if t.label in by_task.index else None
        rows.append(
            {
                "タスク": t.label,
                "収録問題数": n_questions,
                "回答数": 0 if stat is None else int(stat["回答数"]),
                "正答率": None if stat is None else stat["正答率"],
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={"正答率": progress})
    st.caption("収録問題数が少ないタスクは、問題を追加すると本番の出題範囲をまんべんなく練習できます。")


if answers.empty:
    render_exam_section()
    st.stop()

st.header("キーワードクイズ")

# ---------------------------------------------------------------- 概要
learned = len(store.answered_nos() & {k.no for k in keywords})
c1, c2, c3 = st.columns(3)
c1.metric("学習済みキーワード", f"{learned} / {len(keywords)}")
c2.metric("総回答数", f"{len(answers):,}")
c3.metric("全体の正答率", f"{answers['is_correct'].mean():.0%}")
st.progress(learned / len(keywords), text=f"学習済み {learned / len(keywords):.0%}")

# ---------------------------------------------------------------- 分野別の正答率
st.subheader("分野別の正答率")
category_order = list(dict.fromkeys(k.category for k in keywords))
by_cat = store.category_accuracy()
cat_chart = (
    alt.Chart(by_cat)
    .mark_bar(color=SERIES_COLOR, cornerRadiusEnd=4, height={"band": 0.6})
    .encode(
        x=alt.X("正答率:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%", tickCount=5)),
        y=alt.Y("分野:N", sort=category_order, title=None, axis=alt.Axis(labelLimit=200)),
        tooltip=[
            alt.Tooltip("分野:N"),
            alt.Tooltip("正答率:Q", format=".0%"),
            alt.Tooltip("回答数:Q"),
        ],
    )
    .properties(height=alt.Step(28))
)
st.altair_chart(cat_chart, width="stretch")
with st.expander("表で見る"):
    st.dataframe(
        by_cat,
        hide_index=True,
        width="stretch",
        column_config={"正答率": st.column_config.NumberColumn(format="percent")},
    )

# ---------------------------------------------------------------- 日別の推移
st.subheader("日別の回答数と正答率")
daily = store.daily_summary()
daily["日"] = daily["日付"].dt.strftime("%m/%d")
# 年をまたいでも日付順に並ぶよう、並び順を明示する
x = alt.X("日:O", title=None, sort=list(daily["日"]), axis=alt.Axis(labelAngle=0))
count_chart = (
    alt.Chart(daily)
    .mark_bar(color=SERIES_COLOR, cornerRadiusEnd=4, width={"band": 0.6})
    .encode(
        x=x,
        y=alt.Y("回答数:Q", title="回答数"),
        tooltip=[alt.Tooltip("日付:T", format="%Y/%m/%d"), alt.Tooltip("回答数:Q")],
    )
    .properties(height=180)
)
acc_base = alt.Chart(daily).encode(
    x=x,
    y=alt.Y("正答率:Q", title="正答率", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
    tooltip=[alt.Tooltip("日付:T", format="%Y/%m/%d"), alt.Tooltip("正答率:Q", format=".0%")],
)
acc_chart = (
    acc_base.mark_line(color=SERIES_COLOR, strokeWidth=2)
    + acc_base.mark_point(color=SERIES_COLOR, filled=True, size=64)
).properties(height=180)
# 単位の違う2つの値は軸を共有せず、別々のグラフにする
st.altair_chart(count_chart, width="stretch")
st.altair_chart(acc_chart, width="stretch")
with st.expander("表で見る"):
    st.dataframe(
        daily.drop(columns="日").assign(日付=daily["日付"].dt.date),
        hide_index=True,
        width="stretch",
        column_config={"正答率": st.column_config.NumberColumn(format="percent")},
    )

# ---------------------------------------------------------------- Excelへの書き戻し
st.subheader("Excelの「理解度」を更新")
levels = {
    no: level
    for no, results in store.results_by_no().items()
    if (level := judge_understanding(results)) is not None
}
counts = {m: sum(1 for v in levels.values() if v == m) for m in "◎○△"}
st.markdown(
    "直近3回すべて正解 → **◎**、直近3回に1回でも正解 → **○**、それ以外 → **△** "
    "(未回答のキーワードは変更しません)"
)
st.caption(
    f"判定結果: ◎ {counts['◎']}件 ・ ○ {counts['○']}件 ・ △ {counts['△']}件 / "
    f"元ファイルは上書きせず `_updated_YYYYMMDD.xlsx` を付けた別名で保存します"
)

if st.button("理解度を判定してExcelに書き戻す", type="primary", disabled=not levels):
    try:
        dest, n = write_understanding(DEFAULT_EXCEL_PATH, levels)
    except PermissionError:
        st.error("保存できませんでした。同じ名前のファイルをExcelで開いている場合は閉じてください。")
    else:
        st.session_state["written_excel"] = str(dest)
        st.success(f"{n}件の理解度を書き込み、`{dest.name}` に保存しました。")

written = st.session_state.get("written_excel")
if written:
    path = Path(written)
    if path.exists():
        st.download_button(
            f"{path.name} をダウンロード",
            data=path.read_bytes(),
            file_name=path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )

render_exam_section()
