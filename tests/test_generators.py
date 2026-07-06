import random

from grape_pii.detect.rules import detect_all, luhn_ok, rrn_checksum
from grape_pii.synth.generators import (
    make_address, make_name, make_replacement, preserve_format,
)


def test_preserve_format():
    assert preserve_format("1234-5678 90", "0987654321") == "0987-6543 21"


def test_rrn_replacement_valid_and_format_preserved():
    rng = random.Random(0)
    original = "900101-1234567"
    for _ in range(20):
        rep = make_replacement("RRN", original, rng)
        assert rep[6] == "-" and len(rep) == 14
        digits = rep.replace("-", "")
        assert rrn_checksum(digits[:12]) == int(digits[12])


def test_card_replacement_luhn_valid():
    rng = random.Random(0)
    original = "4111-1111-1111-1111"
    for _ in range(20):
        rep = make_replacement("CARD", original, rng)
        assert rep.count("-") == 3
        assert luhn_ok(rep.replace("-", ""))


def test_masked_rrn_replacement_keeps_mask():
    rng = random.Random(0)
    rep = make_replacement("RRN", "650101-1******", rng)
    assert rep.endswith("******") and rep[6] == "-" and len(rep) == 14
    assert [d.type for d in detect_all(f"번호 {rep} 끝")] == ["RRN"]


def test_phone_replacement_keeps_prefix():
    rep = make_replacement("PHONE", "010-1234-5678", random.Random(0))
    assert rep.startswith("010-") and len(rep) == 13


def test_account_replacement_format():
    rep = make_replacement("ACCOUNT", "123456-01-234567", random.Random(0))
    parts = rep.split("-")
    assert [len(p) for p in parts] == [6, 2, 6]


def test_date_replacement_keeps_separators():
    rng = random.Random(0)
    rep = make_replacement("DATE", "1965년 01월 01일", rng)
    assert rep.endswith("일") and "년 " in rep and "월 " in rep
    assert rep != "1965년 01월 01일"
    dotted = make_replacement("DATE", "2020.11.04", rng)
    assert dotted.count(".") == 2


def test_name_and_address_nonempty():
    assert len(make_name(random.Random(0))) >= 2
    assert len(make_address(random.Random(0))) >= 5


def test_replacement_is_detectable():
    # 치환값도 원본과 같은 타입으로 재탐지되어야 함 (형태 보존 검증)
    rng = random.Random(5)
    rep = make_replacement("RRN", "900101-1234567", rng)
    assert [d.type for d in detect_all(f"번호 {rep} 끝")] == ["RRN"]


def test_replacement_differs_from_original():
    rng = random.Random(11)
    original = "900101-1234567"
    reps = {make_replacement("RRN", original, rng) for _ in range(10)}
    assert original not in reps
    assert len(reps) > 1
