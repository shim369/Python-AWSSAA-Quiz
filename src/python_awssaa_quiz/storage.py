"""SQLiteへの回答履歴の保存と集計。"""

from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pandas as pd

from .loader import DATA_DIR
from .quiz_engine import ItemStats

# 環境変数 AWSSAA_QUIZ_DB で保存先を変えられる(テスト用)
DEFAULT_DB_PATH = Path(os.environ.get("AWSSAA_QUIZ_DB", DATA_DIR / "history.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT    NOT NULL,
    question_index INTEGER NOT NULL,
    item_id        TEXT    NOT NULL,
    no             INTEGER NOT NULL,
    keyword        TEXT    NOT NULL,
    category       TEXT    NOT NULL,
    format         TEXT    NOT NULL,
    is_correct     INTEGER NOT NULL,
    answered_at    TEXT    NOT NULL,
    UNIQUE (session_id, question_index)
);
CREATE INDEX IF NOT EXISTS idx_answers_item ON answers (item_id, answered_at);
"""


class HistoryStore:
    def __init__(self, path: Path | str = DEFAULT_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def record_answer(
        self,
        *,
        session_id: str,
        question_index: int,
        item_id: str,
        no: int,
        keyword: str,
        category: str,
        format: str,
        is_correct: bool,
        answered_at: datetime | None = None,
    ) -> bool:
        """回答を1件記録する。同じ(session_id, question_index)は二重に記録しない。
        記録した場合はTrueを返す。"""
        answered_at = answered_at or datetime.now()
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO answers
                    (session_id, question_index, item_id, no, keyword, category,
                     format, is_correct, answered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    question_index,
                    item_id,
                    no,
                    keyword,
                    category,
                    format,
                    int(is_correct),
                    answered_at.isoformat(timespec="seconds"),
                ),
            )
            return cur.rowcount == 1

    def answers_df(self) -> pd.DataFrame:
        with closing(self._connect()) as conn:
            df = pd.read_sql_query("SELECT * FROM answers ORDER BY answered_at, id", conn)
        df["is_correct"] = df["is_correct"].astype(bool)
        df["answered_at"] = pd.to_datetime(df["answered_at"])
        return df

    def _recent_results(self, key: str) -> dict[str, list[bool]]:
        """key("item_id" または "no")ごとの正誤リスト(新しい順)。"""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {key}, is_correct FROM answers ORDER BY answered_at DESC, id DESC"
            ).fetchall()
        results: dict[str, list[bool]] = defaultdict(list)
        for k, ok in rows:
            results[str(k)].append(bool(ok))
        return dict(results)

    def item_stats(self) -> dict[str, ItemStats]:
        return {k: ItemStats(tuple(v)) for k, v in self._recent_results("item_id").items()}

    def results_by_no(self) -> dict[int, list[bool]]:
        """Excelの行(No)単位の正誤リスト(新しい順)。分割した出題単位はまとめる。"""
        return {int(k): v for k, v in self._recent_results("no").items()}

    def answered_nos(self) -> set[int]:
        with closing(self._connect()) as conn:
            return {r[0] for r in conn.execute("SELECT DISTINCT no FROM answers")}

    def category_accuracy(self) -> pd.DataFrame:
        df = self.answers_df()
        if df.empty:
            return pd.DataFrame(columns=["分野", "回答数", "正答率"])
        g = df.groupby("category")["is_correct"].agg(["count", "mean"]).reset_index()
        g.columns = ["分野", "回答数", "正答率"]
        return g

    def daily_summary(self) -> pd.DataFrame:
        df = self.answers_df()
        if df.empty:
            return pd.DataFrame(columns=["日付", "回答数", "正答率"])
        df["日付"] = df["answered_at"].dt.normalize()
        g = df.groupby("日付")["is_correct"].agg(["count", "mean"]).reset_index()
        g.columns = ["日付", "回答数", "正答率"]
        return g
