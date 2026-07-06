import json
import random

from grape_pii.pipeline import run_file, run_text
from grape_pii.synth.generators import make_rrn_digits


def _sample_tokens():
    d = make_rrn_digits(random.Random(2))
    return [
        {"text": "성명", "bbox": [10, 10, 60, 30]},
        {"text": "홍길동", "bbox": [70, 10, 140, 30]},
        {"text": "주민등록번호", "bbox": [10, 40, 130, 60]},
        {"text": f"{d[:6]}-{d[6:]}", "bbox": [140, 40, 300, 60]},
        {"text": "연락처", "bbox": [10, 70, 70, 90]},
        {"text": "010-1234-5678", "bbox": [80, 70, 220, 90]},
    ]


def test_run_text_detects_and_replaces():
    result = run_text(_sample_tokens(), seed=1)
    by_type = {e["type"]: e for e in result["entities"]}
    assert "RRN" in by_type and "PHONE" in by_type
    assert by_type["RRN"]["token_ids"] == [3]
    assert by_type["PHONE"]["token_ids"] == [5]
    assert by_type["PHONE"]["replacement"].startswith("010-")


def test_run_text_deterministic_with_seed():
    tokens = _sample_tokens()
    assert run_text(tokens, seed=7) == run_text(tokens, seed=7)


def test_labels_do_not_contain_original_pii():
    # 라벨 출력에 원본값이 남으면 안 됨 (매핑 미저장 정책)
    tokens = _sample_tokens()
    rrn_original = tokens[3]["text"]
    dumped = json.dumps(run_text(tokens, seed=1), ensure_ascii=False)
    assert rrn_original not in dumped


def test_run_file(tmp_path):
    src = tmp_path / "ocr.json"
    dst = tmp_path / "labels.json"
    src.write_text(json.dumps({"tokens": _sample_tokens()}, ensure_ascii=False), encoding="utf-8")

    result = run_file(src, dst, seed=1)
    saved = json.loads(dst.read_text(encoding="utf-8"))
    assert saved == result
    assert all("bboxes" in e for e in saved["entities"])
