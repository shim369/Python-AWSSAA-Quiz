"""Streamlit画面で共通に使う処理。Streamlitに依存するのはこのモジュールだけ。"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

from .exam_bank import (
    DEFAULT_EXAM_DIR,
    ExamBankError,
    ExamMode,
    ExamQuestion,
    ExamSettings,
    PresentedQuestion,
    exam_files,
    load_exam_questions,
    make_answer,
    missed_keyword_nos,
    time_limit_seconds,
)
from .loader import DEFAULT_EXCEL_PATH, Keyword, load_keywords
from .quiz_engine import Question, QuizItem, QuizSettings, build_items
from .storage import DEFAULT_DB_PATH, HistoryStore

APP_TITLE = "Python-AWSSAA-Quiz"
QUIZ_KEY = "quiz"
EXAM_KEY = "exam"

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
/* 本番形式の選択肢: 長い文章を読みやすく */
[class*="st-key-exam_choices"] label p {
    font-size: 1.02rem;
    line-height: 1.6;
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


@st.cache_data(show_spinner="本番形式の問題を読み込んでいます…")
def _load_exam_cached(path: str, mtimes: tuple[float, ...]) -> list[ExamQuestion]:
    # mtimes はキャッシュキーとしてだけ使う(YAMLが更新されたら読み直す)
    return load_exam_questions(path)


def load_exam_bank(path: Path = DEFAULT_EXAM_DIR) -> list[ExamQuestion]:
    """問題データを読み込む。書き方に誤りがあれば ExamBankError。"""
    mtimes = tuple(p.stat().st_mtime for p in exam_files(path))
    return _load_exam_cached(str(path), mtimes)


def get_exam_questions(path: Path = DEFAULT_EXAM_DIR) -> list[ExamQuestion]:
    """問題データを読み込む。誤りがあれば画面にエラーを出して止める。"""
    try:
        return load_exam_bank(path)
    except ExamBankError as e:
        st.error(f"本番形式の問題データに誤りがあります: {e}")
        st.stop()


def exam_missed_nos() -> frozenset[int]:
    """本番形式で最後に間違えた問題の関連キーワード(キーワードクイズの弱点優先に使う)。"""
    try:
        questions = load_exam_bank()
    except ExamBankError:
        return frozenset()
    return missed_keyword_nos(questions, get_store().exam_stats())


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


# ---------------------------------------------------------------- 本番形式の状態


@dataclass
class ExamState:
    """本番形式の出題リスト・回答・進み具合。session_state に入れて再実行でも保つ。
    selections と judged の番号は、表示上の選択肢の位置。"""

    questions: list[PresentedQuestion]
    settings: ExamSettings
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    index: int = 0
    selections: dict[int, tuple[int, ...]] = field(default_factory=dict)
    judged: set[int] = field(default_factory=set)  # 練習で答え合わせした問題
    started_at: float = field(default_factory=time.time)
    deadline: float | None = None  # 模擬試験の終了時刻(タイマーOFFならNone)
    finished: bool = False

    @property
    def mode(self) -> ExamMode:
        return self.settings.mode

    def selected(self, index: int) -> tuple[int, ...]:
        return self.selections.get(index, ())

    def is_correct(self, index: int) -> bool:
        return self.questions[index].is_correct(self.selected(index))

    def scored_indices(self) -> list[int]:
        """採点対象の問題番号。模擬試験は全問(未回答は不正解)、練習は答え合わせした問題。"""
        if self.mode is ExamMode.MOCK:
            return list(range(len(self.questions)))
        return sorted(self.judged)

    def correct_count(self) -> int:
        return sum(self.is_correct(i) for i in self.scored_indices())

    def remaining_seconds(self) -> float | None:
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - time.time())


def start_exam(questions: list[PresentedQuestion], settings: ExamSettings) -> None:
    state = ExamState(questions=questions, settings=settings)
    if settings.mode is ExamMode.MOCK and settings.timer:
        state.deadline = state.started_at + time_limit_seconds(len(questions))
    st.session_state[EXAM_KEY] = state


def current_exam() -> ExamState | None:
    return st.session_state.get(EXAM_KEY)


def clear_exam() -> None:
    st.session_state.pop(EXAM_KEY, None)


def exam_widget_key(exam: ExamState, index: int, choice: int | None = None) -> str:
    base = f"exam_{exam.session_id}_{index}"
    return base if choice is None else f"{base}_{choice}"


def save_single_choice(index: int) -> None:
    """ラジオボタン(正解1つの問題)のコールバック。"""
    exam = current_exam()
    if exam is None or index in exam.judged or exam.finished:
        return
    value = st.session_state.get(exam_widget_key(exam, index))
    exam.selections[index] = () if value is None else (value,)


def save_multi_choice(index: int, choice: int) -> None:
    """チェックボックス(正解が複数の問題)のコールバック。"""
    exam = current_exam()
    if exam is None or index in exam.judged or exam.finished:
        return
    chosen = set(exam.selected(index))
    if st.session_state.get(exam_widget_key(exam, index, choice)):
        chosen.add(choice)
    else:
        chosen.discard(choice)
    exam.selections[index] = tuple(sorted(chosen))


def judge_practice(index: int) -> None:
    """練習の「回答する」ボタン。同じ問題の答え合わせと記録は1回だけ。"""
    exam = current_exam()
    if exam is None or index in exam.judged or not exam.selected(index):
        return
    exam.judged.add(index)
    get_store().record_exam_answers(
        [make_answer(exam.session_id, index, exam.questions[index], exam.selected(index), exam.mode)]
    )


def finish_exam() -> None:
    """模擬試験を採点して履歴に記録する(未回答は不正解として記録)。練習は終了するだけ。"""
    exam = current_exam()
    if exam is None or exam.finished:
        return
    exam.finished = True
    if exam.mode is ExamMode.MOCK:
        get_store().record_exam_answers(
            [
                make_answer(exam.session_id, i, pq, exam.selected(i), exam.mode)
                for i, pq in enumerate(exam.questions)
            ]
        )


def go_to_exam_question(index: int) -> None:
    exam = current_exam()
    if exam is not None and 0 <= index < len(exam.questions):
        exam.index = index
