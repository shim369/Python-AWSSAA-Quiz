"""本番形式の問題(問題バンク)の読み込み・検証・出題。Streamlitには依存しない。

問題は data/exam_questions/*.yaml に書く(書き方は README を参照)。
キーワードクイズと違い、問題文・選択肢・解説はすべてデータに書かれたものをそのまま使う。
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

import yaml

from .exam_guide import TASKS, Domain, Task
from .loader import DATA_DIR
from .quiz_engine import ItemStats, QuizMode

DEFAULT_EXAM_DIR = DATA_DIR / "exam_questions"

MOCK_EXAM_SIZE = 65  # 本番の問題数
SECONDS_PER_QUESTION = 120  # 本番は65問130分
PASSING_SCORE = 720  # 1000点満点中


class ExamBankError(ValueError):
    """問題データの書き方に誤りがある。"""


@dataclass(frozen=True)
class ExamChoice:
    text: str
    correct: bool
    reason: str  # 正解・不正解の理由


@dataclass(frozen=True)
class ExamQuestion:
    id: str  # "E0001"
    domain: Domain
    task: Task  # 試験ガイドのタスクステートメント
    question: str
    choices: tuple[ExamChoice, ...]
    explanation: str
    related_keywords: tuple[int, ...]  # キーワード集のNo

    @property
    def answer_count(self) -> int:
        return sum(c.correct for c in self.choices)


# ---------------------------------------------------------------- 読み込みと検証

_ID_RE = re.compile(r"^E\d{4}$")
_QUESTION_KEYS = {"id", "domain", "task", "question", "choices", "explanation", "related_keywords"}
_REQUIRED_KEYS = {"id", "domain", "task", "question", "choices"}
_CHOICE_KEYS = {"text", "correct", "reason"}


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def parse_question(raw: object) -> ExamQuestion:
    """YAMLの1問分(dict)を検証して ExamQuestion にする。誤りがあれば ExamBankError。"""
    if not isinstance(raw, dict):
        raise ExamBankError("1問分は「id: …」から始まる項目のまとまりで書いてください")
    qid = _text(raw.get("id"))
    where = f"問題 {qid or '(idなし)'}"

    unknown = set(raw) - _QUESTION_KEYS
    if unknown:
        raise ExamBankError(f"{where}: 知らない項目があります: {sorted(unknown)}")
    missing = _REQUIRED_KEYS - {k for k, v in raw.items() if v not in (None, "")}
    if missing:
        raise ExamBankError(f"{where}: 必須の項目がありません: {sorted(missing)}")
    if not _ID_RE.match(qid):
        raise ExamBankError(f"{where}: id は「E」と4桁の数字で書いてください(例: E0001)")
    try:
        domain = Domain(_text(raw["domain"]))
    except ValueError:
        raise ExamBankError(
            f"{where}: domain は {', '.join(d.value for d in Domain)} のどれかにしてください"
        ) from None
    task = TASKS.get(_text(raw["task"]))
    if task is None or task.domain is not domain:
        ids = ", ".join(t.id for t in TASKS.values() if t.domain is domain)
        raise ExamBankError(f"{where}: task は domain「{domain.value}」のタスク({ids})にしてください")

    raw_choices = raw["choices"]
    if not isinstance(raw_choices, list):
        raise ExamBankError(f"{where}: choices は「- text: …」の並びで書いてください")
    choices = []
    for i, c in enumerate(raw_choices, start=1):
        if not isinstance(c, dict) or set(c) - _CHOICE_KEYS:
            raise ExamBankError(f"{where}: 選択肢{i}は text / correct / reason だけで書いてください")
        if not _text(c.get("text")) or not _text(c.get("reason")):
            raise ExamBankError(f"{where}: 選択肢{i}に text と reason を書いてください")
        if c.get("correct", False) not in (True, False):
            raise ExamBankError(f"{where}: 選択肢{i}の correct は true か false にしてください")
        choices.append(ExamChoice(_text(c["text"]), bool(c.get("correct")), _text(c["reason"])))

    n_correct = sum(c.correct for c in choices)
    if n_correct == 0:
        raise ExamBankError(f"{where}: 正解(correct: true)の選択肢がありません")
    # 本番と同じく、正解1つなら4択、複数なら5択以上
    if n_correct == 1 and len(choices) != 4:
        raise ExamBankError(f"{where}: 正解が1つの問題は選択肢を4つにしてください")
    if n_correct > 1 and not (len(choices) >= 5 and n_correct < len(choices) - 2):
        raise ExamBankError(f"{where}: 正解が複数の問題は5択以上で、誤答を3つ以上にしてください")
    if len({c.text for c in choices}) != len(choices):
        raise ExamBankError(f"{where}: 同じ文の選択肢があります")

    related = raw.get("related_keywords") or []
    if not isinstance(related, list) or not all(isinstance(n, int) for n in related):
        raise ExamBankError(f"{where}: related_keywords はキーワード集のNo(整数)の並びで書いてください")

    return ExamQuestion(
        id=qid,
        domain=domain,
        task=task,
        question=_text(raw["question"]),
        choices=tuple(choices),
        explanation=_text(raw.get("explanation")),
        related_keywords=tuple(related),
    )


def load_exam_file(path: Path) -> list[ExamQuestion]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ExamBankError(f"{path.name}: YAMLとして読めません: {e}") from e
    if data is None:
        return []
    if not isinstance(data, list):
        raise ExamBankError(f"{path.name}: 問題は「- id: …」の並び(リスト)で書いてください")
    questions = []
    for raw in data:
        try:
            questions.append(parse_question(raw))
        except ExamBankError as e:
            raise ExamBankError(f"{path.name}: {e}") from None
    return questions


def exam_files(directory: Path | str = DEFAULT_EXAM_DIR) -> list[Path]:
    """読み込み対象のファイル(サブフォルダの drafts/ などは含めない)。"""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix in (".yaml", ".yml"))


def load_exam_questions(directory: Path | str = DEFAULT_EXAM_DIR) -> list[ExamQuestion]:
    """フォルダ内のYAMLをすべて読み込む。フォルダがなければ空のリスト。"""
    questions: list[ExamQuestion] = []
    seen: dict[str, str] = {}
    for path in exam_files(directory):
        for q in load_exam_file(path):
            if q.id in seen:
                raise ExamBankError(f"{path.name}: id {q.id} が {seen[q.id]} と重複しています")
            seen[q.id] = path.name
            questions.append(q)
    return questions


# ---------------------------------------------------------------- 出題


class ExamMode(StrEnum):
    PRACTICE = "practice"
    MOCK = "mock"

    @property
    def label(self) -> str:
        return EXAM_MODE_LABELS[self]


EXAM_MODE_LABELS = {
    ExamMode.PRACTICE: "練習(1問ずつ答え合わせ)",
    ExamMode.MOCK: "模擬試験(最後にまとめて採点)",
}


@dataclass(frozen=True)
class PresentedQuestion:
    """選択肢の並びを決めた、出題1問分。order[i] は表示i番目の選択肢の、元データでの位置。"""

    question: ExamQuestion
    order: tuple[int, ...]

    @property
    def choices(self) -> tuple[ExamChoice, ...]:
        return tuple(self.question.choices[i] for i in self.order)

    @property
    def answer(self) -> frozenset[int]:
        """正解の選択肢の、表示上の位置。"""
        return frozenset(i for i, c in enumerate(self.choices) if c.correct)

    def is_correct(self, selected: Iterable[int]) -> bool:
        return frozenset(selected) == self.answer

    def original_indices(self, selected: Iterable[int]) -> tuple[int, ...]:
        """表示上の位置を元データでの位置に直す(履歴に保存する用)。"""
        return tuple(sorted(self.order[i] for i in selected))


@dataclass(frozen=True)
class ExamAnswer:
    """回答履歴に保存する1件分。"""

    session_id: str
    question_index: int
    question_id: str
    domain: str
    mode: str
    selected: tuple[int, ...]  # 元データでの位置
    is_correct: bool
    answered_at: datetime | None = None


def make_answer(
    session_id: str, index: int, pq: PresentedQuestion, selected: Iterable[int], mode: ExamMode
) -> ExamAnswer:
    selected = tuple(selected)
    return ExamAnswer(
        session_id=session_id,
        question_index=index,
        question_id=pq.question.id,
        domain=pq.question.domain.value,
        mode=mode.value,
        selected=pq.original_indices(selected),
        is_correct=pq.is_correct(selected),
    )


def present(question: ExamQuestion, rng: random.Random) -> PresentedQuestion:
    order = list(range(len(question.choices)))
    rng.shuffle(order)
    return PresentedQuestion(question, tuple(order))


@dataclass(frozen=True)
class ExamSettings:
    mode: ExamMode = ExamMode.PRACTICE
    domains: tuple[Domain, ...] = ()  # 空なら全分野(練習のみ)
    tasks: tuple[str, ...] = ()  # タスクのid。空なら絞り込まない(練習のみ)
    count: int | None = 10  # Noneなら条件に合う全問
    order: QuizMode = QuizMode.RANDOM  # 練習での問題の選び方
    timer: bool = True  # 模擬試験で制限時間を設けるか


def exam_weakness_weight(stats: ItemStats | None) -> float:
    """練習の弱点優先モードの重み。1 + 3×直近3回の不正解数 + 1×(未回答)"""
    stats = stats or ItemStats()
    return 1 + 3 * stats.recent_wrong + 1 * (not stats.answered)


def filter_questions(
    questions: Iterable[ExamQuestion],
    settings: ExamSettings,
    stats: Mapping[str, ItemStats],
) -> list[ExamQuestion]:
    """練習で出題の候補になる問題。"""
    pool = [
        q
        for q in questions
        if (not settings.domains or q.domain in settings.domains)
        and (not settings.tasks or q.task.id in settings.tasks)
    ]
    if settings.order is QuizMode.REVIEW_MISTAKES:
        pool = [q for q in pool if (s := stats.get(q.id)) is not None and s.recent_wrong > 0]
    return pool


def allocate_by_domain(
    available: Mapping[Domain, int], total: int
) -> dict[Domain, int]:
    """total問を出題比率に沿って分野に割り振る(最大剰余法)。
    問題が足りない分野の不足分は、ほかの分野で補う。"""
    total = min(total, sum(available.values()))
    alloc = {d: 0 for d in Domain}
    remaining = total
    active = [d for d in Domain if available.get(d, 0) > 0]
    while remaining > 0 and active:
        weight_sum = sum(d.weight for d in active)
        shares = {d: remaining * d.weight / weight_sum for d in active}
        add = {d: int(shares[d]) for d in active}
        leftover = remaining - sum(add.values())
        for d in sorted(active, key=lambda d: shares[d] - add[d], reverse=True)[:leftover]:
            add[d] += 1
        for d in active:
            add[d] = min(add[d], available[d] - alloc[d])
            alloc[d] += add[d]
        remaining = total - sum(alloc.values())
        active = [d for d in active if alloc[d] < available[d]]
    return alloc


def generate_exam(
    questions: Sequence[ExamQuestion],
    settings: ExamSettings,
    stats: Mapping[str, ItemStats] | None = None,
    seed: int | None = None,
) -> list[PresentedQuestion]:
    """設定に従って出題リストを作る。seedを指定すると同じ結果が再現できる。

    - 練習: 分野と選び方(ランダム/弱点優先/間違えた問題)で絞り込む
    - 模擬試験: 全分野から出題比率に沿って選び、分野を混ぜて並べる"""
    rng = random.Random(seed)
    stats = stats or {}

    if settings.mode is ExamMode.MOCK:
        count = MOCK_EXAM_SIZE if settings.count is None else settings.count
        by_domain = {d: [q for q in questions if q.domain is d] for d in Domain}
        alloc = allocate_by_domain({d: len(qs) for d, qs in by_domain.items()}, count)
        selected = [q for d in Domain for q in rng.sample(by_domain[d], alloc[d])]
        rng.shuffle(selected)
        return [present(q, rng) for q in selected]

    pool = filter_questions(questions, settings, stats)
    n = len(pool) if settings.count is None else min(settings.count, len(pool))
    if settings.order is QuizMode.WEAK_FIRST:
        # 重み付きの非復元抽出(キーワードクイズと同じ Efraimidis–Spirakis法)
        keyed = [(rng.random() ** (1.0 / exam_weakness_weight(stats.get(q.id))), q) for q in pool]
        keyed.sort(key=lambda pair: pair[0], reverse=True)
        selected = [q for _, q in keyed[:n]]
    else:
        selected = rng.sample(pool, n)
    return [present(q, rng) for q in selected]


def time_limit_seconds(n_questions: int) -> int:
    """模擬試験の制限時間。本番と同じ1問あたり2分。"""
    return n_questions * SECONDS_PER_QUESTION


def scaled_score(correct: int, total: int) -> int:
    """1000点満点の目安スコア。本番は問題ごとに配点が違うため、正答率からの単純換算。"""
    return round(1000 * correct / total) if total else 0


def missed_keyword_nos(
    questions: Iterable[ExamQuestion], stats: Mapping[str, ItemStats]
) -> frozenset[int]:
    """最後の回答が不正解だった本番形式の問題に関連するキーワードのNo。"""
    return frozenset(
        no
        for q in questions
        if (s := stats.get(q.id)) is not None and s.recent and not s.recent[0]
        for no in q.related_keywords
    )


# ---------------------------------------------------------------- 内容のチェック


@dataclass(frozen=True)
class LintResult:
    errors: tuple[str, ...]  # 直す必要があるもの
    warnings: tuple[str, ...]  # 作問ルール上、見直したほうがよいもの


def lint_question(q: ExamQuestion, keyword_nos: set[int]) -> LintResult:
    """形式の検証(parse_question)のあとに行う、内容のチェック。"""
    errors, warnings = [], []
    unknown = [n for n in q.related_keywords if n not in keyword_nos]
    if unknown:
        errors.append(f"related_keywords にキーワード集にないNoがあります: {unknown}")
    if "つ選択" in q.question:
        errors.append("問題文に「〇つ選択」を書かないでください(画面に自動で表示されます)")
    if not q.related_keywords:
        warnings.append("related_keywords がありません")
    if not q.explanation:
        warnings.append("explanation がありません")
    correct_len = [len(c.text) for c in q.choices if c.correct]
    wrong_len = [len(c.text) for c in q.choices if not c.correct]
    if min(correct_len) > 1.5 * max(wrong_len):
        warnings.append("正解の選択肢だけが長く、見た目で答えがわかります")
    return LintResult(tuple(errors), tuple(warnings))
