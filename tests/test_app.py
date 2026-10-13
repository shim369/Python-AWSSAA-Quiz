"""Streamlit画面の通し動作(AppTestでヘッドレス実行)。"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from python_awssaa_quiz.ui import QUIZ_KEY

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
