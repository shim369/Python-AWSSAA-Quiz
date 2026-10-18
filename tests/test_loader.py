from collections import Counter


def test_loads_all_keywords(keywords):
    assert len(keywords) == 160
    assert [k.no for k in keywords] == list(range(1, 161))


def test_categories_and_importance(keywords):
    assert len({k.category for k in keywords}) == 12
    assert set(Counter(k.importance for k in keywords)) == {1, 2, 3}


def test_first_and_last_rows(keywords):
    first, last = keywords[0], keywords[-1]
    assert (first.name, first.excel_row, first.importance) == ("Amazon EC2", 5, 3)
    assert last.excel_row == 164
    assert all(k.summary and k.exam_point for k in keywords)
