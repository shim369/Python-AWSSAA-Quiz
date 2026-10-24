from datetime import datetime

from python_awssaa_quiz.storage import HistoryStore


def _record(store, session, idx, item_id, ok, when, no=None):
    return store.record_answer(
        session_id=session,
        question_index=idx,
        item_id=item_id,
        no=no or int(item_id.split("-")[0]),
        keyword=f"kw{item_id}",
        category="分析" if item_id == "1" else "移行",
        format="summary_to_keyword",
        is_correct=ok,
        answered_at=when,
    )


def test_no_double_recording(tmp_path):
    store = HistoryStore(tmp_path / "h.db")
    t = datetime(2026, 10, 1, 10)
    assert _record(store, "s1", 0, "1", True, t)
    assert not _record(store, "s1", 0, "1", False, t)  # 同じ問題の二重記録
    assert _record(store, "s2", 0, "1", False, t)
    assert len(store.answers_df()) == 2


def test_stats_are_newest_first_and_grouped(tmp_path):
    store = HistoryStore(tmp_path / "h.db")
    _record(store, "s", 0, "1", False, datetime(2026, 10, 1))
    _record(store, "s", 1, "1", True, datetime(2026, 10, 2))
    _record(store, "s", 2, "142-1", False, datetime(2026, 10, 2))
    _record(store, "s", 3, "142-3", True, datetime(2026, 10, 3))

    assert store.item_stats()["1"].recent == (True, False)
    assert store.results_by_no()[142] == [True, False]
    assert store.answered_nos() == {1, 142}

    daily = store.daily_summary()
    assert list(daily["回答数"]) == [1, 2, 1]
    cat = store.category_accuracy().set_index("分野")
    assert cat.loc["分析", "正答率"] == 0.5


def _exam(session, idx, qid, ok, when, mode="mock"):
    from python_awssaa_quiz.exam_bank import ExamAnswer

    return ExamAnswer(
        session_id=session,
        question_index=idx,
        question_id=qid,
        domain="secure",
        mode=mode,
        selected=(0, 2),
        is_correct=ok,
        answered_at=when,
    )


def test_exam_answers_are_separate_and_not_double_recorded(tmp_path):
    store = HistoryStore(tmp_path / "h.db")
    t = datetime(2026, 10, 1, 10)
    rows = [_exam("m1", 0, "E0001", True, t), _exam("m1", 1, "E0002", False, t)]
    assert store.record_exam_answers(rows) == 2
    assert store.record_exam_answers(rows) == 0  # 二重記録しない
    assert store.answers_df().empty  # キーワードクイズの履歴には混ざらない
    df = store.exam_answers_df()
    assert list(df["selected"]) == ["0,2", "0,2"]


def test_exam_stats_and_mock_results(tmp_path):
    store = HistoryStore(tmp_path / "h.db")
    store.record_exam_answers(
        [
            _exam("m1", 0, "E0001", False, datetime(2026, 10, 1)),
            _exam("m1", 1, "E0002", True, datetime(2026, 10, 1)),
            _exam("p1", 0, "E0001", True, datetime(2026, 10, 2), mode="practice"),
            _exam("m2", 0, "E0001", True, datetime(2026, 10, 3)),
            _exam("m2", 1, "E0002", True, datetime(2026, 10, 3)),
        ]
    )
    assert store.exam_stats()["E0001"].recent == (True, True, False)
    mocks = store.mock_exam_results()
    assert list(mocks["正解数"]) == [1, 2]  # 練習の回答は模擬試験の結果に含めない
    assert list(mocks["正答率"]) == [0.5, 1.0]
