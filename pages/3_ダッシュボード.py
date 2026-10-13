"""ダッシュボード: 学習状況の集計とExcelへの書き戻し。"""

from pathlib import Path

import altair as alt
import streamlit as st

from python_awssaa_quiz.excel_writer import judge_understanding, write_understanding
from python_awssaa_quiz.loader import DEFAULT_EXCEL_PATH
from python_awssaa_quiz.ui import get_keywords, get_store, setup_page

SERIES_COLOR = "#2a78d6"  # 系列が1つのグラフで共通に使う色

setup_page()
st.title("ダッシュボード")

keywords = get_keywords()
store = get_store()
answers = store.answers_df()

if answers.empty:
    st.info("まだ回答履歴がありません。クイズを解くとここに学習状況が表示されます。")
    if st.button("出題設定へ", type="primary"):
        st.switch_page("app.py")
    st.stop()

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
