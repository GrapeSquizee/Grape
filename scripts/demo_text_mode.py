"""text 모드 E2E 데모 — 가짜 PII 로 만든 OCR 결과를 파이프라인에 통과시킨다.

사용: python scripts/demo_text_mode.py
(실제 문서 없이 탐지→치환 로직을 확인하는 용도. 모든 값은 합성값이다.)
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from grape_pii.pipeline import run_text
from grape_pii.synth.generators import make_card_digits, make_rrn_digits

rng = random.Random(20260706)
rrn = make_rrn_digits(rng)
card = make_card_digits(16, rng)

tokens = [
    {"text": "개인정보", "bbox": [40, 20, 120, 44]},
    {"text": "수집·이용", "bbox": [128, 20, 220, 44]},
    {"text": "동의서", "bbox": [228, 20, 300, 44]},
    {"text": "성명:", "bbox": [40, 80, 90, 104]},
    {"text": "김철수", "bbox": [100, 80, 170, 104]},
    {"text": "주민등록번호:", "bbox": [40, 120, 170, 144]},
    {"text": f"{rrn[:6]}-{rrn[6:]}", "bbox": [180, 120, 340, 144]},
    {"text": "휴대전화:", "bbox": [40, 160, 130, 184]},
    {"text": "010-2345-6789", "bbox": [140, 160, 290, 184]},
    {"text": "카드번호:", "bbox": [40, 200, 130, 224]},
    {"text": "-".join(card[i:i + 4] for i in range(0, 16, 4)), "bbox": [140, 200, 360, 224]},
    {"text": "환불계좌:", "bbox": [40, 240, 130, 264]},
    {"text": "국민은행", "bbox": [140, 240, 220, 264]},
    {"text": "123456-01-234567", "bbox": [230, 240, 410, 264]},
    {"text": "이메일:", "bbox": [40, 280, 110, 304]},
    {"text": "chulsoo.kim@example.com", "bbox": [120, 280, 380, 304]},
]

result = run_text(tokens, seed=42)

print("=== 입력 토큰 ===")
for i, t in enumerate(tokens):
    print(f"  [{i:2d}] {t['text']}")
print("\n=== 탐지·치환 결과 ===")
for e in result["entities"]:
    original = " ".join(tokens[i]["text"] for i in e["token_ids"])
    print(f"  {e['type']:8s} conf={e['confidence']:.2f} src={e['source']:4s} "
          f"tokens={e['token_ids']} | {original} → {e['replacement']}")
print("\n=== 라벨 JSON (원본값 미포함) ===")
print(json.dumps(result, ensure_ascii=False, indent=2))
