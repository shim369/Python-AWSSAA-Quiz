"""Claude API で本番形式の問題の下書きを作る(scripts/draft_exam_questions.py から使う)。

生成した問題は data/exam_questions/drafts/ に保存するだけで、出題には使わない。
内容を確認・修正してから data/exam_questions/ に移すと出題される。
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .exam_bank import DEFAULT_EXAM_DIR, ExamBankError, ExamQuestion, exam_files, load_exam_file, parse_question
from .exam_guide import GUIDE_URL, TASKS, Task
from .loader import PROJECT_ROOT, Keyword

DRAFTS_DIR = DEFAULT_EXAM_DIR / "drafts"
DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

GUIDELINES_PATH = PROJECT_ROOT / "docs" / "exam_question_guidelines.md"

ROLE_PROMPT = """\
あなたは AWS 認定ソリューションアーキテクト – アソシエイト(SAA-C03)の問題作成者です。
学習アプリ用に、本番と同じ難易度・形式のオリジナル問題を日本語で作ります。
次の作問ルールに従ってください。
"""


def load_guidelines(path: Path = GUIDELINES_PATH) -> str:
    """作問ルール(docs/exam_question_guidelines.md)の本文。最初の「## 」より前の説明は除く。"""
    text = path.read_text(encoding="utf-8")
    start = text.find("\n## ")
    return text[start + 1 :].strip() if start >= 0 else text.strip()


# 出力の形(IDはスクリプト側で振る)
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": list(TASKS)},
                    "question": {"type": "string"},
                    "choices": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "correct": {"type": "boolean"},
                                "reason": {"type": "string"},
                            },
                            "required": ["text", "correct", "reason"],
                            "additionalProperties": False,
                        },
                    },
                    "explanation": {"type": "string"},
                    "related_keywords": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["task", "question", "choices", "explanation", "related_keywords"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


class DraftError(RuntimeError):
    """APIの応答から問題を作れなかった。"""


def keyword_reference(keywords: Iterable[Keyword]) -> str:
    return "\n".join(f"{k.no}: {k.name} ― {k.exam_point}" for k in keywords)


def build_system_prompt(keywords: Iterable[Keyword]) -> str:
    # 毎回同じ内容なので、プロンプトキャッシュが効く
    return (
        f"{ROLE_PROMPT}\n{load_guidelines()}\n\n試験ガイド: {GUIDE_URL}\n\n"
        "## キーワード集(No: キーワード ― 試験での頻出ポイント)\n"
        + keyword_reference(keywords)
    )


def least_covered_tasks(questions: Sequence[ExamQuestion], n: int) -> list[Task]:
    """収録問題が少ないタスクをn個(同数なら試験ガイドの順)。"""
    counts = {t: sum(q.task.id == t.id for q in questions) for t in TASKS.values()}
    return sorted(TASKS.values(), key=lambda t: counts[t])[:n]


def build_user_prompt(
    tasks: Sequence[Task], count: int, existing: Sequence[ExamQuestion], note: str = ""
) -> str:
    lines = [f"次のタスクから、合計{count}問を作ってください(タスクにできるだけ均等に割り振る)。", ""]
    for t in tasks:
        lines.append(f"## タスク {t.id} {t.title}(分野: {t.domain.label})")
        lines += [f"- {f}" for f in t.focus]
        lines.append("")
    same_task = [q for q in existing if q.task in tasks]
    if same_task:
        lines.append("# すでにある問題(同じシナリオ・同じ正解の組み合わせは避ける)")
        lines += [f"- [{q.task.id}] {q.question.splitlines()[0]}" for q in same_task]
        lines.append("")
    if note:
        lines += ["# 追加の指示", note, ""]
    return "\n".join(lines)


def response_text(message: Any) -> str:
    """応答のテキストを取り出す。フォールバックが起きた場合は、最後のモデルの出力だけを使う。"""
    stop = getattr(message, "stop_reason", None)
    if stop == "refusal":
        raise DraftError("モデルが生成を断りました(stop_reason: refusal)。指示を変えて再実行してください")
    if stop == "max_tokens":
        raise DraftError("出力が上限で途切れました。--count を減らして再実行してください")
    blocks = list(message.content)
    last_fallback = max((i for i, b in enumerate(blocks) if b.type == "fallback"), default=-1)
    text = "".join(b.text for b in blocks[last_fallback + 1 :] if b.type == "text")
    if not text.strip():
        raise DraftError("応答にテキストがありません")
    return text


def request_drafts(
    client: Any,
    *,
    keywords: Sequence[Keyword],
    tasks: Sequence[Task],
    count: int,
    existing: Sequence[ExamQuestion],
    model: str = DEFAULT_MODEL,
    note: str = "",
) -> list[dict[str, Any]]:
    """Claude API を呼び、問題の下書き(dictのリスト、IDなし)を返す。"""
    with client.beta.messages.stream(
        model=model,
        max_tokens=64000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
        },
        system=[
            {
                "type": "text",
                "text": build_system_prompt(keywords),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": build_user_prompt(tasks, count, existing, note)}],
    ) as stream:
        message = stream.get_final_message()
    try:
        data = json.loads(response_text(message))
    except json.JSONDecodeError as e:
        raise DraftError(f"応答をJSONとして読めません: {e}") from e
    return list(data["questions"])


# ---------------------------------------------------------------- 検証と保存

_ID_NUM_RE = re.compile(r"^E(\d{4})$")


def all_known_ids(directory: Path = DEFAULT_EXAM_DIR) -> set[str]:
    """出題中の問題と下書きで使われているID(下書きの読み込みエラーは無視する)。"""
    ids: set[str] = set()
    for path in [*exam_files(directory), *exam_files(directory / "drafts")]:
        try:
            ids |= {q.id for q in load_exam_file(path)}
        except ExamBankError:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            ids |= {str(d.get("id")) for d in data if isinstance(d, dict)}
    return ids


def next_ids(used: Iterable[str], n: int) -> list[str]:
    start = max((int(m.group(1)) for i in used if (m := _ID_NUM_RE.match(i))), default=0) + 1
    return [f"E{i:04}" for i in range(start, start + n)]


@dataclass
class DraftResult:
    accepted: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[tuple[dict[str, Any], str]] = field(default_factory=list)


def finalize_drafts(
    drafts: Sequence[dict[str, Any]], used_ids: Iterable[str], keyword_nos: set[int]
) -> DraftResult:
    """IDとdomainを付け、アプリと同じ検証にかける。キーワード集にないNoは取り除く。"""
    result = DraftResult()
    ids = iter(next_ids(used_ids, len(drafts)))
    for draft in drafts:
        task = TASKS.get(str(draft.get("task")))
        record: dict[str, Any] = {
            "id": next(ids),
            "domain": task.domain.value if task else "",
            "task": draft.get("task"),
            "question": draft.get("question"),
            "choices": [
                {"text": c["text"], **({"correct": True} if c["correct"] else {}), "reason": c["reason"]}
                for c in draft.get("choices", [])
            ],
            "explanation": draft.get("explanation", ""),
            "related_keywords": [n for n in draft.get("related_keywords", []) if n in keyword_nos],
        }
        try:
            parse_question(record)
        except ExamBankError as e:
            result.rejected.append((record, str(e)))
        else:
            result.accepted.append(record)
    return result


class _BlockDumper(yaml.SafeDumper):
    pass


def _str_representer(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_BlockDumper.add_representer(str, _str_representer)


def dump_questions(records: Sequence[dict[str, Any]]) -> str:
    for r in records:
        # 問題文と解説は複数行のブロックで書き、手で直しやすくする
        for key in ("question", "explanation"):
            if r.get(key) and not r[key].endswith("\n"):
                r[key] = r[key].rstrip() + "\n"
    return yaml.dump(
        list(records), Dumper=_BlockDumper, allow_unicode=True, sort_keys=False, width=1000
    ).replace("\n- id:", "\n\n- id:")


def write_drafts(records: Sequence[dict[str, Any]], directory: Path = DRAFTS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"draft_{datetime.now():%Y%m%d_%H%M%S}.yaml"
    header = (
        "# Claude API で生成した下書き(未レビュー)。\n"
        "# 内容を確認・修正し、問題ごとに data/exam_questions/ のYAMLへ移すと出題されます。\n\n"
    )
    path.write_text(header + dump_questions(records), encoding="utf-8")
    return path
