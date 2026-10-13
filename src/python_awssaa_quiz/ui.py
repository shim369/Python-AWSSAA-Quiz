"""Streamlit画面で共通に使う処理。Streamlitに依存するのはこのモジュールだけ。"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

from .loader import DEFAULT_EXCEL_PATH, Keyword, load_keywords
from .quiz_engine import Question, QuizItem, QuizSettings, build_items
from .storage import DEFAULT_DB_PATH, HistoryStore

APP_TITLE = "Python-AWSSAA-Quiz"
QUIZ_KEY = "quiz"

_CSS = """
<style>
/* 選択肢: 縦に並べた大きめのボタン。長い文章も折り返して左寄せで読めるように */
[class*="st-key-choices"] button {
    justify-content: flex-start;
    text-align: left;
    min-height: 3.4rem;
    padding: 0.8rem 1rem;
}
[class*="st-key-choices"] button > div,
[class*="st-key-choices"] button [data-testid="stMarkdownContainer"] {
    width: 100%;
    justify-content: flex-start;
    text-align: left;
}
[class*="st-key-choices"] button p {
    font-size: 1.05rem;
    line-height: 1.6;
    text-align: left;
    white-space: normal;
}
/* 問題文 */
.quiz-prompt {
    font-size: 1.2rem;
    line-height: 1.9;
    word-break: break-word;
}
</style>
"""


def setup_page() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="centered")
    st.markdown(_CSS, unsafe_allow_html=True)


_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>#|~$])")


def md_escape(text: str) -> str:
    """データ中の記号がMarkdownとして解釈されないようにする。"""
    return _MD_SPECIAL.sub(r"\\\1", text)


# ---------------------------------------------------------------- データ


@st.cache_data(show_spinner="キーワード集を読み込んでいます…")
def _load_keywords_cached(path: str, mtime: float) -> list[Keyword]:
    # mtime はキャッシュキーとしてだけ使う(Excelが更新されたら読み直す)
    return load_keywords(path)


def get_keywords(path: Path = DEFAULT_EXCEL_PATH) -> list[Keyword]:
    if not path.exists():
        st.error(f"Excelファイルが見つかりません: `{path}`")
        st.stop()
    return _load_keywords_cached(str(path), path.stat().st_mtime)


def get_items() -> list[QuizItem]:
    return build_items(get_keywords())


@st.cache_resource
def get_store(path: str = str(DEFAULT_DB_PATH)) -> HistoryStore:
    return HistoryStore(path)


# ---------------------------------------------------------------- 出題中の状態


@dataclass
class QuizState:
    """出題リスト・選択肢の並び順・現在の問題番号・回答状況をまとめて保持する。
    session_state に入れておくので、再実行されても問題や選択肢は変わらない。"""

    questions: list[Question]
    settings: QuizSettings
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    index: int = 0
    answers: dict[int, int] = field(default_factory=dict)  # 問題番号 → 選んだ選択肢

    @property
    def finished(self) -> bool:
        return len(self.answers) == len(self.questions)

    def correct_count(self) -> int:
        return sum(self.questions[i].is_correct(c) for i, c in self.answers.items())


def start_quiz(questions: list[Question], settings: QuizSettings) -> None:
    st.session_state[QUIZ_KEY] = QuizState(questions=questions, settings=settings)


def current_quiz() -> QuizState | None:
    return st.session_state.get(QUIZ_KEY)


def submit_answer(index: int, choice: int) -> None:
    """選択肢ボタンのコールバック。同じ問題への回答は1回だけ記録する。"""
    quiz = current_quiz()
    if quiz is None or index in quiz.answers:
        return
    quiz.answers[index] = choice
    q = quiz.questions[index]
    get_store().record_answer(
        session_id=quiz.session_id,
        question_index=index,
        item_id=q.item.item_id,
        no=q.item.no,
        keyword=q.item.name,
        category=q.item.category,
        format=q.format.value,
        is_correct=q.is_correct(choice),
    )


def go_next() -> None:
    quiz = current_quiz()
    if quiz is not None and quiz.index in quiz.answers:
        quiz.index += 1
