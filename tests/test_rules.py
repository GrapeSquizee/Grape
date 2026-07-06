"""룰 탐지기 테스트. 테스트에 쓰는 PII 는 모두 생성기가 만든 가짜값이다."""
import random

from grape_pii.detect.rules import (
    detect_account, detect_all, detect_card, detect_email, detect_phone,
    detect_rrn, luhn_ok, rrn_checksum,
)
from grape_pii.synth.generators import make_card_digits, make_rrn_digits


def test_rrn_checksum_roundtrip():
    rng = random.Random(42)
    for _ in range(50):
        d = make_rrn_digits(rng)
        assert len(d) == 13
        assert rrn_checksum(d[:12]) == int(d[12])


def test_detect_rrn_with_and_without_hyphen():
    d = make_rrn_digits(random.Random(1))
    hyphenated = f"{d[:6]}-{d[6:]}"
    for text in (f"주민등록번호 {hyphenated} 본인", f"주민등록번호 {d} 본인"):
        found = detect_rrn(text)
        assert len(found) == 1
        assert found[0].confidence == 1.0


def test_detect_rrn_post2020_random_tail():
    # 2020.10 이후 발급분은 체크섬 불성립 — 낮은 confidence 로라도 탐지해야 함
    found = detect_rrn("번호 010203-4999999 끝")
    assert len(found) == 1
    assert found[0].confidence == 0.8


def test_rrn_invalid_date_rejected():
    assert detect_rrn("991345-1234567") == []  # 13월
    assert detect_rrn("990232-1234567") == []  # 2월 32일


def test_luhn_and_card_detection():
    rng = random.Random(7)
    for _ in range(30):
        digits = make_card_digits(16, rng)
        assert luhn_ok(digits)
        grouped = "-".join(digits[i:i + 4] for i in range(0, 16, 4))
        assert any(d.confidence == 1.0 for d in detect_card(f"카드번호 {grouped}"))
        assert any(d.confidence == 1.0 for d in detect_card(f"카드번호 {digits}"))


def test_card_grouped_luhn_fail_still_detected():
    # 구분자 있는 카드형태는 Luhn 실패여도 탐지 (OCR 오독 대비, 재현율 우선)
    found = detect_card("4111-1111-1111-1112")
    assert len(found) == 1
    assert found[0].confidence < 1.0


def test_card_bare_luhn_fail_not_detected():
    assert detect_card("4111111111111112") == []


def test_detect_phone():
    assert detect_phone("연락처 010-1234-5678")[0].text == "010-1234-5678"
    assert detect_phone("Tel 02-345-6789")[0].text == "02-345-6789"
    assert detect_phone("no phone 123-4567 here") == []


def test_detect_email():
    assert detect_email("문의: hong@example.co.kr 로")[0].text == "hong@example.co.kr"


def test_detect_account_with_context():
    found = detect_account("입금계좌 국민은행 123456-01-234567")
    assert len(found) == 1
    assert found[0].confidence == 0.9


def test_detect_account_without_context_lower_conf():
    found = detect_account("번호는 123456-01-234567 입니다")
    assert found and found[0].confidence == 0.6


def test_detect_all_no_overlap():
    d = make_rrn_digits(random.Random(3))
    rrn = f"{d[:6]}-{d[6:]}"
    text = f"성명 홍길동 주민번호 {rrn} 연락처 010-9876-5432 계좌 국민 123456-01-234567"
    found = detect_all(text)
    types = [f.type for f in found]
    assert "RRN" in types and "PHONE" in types and "ACCOUNT" in types
    for i, a in enumerate(found):
        for b in found[i + 1:]:
            assert not a.overlaps(b)


def test_rrn_not_misdetected_as_account():
    # 주민번호 형태(6-7)는 generic 계좌 패턴과 겹치지만 RRN 이 우선해야 함
    d = make_rrn_digits(random.Random(9))
    found = detect_all(f"계좌 및 주민번호 {d[:6]}-{d[6:]}")
    assert [f.type for f in found] == ["RRN"]
