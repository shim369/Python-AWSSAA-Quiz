"""本番形式の問題データを確認するコマンド。

    uv run exam-questions check                 # 出題中の問題と下書きをすべて確認
    uv run exam-questions check <ファイル>...    # 指定したファイルだけ確認(idの重複は全体で確認)
    uv run exam-questions coverage              # タスク別の収録数
    uv run exam-questions next-id [n]           # 次に使えるidをn個
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from .exam_bank import DEFAULT_EXAM_DIR, ExamBankError, exam_files, lint_question, load_exam_file
from .exam_drafting import DRAFTS_DIR, all_known_ids, next_ids
from .exam_guide import TASKS, Domain
from .loader import PROJECT_ROOT, load_keywords


def _ids_by_file(paths: list[Path]) -> dict[Path, list[str]]:
    """各ファイルに書かれたid(形式の誤りがあっても読めた分だけ)。"""
    import yaml

    result = {}
    for path in paths:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        except yaml.YAMLError:
            data = []
        result[path] = [str(d.get("id")) for d in data if isinstance(d, dict) and d.get("id")]
    return result


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def check(paths: list[Path]) -> int:
    """エラーの数を返す。"""
    all_paths = sorted({*exam_files(DEFAULT_EXAM_DIR), *exam_files(DRAFTS_DIR), *paths})
    targets = paths or all_paths
    keyword_nos = {k.no for k in load_keywords()}

    where: dict[str, list[str]] = {}
    for path, ids in _ids_by_file(all_paths).items():
        for qid in ids:
            where.setdefault(qid, []).append(path.name)
    duplicated = {qid: files for qid, files in where.items() if len(files) > 1}

    n_errors = 0
    for path in targets:
        try:
            questions = load_exam_file(path)
        except ExamBankError as e:
            print(f"NG  {_display(path)}\n    エラー: {e}")
            n_errors += 1
            continue
        lines = []
        for q in questions:
            lint = lint_question(q, keyword_nos)
            errors = list(lint.errors)
            if q.id in duplicated:
                errors.append(f"id が重複しています({', '.join(duplicated[q.id])})")
            n_errors += len(errors)
            lines += [f"    {q.id} エラー: {m}" for m in errors]
            lines += [f"    {q.id} 注意: {m}" for m in lint.warnings]
        status = "NG" if any("エラー" in line for line in lines) else "OK"
        print(f"{status}  {_display(path)}({len(questions)}問)")
        for line in lines:
            print(line)
    print(f"\nエラー {n_errors} 件" if n_errors else "\nエラーはありません")
    return n_errors


def coverage() -> None:
    bank = [q for p in exam_files(DEFAULT_EXAM_DIR) for q in load_exam_file(p)]
    drafts = []
    for p in exam_files(DRAFTS_DIR):
        try:
            drafts += load_exam_file(p)
        except ExamBankError:
            pass
    by_task = Counter(q.task.id for q in bank)
    multi = Counter(q.task.id for q in bank if q.answer_count > 1)
    draft_by_task = Counter(q.task.id for q in drafts)

    # 日本語は文字幅がそろわないので、数字を先に並べる
    print("収録 (複数選択) 下書き  タスク")
    for t in TASKS.values():
        print(f"{by_task[t.id]:>4} ({multi[t.id]:>6}) {draft_by_task[t.id]:>6}  {t.label}")
    print()
    total = len(bank)
    for d in Domain:
        n = sum(q.domain is d for q in bank)
        share = n / total if total else 0
        print(f"{d.label}: {n}問({share:.0%} / 本番の比率 {d.weight:.0%})")
    print(f"\n合計 {total}問(下書き {len(drafts)}問)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exam-questions", description="本番形式の問題データを確認する")
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="形式と内容を確認する")
    p_check.add_argument("paths", nargs="*", type=Path)
    sub.add_parser("coverage", help="タスク別の収録数を表示する")
    p_next = sub.add_parser("next-id", help="次に使えるidを表示する")
    p_next.add_argument("n", nargs="?", type=int, default=1)
    args = parser.parse_args(argv)

    if args.command == "check":
        missing = [p for p in args.paths if not p.is_file()]
        if missing:
            parser.error(f"ファイルが見つかりません: {', '.join(map(str, missing))}")
        return 1 if check([p.resolve() for p in args.paths]) else 0
    if args.command == "coverage":
        coverage()
        return 0
    print("\n".join(next_ids(all_known_ids(DEFAULT_EXAM_DIR), args.n)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
