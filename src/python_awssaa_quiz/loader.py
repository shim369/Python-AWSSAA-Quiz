"""キーワード集Excelの読み込みとデータクラスへの変換。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_EXCEL_PATH = DATA_DIR / "AWS_SAA_重要キーワード集.xlsx"

SHEET_NAME = "キーワード一覧"
HEADER_ROW = 4  # Excel上の行番号(1始まり)
FIRST_DATA_ROW = HEADER_ROW + 1
COLUMNS = ["No", "分野", "キーワード", "概要", "試験での頻出ポイント", "重要度", "理解度"]

# 理解度の記号 → Excelのプルダウンに登録されている表記
UNDERSTANDING_LABELS = {
    "◎": "◎ 説明できる",
    "○": "○ なんとなく",
    "△": "△ 要復習",
}


@dataclass(frozen=True)
class Keyword:
    no: int
    category: str
    name: str
    summary: str
    exam_point: str
    importance: int  # ★の数(1〜3)
    understanding: str | None  # "◎" / "○" / "△" / None(未記入)
    excel_row: int  # Excel上の行番号(書き戻しで使う)


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _parse_understanding(value: object) -> str | None:
    text = _clean(value)
    if not text:
        return None
    mark = text[0]
    return mark if mark in UNDERSTANDING_LABELS else None


def load_keywords(path: Path | str = DEFAULT_EXCEL_PATH) -> list[Keyword]:
    """シート「キーワード一覧」を読み込み、Keywordのリストを返す。"""
    df = pd.read_excel(
        path,
        sheet_name=SHEET_NAME,
        header=HEADER_ROW - 1,
        usecols="A:G",
        dtype=object,
        engine="openpyxl",
    )
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"想定している列が見つかりません: {missing}(見出しは{HEADER_ROW}行目)")

    keywords: list[Keyword] = []
    for offset, row in enumerate(df.itertuples(index=False)):
        record = dict(zip(df.columns, row))
        if _clean(record["No"]) == "" or _clean(record["キーワード"]) == "":
            continue
        keywords.append(
            Keyword(
                no=int(record["No"]),
                category=_clean(record["分野"]),
                name=_clean(record["キーワード"]),
                summary=_clean(record["概要"]),
                exam_point=_clean(record["試験での頻出ポイント"]),
                importance=_clean(record["重要度"]).count("★"),
                understanding=_parse_understanding(record["理解度"]),
                excel_row=FIRST_DATA_ROW + offset,
            )
        )

    nos = [k.no for k in keywords]
    if len(nos) != len(set(nos)):
        raise ValueError("No列に重複があります")
    return keywords
