"""exam-questions コマンド(問題データの確認)。"""

import yaml

import python_awssaa_quiz.exam_cli as cli


def question(qid, **overrides):
    q = {
        "id": qid,
        "domain": "cost",
        "task": "4.4",
        "question": "問題文",
        "choices": [
            {"text": "正解", "correct": True, "reason": "理由"},
            *({"text": f"誤答{i}", "reason": "理由"} for i in range(3)),
        ],
        "explanation": "解説",
        "related_keywords": [61],
    }
    q.update(overrides)
    return q


def write(path, questions):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(questions, allow_unicode=True), encoding="utf-8")
    return path


def use_dirs(monkeypatch, tmp_path):
    bank, drafts = tmp_path / "bank", tmp_path / "bank" / "drafts"
    bank.mkdir()
    monkeypatch.setattr(cli, "DEFAULT_EXAM_DIR", bank)
    monkeypatch.setattr(cli, "DRAFTS_DIR", drafts)
    return bank, drafts


def test_check_passes_bundled_bank(excel_path, capsys):
    assert cli.main(["check"]) == 0
    assert "エラーはありません" in capsys.readouterr().out


def test_check_reports_errors_and_duplicate_ids(excel_path, monkeypatch, tmp_path, capsys):
    bank, drafts = use_dirs(monkeypatch, tmp_path)
    write(bank / "cost.yaml", [question("E0001")])
    draft = write(
        drafts / "d.yaml",
        [question("E0001"), question("E0002", question="どれか。(2つ選択)", related_keywords=[9999])],
    )
    assert cli.main(["check", str(draft)]) == 1
    out = capsys.readouterr().out
    assert "E0001 エラー: id が重複" in out
    assert "E0002 エラー: 問題文に「〇つ選択」" in out
    assert "E0002 エラー: related_keywords" in out


def test_check_reports_format_errors(excel_path, monkeypatch, tmp_path, capsys):
    bank, drafts = use_dirs(monkeypatch, tmp_path)
    broken = write(drafts / "d.yaml", [question("E0003", task="1.1")])
    assert cli.main(["check", str(broken)]) == 1
    assert "task は" in capsys.readouterr().out


def test_coverage_and_next_id(monkeypatch, tmp_path, capsys):
    bank, drafts = use_dirs(monkeypatch, tmp_path)
    write(bank / "cost.yaml", [question("E0001"), question("E0002")])
    write(drafts / "d.yaml", [question("E0007")])
    assert cli.main(["coverage"]) == 0
    out = capsys.readouterr().out
    assert "   2 (     0)      1  4.4" in out and "合計 2問(下書き 1問)" in out
    assert cli.main(["next-id", "2"]) == 0
    assert capsys.readouterr().out.split() == ["E0008", "E0009"]
