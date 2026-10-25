"""起動用のスクリプト。画面の一覧とサイドバーの並びを決める。起動: uv run streamlit run app.py"""

import streamlit as st

from python_awssaa_quiz.ui import KEYWORD_PAGE, setup_page

setup_page()
st.navigation(
    [
        st.Page(KEYWORD_PAGE, title="キーワードクイズ", icon="🔤", default=True),
        st.Page("pages/本番形式.py", title="本番形式", icon="📝"),
        st.Page("pages/ダッシュボード.py", title="ダッシュボード", icon="📊"),
        st.Page("pages/使い方.py", title="使い方", icon="❓"),
    ]
).run()
