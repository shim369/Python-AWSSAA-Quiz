"""問題生成と出題順の決定。Streamlitには依存しない。"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from .excel_writer import judge_understanding
from .loader import Keyword

MASK = "〇〇"
NUM_CHOICES = 4


class QuestionFormat(StrEnum):
    SUMMARY_TO_KEYWORD = "summary_to_keyword"
    KEYWORD_TO_SUMMARY = "keyword_to_summary"
    SCENARIO_TO_KEYWORD = "scenario_to_keyword"

    @property
    def label(self) -> str:
        return FORMAT_LABELS[self]


FORMAT_LABELS = {
    QuestionFormat.SUMMARY_TO_KEYWORD: "概要 → キーワード",
    QuestionFormat.KEYWORD_TO_SUMMARY: "キーワード → 概要",
    QuestionFormat.SCENARIO_TO_KEYWORD: "シナリオ → キーワード",
}

FORMAT_INSTRUCTIONS = {
    QuestionFormat.SUMMARY_TO_KEYWORD: "次の説明に当てはまるキーワードはどれですか?",
    QuestionFormat.KEYWORD_TO_SUMMARY: "次のキーワードの説明として正しいものはどれですか?",
    QuestionFormat.SCENARIO_TO_KEYWORD: "次の要件・ポイントに最も適したサービス/機能はどれですか?",
}


class QuizMode(StrEnum):
    RANDOM = "random"
    WEAK_FIRST = "weak_first"
    REVIEW_MISTAKES = "review_mistakes"

    @property
    def label(self) -> str:
        return MODE_LABELS[self]


MODE_LABELS = {
    QuizMode.RANDOM: "ランダム",
    QuizMode.WEAK_FIRST: "弱点優先",
    QuizMode.REVIEW_MISTAKES: "間違えた問題だけ復習",
}

# 正式名称・旧名など、キーワード名からは機械的に導けない別名(問題文の伏せ字に使う)
EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    "AWS DMS": ("Database Migration Service",),
    "AWS SCT": ("Schema Conversion Tool",),
    "Amazon Data Firehose": ("Kinesis Data Firehose", "Firehose"),
    "AWS IAM Identity Center": ("AWS SSO",),
    "Amazon SageMaker AI": ("SageMaker",),
    "Amazon OpenSearch Service": ("OpenSearch",),
    "EC2 Auto Scaling": ("Auto Scaling",),
    "AWS Well-Architected フレームワーク": ("Well-Architected",),
    "AWS Snowファミリー": ("Snowball", "Snow"),
}

# お互いを誤答にすると「どちらも正解」になりうる組み合わせ(名前の前方一致で拾えないもの)
RELATED_PAIRS: tuple[tuple[str, str], ...] = (
    ("Elastic Load Balancing(ELB)", "Application Load Balancer(ALB)"),
    ("Elastic Load Balancing(ELB)", "Network Load Balancer(NLB)"),
    ("Elastic Load Balancing(ELB)", "Gateway Load Balancer(GWLB)"),
    ("AWS Organizations", "サービスコントロールポリシー(SCP)"),
    ("S3ストレージクラス", "S3 Glacier Deep Archive"),
    ("IAMロール", "AWS STS"),
    ("リージョン / AZ / エッジロケーション", "RDSマルチAZ"),
    ("RPO / RTO", "DR戦略"),
)

# 頻出ポイントが一般的すぎて、シナリオ問題の問題文にならないキーワードのNo
SCENARIO_EXCLUDED_NOS: frozenset[int] = frozenset({13, 58, 72, 142, 143, 145})

_PREFIX_RE = re.compile(r"^(Amazon|AWS)\s+")
_PAREN_RE = re.compile(r"[((]([^()()]*)[))]")
_ASCII_ABBR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .\-/]*$")
_SPLIT_RE = re.compile(r"\s*/\s*")
_MULTI_SPLIT_RE = re.compile(r"\s+/\s+")


@dataclass(frozen=True)
class QuizItem:
    """出題の単位。通常はKeywordと1対1だが、複数サービスをまとめた行は分割される。"""

    item_id: str  # "142" や、分割した場合は "142-2"
    no: int
    category: str
    name: str
    summary: str
    exam_point: str
    importance: int
    understanding: str | None


@dataclass(frozen=True)
class Question:
    item: QuizItem
    format: QuestionFormat
    prompt: str
    choices: tuple[str, ...]
    choice_item_ids: tuple[str, ...]
    answer_index: int

    def is_correct(self, choice_index: int) -> bool:
        return choice_index == self.answer_index


@dataclass(frozen=True)
class QuizSettings:
    categories: tuple[str, ...] = ()  # 空なら全分野
    importances: tuple[int, ...] = ()  # 空なら全重要度
    formats: tuple[QuestionFormat, ...] = (QuestionFormat.SUMMARY_TO_KEYWORD,)
    count: int | None = 10  # Noneなら条件に合う全問
    mode: QuizMode = QuizMode.RANDOM


@dataclass(frozen=True)
class ItemStats:
    """1つの出題単位の回答履歴(新しい順)。"""

    recent: tuple[bool, ...] = field(default_factory=tuple)

    @property
    def answered(self) -> bool:
        return bool(self.recent)

    @property
    def recent_wrong(self) -> int:
        return sum(1 for ok in self.recent[:3] if not ok)


# ---------------------------------------------------------------- 出題単位の作成


def _split_multi_service(keyword: Keyword) -> list[QuizItem] | None:
    """「Amazon Comprehend / Textract / …」のように、キーワードと概要が
    同じ数に「 / 」で区切られている行を、サービスごとの出題単位に分ける。"""
    names = _MULTI_SPLIT_RE.split(keyword.name)
    summaries = _MULTI_SPLIT_RE.split(keyword.summary)
    if len(names) < 3 or len(names) != len(summaries):
        return None
    prefix_match = _PREFIX_RE.match(names[0])
    prefix = prefix_match.group(0) if prefix_match else ""
    items = []
    for i, (name, summary) in enumerate(zip(names, summaries), start=1):
        full_name = name if _PREFIX_RE.match(name) else prefix + name
        items.append(
            QuizItem(
                item_id=f"{keyword.no}-{i}",
                no=keyword.no,
                category=keyword.category,
                name=full_name,
                summary=summary,
                exam_point=keyword.exam_point,
                importance=keyword.importance,
                understanding=keyword.understanding,
            )
        )
    return items


def build_items(keywords: Iterable[Keyword]) -> list[QuizItem]:
    items: list[QuizItem] = []
    for kw in keywords:
        split = _split_multi_service(kw)
        if split:
            items.extend(split)
            continue
        items.append(
            QuizItem(
                item_id=str(kw.no),
                no=kw.no,
                category=kw.category,
                name=kw.name,
                summary=kw.summary,
                exam_point=kw.exam_point,
                importance=kw.importance,
                understanding=kw.understanding,
            )
        )
    return items


# ---------------------------------------------------------------- 伏せ字


def _strip_prefix(name: str) -> str:
    return _PREFIX_RE.sub("", name).strip()


def aliases_for(name: str) -> set[str]:
    """問題文から伏せるべき、キーワードの表記ゆれの一覧。"""
    found: set[str] = {name}
    base = _PAREN_RE.sub("", name).strip()
    found.add(base)
    for inner in _PAREN_RE.findall(name):
        # 括弧内は「RI」「CRR/SRR」のような英字の略称だけを対象にする
        # (「パブリック/プライベート」等まで伏せると問題文が読めなくなるため)
        if _ASCII_ABBR_RE.match(inner.strip()):
            found.update(p for p in _SPLIT_RE.split(inner.strip()) if p)
    for part in _SPLIT_RE.split(base):
        found.add(part)
    found.update(EXTRA_ALIASES.get(name, ()))
    found |= {_strip_prefix(a) for a in found}
    return {a.strip() for a in found if len(a.strip()) >= 2}


def _alias_pattern(alias: str) -> str:
    escaped = re.escape(alias)
    # 英数字で始まる/終わる別名は、英単語の一部に一致しないよう境界を付ける
    if alias[0].isascii() and alias[0].isalnum():
        escaped = r"(?<![A-Za-z0-9])" + escaped
    if alias[-1].isascii() and alias[-1].isalnum():
        escaped = escaped + r"(?![A-Za-z0-9])"
    return escaped


def mask_text(text: str, name: str) -> str:
    """textに含まれるキーワード名(とその表記ゆれ)を「〇〇」に置き換える。"""
    for alias in sorted(aliases_for(name), key=len, reverse=True):
        text = re.sub(_alias_pattern(alias), MASK, text, flags=re.IGNORECASE)
    return text


def contains_alias(text: str, name: str) -> bool:
    return any(
        re.search(_alias_pattern(a), text, flags=re.IGNORECASE) for a in aliases_for(name)
    )


# ---------------------------------------------------------------- 誤答の選び方


def _core(name: str) -> str:
    return _strip_prefix(name).replace(" ", "").lower()


_RELATED_SET = {frozenset(pair) for pair in RELATED_PAIRS}


def are_related(a: QuizItem, b: QuizItem) -> bool:
    """親子関係などで、お互いを誤答にすると正解が曖昧になる組み合わせか。"""
    if a.no == b.no and a.item_id == b.item_id:
        return True
    if frozenset((a.name, b.name)) in _RELATED_SET:
        return True
    ca, cb = _core(a.name), _core(b.name)
    shorter, longer = sorted((ca, cb), key=len)
    return len(shorter) >= 2 and longer.startswith(shorter)


def is_format_applicable(item: QuizItem, fmt: QuestionFormat) -> bool:
    if fmt is QuestionFormat.SCENARIO_TO_KEYWORD:
        return item.no not in SCENARIO_EXCLUDED_NOS and bool(item.exam_point)
    if fmt is QuestionFormat.KEYWORD_TO_SUMMARY:
        return bool(item.summary)
    return bool(item.summary)


def _choice_text(item: QuizItem, fmt: QuestionFormat) -> str:
    if fmt is QuestionFormat.KEYWORD_TO_SUMMARY:
        return mask_text(item.summary, item.name)
    return item.name


def pick_distractors(
    target: QuizItem,
    pool: Sequence[QuizItem],
    fmt: QuestionFormat,
    rng: random.Random,
    k: int = NUM_CHOICES - 1,
) -> list[QuizItem]:
    """誤答をk個選ぶ。同じ分野を優先し、足りなければ他の分野から補う。"""
    used_texts = {_choice_text(target, fmt)}
    candidates = [
        it
        for it in pool
        if it.item_id != target.item_id
        and not are_related(target, it)
        and is_format_applicable(it, QuestionFormat.SUMMARY_TO_KEYWORD)
    ]
    same = [it for it in candidates if it.category == target.category]
    other = [it for it in candidates if it.category != target.category]
    rng.shuffle(same)
    rng.shuffle(other)

    chosen: list[QuizItem] = []
    for it in same + other:
        if len(chosen) == k:
            break
        text = _choice_text(it, fmt)
        if text in used_texts or any(are_related(it, c) for c in chosen):
            continue
        used_texts.add(text)
        chosen.append(it)
    if len(chosen) < k:
        raise ValueError(f"「{target.name}」の誤答候補が足りません")
    return chosen


# ---------------------------------------------------------------- 問題の生成


def make_question(
    item: QuizItem, fmt: QuestionFormat, pool: Sequence[QuizItem], rng: random.Random
) -> Question:
    distractors = pick_distractors(item, pool, fmt, rng)
    options = [item, *distractors]
    rng.shuffle(options)

    if fmt is QuestionFormat.SUMMARY_TO_KEYWORD:
        prompt = mask_text(item.summary, item.name)
    elif fmt is QuestionFormat.SCENARIO_TO_KEYWORD:
        prompt = mask_text(item.exam_point, item.name)
    else:
        prompt = item.name

    return Question(
        item=item,
        format=fmt,
        prompt=prompt,
        choices=tuple(_choice_text(o, fmt) for o in options),
        choice_item_ids=tuple(o.item_id for o in options),
        answer_index=options.index(item),
    )


def filter_items(items: Iterable[QuizItem], settings: QuizSettings) -> list[QuizItem]:
    return [
        it
        for it in items
        if (not settings.categories or it.category in settings.categories)
        and (not settings.importances or it.importance in settings.importances)
        and any(is_format_applicable(it, f) for f in settings.formats)
    ]


def weakness_weight(item: QuizItem, stats: ItemStats | None) -> float:
    """弱点優先モードの重み。
    1 + 3×直近3回の不正解数 + 2×(理解度△) + 1×(★★★) + 1×(未回答)"""
    stats = stats or ItemStats()
    history_level = judge_understanding(stats.recent)
    weak = item.understanding == "△" or history_level == "△"
    return (
        1
        + 3 * stats.recent_wrong
        + 2 * weak
        + 1 * (item.importance == 3)
        + 1 * (not stats.answered)
    )


def needs_review(stats: ItemStats | None) -> bool:
    """「間違えた問題だけ復習」の対象: 直近3回の中に不正解がある。"""
    return stats is not None and stats.recent_wrong > 0


def select_items(
    candidates: Sequence[QuizItem],
    settings: QuizSettings,
    stats: Mapping[str, ItemStats],
    rng: random.Random,
) -> list[QuizItem]:
    pool = list(candidates)
    if settings.mode is QuizMode.REVIEW_MISTAKES:
        pool = [it for it in pool if needs_review(stats.get(it.item_id))]

    n = len(pool) if settings.count is None else min(settings.count, len(pool))

    if settings.mode is QuizMode.WEAK_FIRST:
        # 重み付きの非復元抽出(Efraimidis–Spirakis法)。重いものほど前に来やすい
        keyed = [
            (rng.random() ** (1.0 / weakness_weight(it, stats.get(it.item_id))), it)
            for it in pool
        ]
        keyed.sort(key=lambda pair: pair[0], reverse=True)
        return [it for _, it in keyed[:n]]

    return rng.sample(pool, n)


def generate_quiz(
    items: Sequence[QuizItem],
    settings: QuizSettings,
    stats: Mapping[str, ItemStats] | None = None,
    seed: int | None = None,
) -> list[Question]:
    """設定に従って問題のリストを作る。seedを指定すると同じ結果が再現できる。"""
    if not settings.formats:
        raise ValueError("出題形式を1つ以上選んでください")
    rng = random.Random(seed)
    stats = stats or {}
    selected = select_items(filter_items(items, settings), settings, stats, rng)
    return questions_for(selected, items, settings.formats, rng)


def questions_for(
    selected: Sequence[QuizItem],
    pool: Sequence[QuizItem],
    formats: Sequence[QuestionFormat],
    rng: random.Random,
) -> list[Question]:
    """選んだ出題単位それぞれについて、使える形式から1つ選んで問題を作る。"""
    questions = []
    for item in selected:
        usable = [f for f in formats if is_format_applicable(item, f)]
        if not usable:
            usable = [QuestionFormat.SUMMARY_TO_KEYWORD]
        questions.append(make_question(item, rng.choice(usable), pool, rng))
    return questions
