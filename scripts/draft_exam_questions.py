"""Claude API で本番形式の問題の下書きを作る。

使い方:
    uv run --group tools python scripts/draft_exam_questions.py              # 収録の少ないタスクから5問
    uv run --group tools python scripts/draft_exam_questions.py --task 3.4 --task 4.4 --count 6
    uv run --group tools python scripts/draft_exam_questions.py --task 2.2 --note "DR戦略の比較を中心に"

APIの認証情報は環境変数 ANTHROPIC_API_KEY などから読み込む。
下書きは data/exam_questions/drafts/ に保存され、確認して移すまでは出題されない。
"""

from __future__ import annotations

import argparse
import sys

import anthropic

from python_awssaa_quiz.exam_bank import ExamBankError, load_exam_questions
from python_awssaa_quiz.exam_drafting import (
    DEFAULT_MODEL,
    DraftError,
    all_known_ids,
    finalize_drafts,
    least_covered_tasks,
    request_drafts,
    write_drafts,
)
from python_awssaa_quiz.exam_guide import TASKS
from python_awssaa_quiz.loader import load_keywords


def main() -> int:
    parser = argparse.ArgumentParser(description="本番形式の問題の下書きを Claude API で作る")
    parser.add_argument(
        "--task",
        action="append",
        choices=list(TASKS),
        help="出題するタスク(複数指定可)。省略すると収録問題の少ないタスクを2つ選ぶ",
    )
    parser.add_argument("--count", type=int, default=5, help="作る問題数(1〜10、既定: 5)")
    parser.add_argument("--note", default="", help="追加の指示(例: 特定のサービスを中心に)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"使うモデル(既定: {DEFAULT_MODEL})")
    args = parser.parse_args()

    if not 1 <= args.count <= 10:
        parser.error("--count は1〜10にしてください")

    try:
        existing = load_exam_questions()
    except ExamBankError as e:
        print(f"問題データに誤りがあります。先に直してください: {e}", file=sys.stderr)
        return 1
    keywords = load_keywords()
    tasks = [TASKS[t] for t in args.task] if args.task else least_covered_tasks(existing, 2)
    print("対象のタスク: " + " / ".join(t.label for t in tasks))
    print(f"{args.count}問を生成しています(数分かかることがあります)…")

    try:
        drafts = request_drafts(
            anthropic.Anthropic(),
            keywords=keywords,
            tasks=tasks,
            count=args.count,
            existing=existing,
            model=args.model,
            note=args.note,
        )
    except DraftError as e:
        print(f"生成できませんでした: {e}", file=sys.stderr)
        return 1
    except anthropic.AuthenticationError:
        print("APIの認証に失敗しました。ANTHROPIC_API_KEY を確認してください", file=sys.stderr)
        return 1
    except anthropic.RateLimitError:
        print("APIの利用上限に達しました。しばらく待ってから再実行してください", file=sys.stderr)
        return 1
    except anthropic.APIStatusError as e:
        print(f"APIエラー({e.status_code}): {e.message}", file=sys.stderr)
        return 1
    except anthropic.APIConnectionError:
        print("APIに接続できませんでした。ネットワークを確認してください", file=sys.stderr)
        return 1

    result = finalize_drafts(drafts, all_known_ids(), {k.no for k in keywords})
    for record, reason in result.rejected:
        print(f"  形式の誤りで除外: {reason}", file=sys.stderr)
    if not result.accepted:
        print("使える下書きがありませんでした。", file=sys.stderr)
        return 1

    path = write_drafts(result.accepted)
    print(f"{len(result.accepted)}問の下書きを保存しました: {path}")
    print("内容を確認・修正してから、data/exam_questions/ のYAMLに移してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
