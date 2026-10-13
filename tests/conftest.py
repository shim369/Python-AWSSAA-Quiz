from pathlib import Path

import pytest

from python_awssaa_quiz.loader import DEFAULT_EXCEL_PATH, load_keywords
from python_awssaa_quiz.quiz_engine import build_items


@pytest.fixture(scope="session")
def excel_path() -> Path:
    if not DEFAULT_EXCEL_PATH.exists():
        pytest.skip(f"{DEFAULT_EXCEL_PATH} がありません")
    return DEFAULT_EXCEL_PATH


@pytest.fixture(scope="session")
def keywords(excel_path):
    return load_keywords(excel_path)


@pytest.fixture(scope="session")
def items(keywords):
    return build_items(keywords)
