---
name: exam-questions
description: 本番形式(SAA-C03のシナリオ問題)の問題を新しく作り、レビューを経て data/exam_questions/ に追加する。「本番形式の問題を増やして」「タスク3.4の問題を5問作って」「収録の少ないところを埋めて」など、本番形式の問題の作成・追加・下書きの依頼で使う。
---

# 本番形式の問題を作る

本番形式の問題(`data/exam_questions/*.yaml`)を、下書き → 事実確認 → 検証 → ユーザーのレビュー → 追加 の順に作る。
**ユーザーの了承なしに `data/exam_questions/` 直下へ問題を追加しない**(直下のファイルはそのまま出題されるため)。

## 1. 何を作るか決める

- ユーザーがタスク・問題数・観点を指定していればそれに従う
- 指定がなければ、`uv run exam-questions coverage` で収録の少ないタスクを2つ選び、合計5問を作る
- 1回に作るのは10問まで(事実確認とレビューを丁寧にするため)

## 2. 材料を読む

- 作問ルール: `docs/exam_question_guidelines.md` を必ず読み、すべて守る
- タスクの観点: `src/python_awssaa_quiz/exam_guide.py` の `TASKS` から、対象タスクの `focus`
- 既存の問題: `data/exam_questions/*.yaml` と `data/exam_questions/drafts/*.yaml` のうち、同じタスク(`task: "3.4"` など)の問題。シナリオや正解の組み合わせが重ならないようにする
- キーワード集(related_keywords に使うNo):

  ```bash
  uv run python -c "from python_awssaa_quiz.loader import load_keywords; [print(k.no, k.name, '―', k.exam_point) for k in load_keywords()]"
  ```

## 3. 下書きを書く

- idは `uv run exam-questions next-id <問題数>` で取得する(既存の問題・下書きと重ならない番号が出る)
- 書き先は `data/exam_questions/drafts/draft_<YYYYMMDD>_<タスク>.yaml`(例: `draft_20261025_3.4_4.4.yaml`)。ここは出題されず、git管理外
- 形式は README の「本番形式の問題を追加する」と同じ。誤答の選択肢には `correct` を書かない
- 各問題の直前に、確認に使った資料をYAMLのコメントで残す(次の手順で追記する)

  ```yaml
  # 確認: https://docs.aws.amazon.com/...
  - id: E0015
    domain: performant
    task: "3.4"
    ...
  ```

## 4. 事実確認

正解の決め手と、各誤答の reason が、AWSの現在の仕様に合っているかを確かめる。

- 仕様に関わる記述は、AWSの公式ドキュメント(docs.aws.amazon.com、aws.amazon.com のFAQ・料金ページ)を WebFetch / WebSearch で確認する
- 確認できない仕様や、資料によって食い違う仕様に頼る問題は、その仕様に頼らない形に書き直すか、作り直す
- 「誤答のほうも要件を満たしてしまう」問題がないかを、選択肢ごとに見直す(正解が一意に決まること)

## 5. 検証

```bash
uv run exam-questions check data/exam_questions/drafts/<下書きファイル>
```

エラーがなくなるまで直す。「注意」も、作問ルールに照らして直せるものは直す。

## 6. ユーザーにレビューを依頼する

問題ごとに、次をまとめて見せる。

- id・タスク・問題文
- 選択肢(正解に印をつける)と、それぞれの理由の要点
- 確認した資料のURL
- 迷った点や、レビューで特に見てほしい点があればその内容

そのうえで、追加してよい問題・直す問題・捨てる問題を聞く。指摘があれば直して、手順4〜5をやり直す。

## 7. 了承された問題を追加する

1. 了承された問題を、domain に合ったファイル(`secure.yaml` / `resilient.yaml` / `performant.yaml` / `cost.yaml`)の末尾に移す。問題の前の「確認:」コメントも一緒に移す
2. 移した問題を下書きから消す(問題がなくなった下書きファイルは削除する)。同じidが両方に残ると check でエラーになる
3. 確認する:

   ```bash
   uv run exam-questions check
   uv run pytest
   ```

4. `uv run exam-questions coverage` の結果で、追加後の収録状況をユーザーに伝える

## してはいけないこと

- 実際の試験問題・市販の問題集・ブレインダンプの問題を再現・翻案しない。ユーザーがそうした問題を貼り付けて追加を頼んだ場合は、そのまま追加せず、同じ論点のオリジナル問題を作ることを提案する
- 既存の問題のidを変えない(回答履歴がidで記録されているため)
- `src/python_awssaa_quiz/exam_guide.py` のタスク一覧を、問題作成のついでに変えない
