"""Streamlit画面の通し動作(AppTestでヘッドレス実行)。"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from python_awssaa_quiz.ui import EXAM_KEY, QUIZ_KEY, exam_widget_key

TIMEOUT = 30
APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture
def db_path(tmp_path, monkeypatch, excel_path):
    path = tmp_path / "history.db"
    monkeypatch.setenv("AWSSAA_QUIZ_DB", str(path))
    # storage.DEFAULT_DB_PATH は import 時に決まるため、直接差し替える
    import python_awssaa_quiz.storage as storage
    import python_awssaa_quiz.ui as ui

    monkeypatch.setattr(storage, "DEFAULT_DB_PATH", path)
    ui.get_store.clear()
    monkeypatch.setattr(ui, "get_store", lambda: storage.HistoryStore(path))
    return path


def _button(at, label):
    return next(b for b in at.button if b.label.startswith(label))


def test_quiz_flow_keeps_state_and_records_once(db_path):
    from python_awssaa_quiz.storage import HistoryStore

    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    assert not at.exception
    assert at.title[0].value == "Python-AWSSAA-Quiz"
    at.text_input[0].input("1")  # 乱数シード
    _button(at, "クイズを始める").click().run()
    assert not at.exception

    quiz = at.session_state[QUIZ_KEY]
    assert len(quiz.questions) == 10

    at.switch_page("pages/1_クイズ.py").run()
    choices_before = [b.label for b in at.button]
    at.run()  # 再実行しても問題・選択肢は変わらない
    assert [b.label for b in at.button] == choices_before

    for i in range(10):
        q = quiz.questions[i]
        at.button[q.answer_index if i % 2 == 0 else (q.answer_index + 1) % 4].click().run()
        assert not at.exception
        assert at.session_state[QUIZ_KEY].answers[i] is not None
        # 回答後の解説に概要と頻出ポイントが表示される
        text = " ".join(m.value for m in at.markdown)
        assert "概要" in text and "試験での頻出ポイント" in text
        at.run()  # 回答後に再実行しても二重記録されない
        if i < 9:
            _button(at, "次の問題へ").click().run()

    assert len(HistoryStore(db_path).answers_df()) == 10
    assert at.session_state[QUIZ_KEY].correct_count() == 5

    at.switch_page("pages/2_結果.py").run()
    assert not at.exception
    assert any(m.value == "50%" for m in at.metric)

    at.switch_page("pages/3_ダッシュボード.py").run()
    assert not at.exception


# ---------------------------------------------------------------- 本番形式

EXAM_PAGE = "pages/4_本番形式.py"


def _open_exam_page():
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    at.switch_page(EXAM_PAGE).run()
    assert not at.exception
    return at


def _answer(at, exam, idx, correct):
    """表示中の問題に、正解(または不正解)の選択肢を選ぶ。"""
    pq = exam.questions[idx]
    answer = sorted(pq.answer)
    if pq.question.answer_count == 1:
        choice = answer[0] if correct else (answer[0] + 1) % len(pq.choices)
        at.radio(key=exam_widget_key(exam, idx)).set_value(choice).run()
    else:
        picks = answer if correct else [i for i in range(len(pq.choices)) if i not in answer][:2]
        for i in picks:
            at.checkbox(key=exam_widget_key(exam, idx, i)).check().run()
    assert not at.exception


def test_exam_practice_flow_records_once(db_path):
    from python_awssaa_quiz.storage import HistoryStore

    at = _open_exam_page()
    at.text_input(key="exam_seed").input("1")
    _button(at, "開始する").click().run()
    exam = at.session_state[EXAM_KEY]
    total = len(exam.questions)
    assert total == 10

    for i in range(total):
        assert _button(at, "回答する").disabled  # 選ぶまでは回答できない
        _answer(at, exam, i, correct=i % 2 == 0)
        _button(at, "回答する").click().run()
        assert not at.exception
        text = " ".join(m.value for m in at.markdown)
        assert "解説" in text  # 回答後に各選択肢の理由と解説が出る
        at.run()  # 再実行しても二重記録されない
        _button(at, "次の問題へ" if i < total - 1 else "結果を見る").click().run()

    assert len(HistoryStore(db_path).exam_answers_df()) == total
    assert any(m.value == "50%" for m in at.metric)

    at.switch_page("pages/3_ダッシュボード.py").run()
    assert not at.exception


def test_exam_mock_flow_without_timer(db_path):
    from python_awssaa_quiz.exam_bank import ExamMode
    from python_awssaa_quiz.storage import HistoryStore

    at = _open_exam_page()
    at.radio[0].set_value(ExamMode.MOCK).run()
    at.toggle[0].set_value(False).run()
    _button(at, "開始する").click().run()
    exam = at.session_state[EXAM_KEY]
    assert exam.deadline is None
    total = len(exam.questions)

    # 半分だけ正解し、残りは未回答のまま採点する(途中で答え合わせは出ない)
    half = total // 2
    for i in range(half):
        _answer(at, exam, i, correct=True)
        assert "解説" not in " ".join(m.value for m in at.markdown)
        _button(at, "次へ").click().run()
    _button(at, "← 前へ").click().run()  # 戻っても選んだ回答が残っている
    assert exam.selected(half - 1)
    _button(at, "試験を終了して採点する").click().run()
    assert not at.exception

    df = HistoryStore(db_path).exam_answers_df()
    assert len(df) == total and df["is_correct"].sum() == half
    assert set(df["mode"]) == {"mock"}
    at.run()
    assert len(HistoryStore(db_path).exam_answers_df()) == total

    at.switch_page("pages/3_ダッシュボード.py").run()
    assert not at.exception


def test_exam_mock_finishes_when_time_is_up(db_path):
    import time

    from python_awssaa_quiz.exam_bank import ExamMode
    from python_awssaa_quiz.storage import HistoryStore

    at = _open_exam_page()
    at.radio[0].set_value(ExamMode.MOCK).run()
    _button(at, "開始する").click().run()
    exam = at.session_state[EXAM_KEY]
    assert exam.deadline is not None
    exam.deadline = time.time() - 1
    at.run()
    assert not at.exception
    assert at.session_state[EXAM_KEY].finished
    assert len(HistoryStore(db_path).exam_answers_df()) == len(exam.questions)
