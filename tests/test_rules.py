"""룰 탐지기 테스트. 테스트에 쓰는 PII 는 모두 생성기가 만든 가짜값이다."""
import random

from grape_pii.detect.rules import (
    detect_account, detect_address, detect_all, detect_card, detect_date,
    detect_email, detect_name, detect_phone, detect_rrn, luhn_ok, rrn_checksum,
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


def test_detect_rrn_masked_tail():
    # 증명서 견본의 마스킹 형태 (뒷자리 * 처리) 도 탐지해야 함
    for text in ("650101-1******", "400401-1******", "번호 030201-3●●●●●● 끝"):
        found = detect_rrn(text)
        assert len(found) == 1, text
        assert found[0].confidence == 0.9


def test_detect_rrn_masked_ocr_variants():
    # OCR 이 * 개수를 다르게 읽거나(5/7개) 공백을 끼워 읽는 경우
    for text in ("680202-2*****", "650101-1*******", "750123-1 ******"):
        assert len(detect_rrn(text)) == 1, text


def test_detect_address_rule():
    found = detect_address("등록기준지 서울특별시 영등포구 여의도동 1번지의 1234")
    assert len(found) == 1
    assert found[0].text.startswith("서울특별시")
    assert "1번지의 1234" in found[0].text
    assert detect_address("경기도 수원시 팔달구 정조로 825") != []
    assert detect_address("주소 없는 문장입니다") == []


def test_masked_rrn_invalid_date_rejected():
    assert detect_rrn("651301-1******") == []  # 13월


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


def test_detect_date_formats():
    for text in ("1965년 01월 01일", "1965.1.1", "2003-02-01", "출생 1942년 04월 02일 끝"):
        assert len(detect_date(text)) == 1, text


def test_detect_date_invalid_rejected():
    assert detect_date("2020년 13월 01일") == []
    assert detect_date("1234-56-78") == []


def test_detect_name_hanja():
    found = detect_name("성명 김본인(金本人) 출생")
    assert len(found) == 1
    assert found[0].text == "김본인(金本人)"


def test_detect_name_hanja_with_space_and_garbled():
    # OCR 이 이름과 괄호를 띄어 읽거나 한자를 일부 오독해도 잡혀야 함
    assert len(detect_name("부 김영철 (金晄쒜) 1954년")) == 1
    assert len(detect_name("모 이은미(李恩美) 1942년")) == 1


def test_document_title_not_a_name():
    # "증명서(일반)" 같은 문서 제목 꼬리가 이름으로 오탐되면 안 됨
    assert detect_name("가족관계증명서(일반)") == []
    assert detect_name("위 가족관계증명서(일반)는 기록사항과 틀림없음") == []
    assert detect_name("가 족 관 계 증 명 서 (일반)") == []


def test_detect_name_relation_when_hanja_garbled():
    # OCR 이 한자를 전부 한글로 오독하거나 괄호를 잃어도 구분 키워드 뒤 이름을 잡음
    assert [f.text for f in detect_name("본인 김본인(김본인) 1965년")] == ["김본인"]
    assert [f.text for f in detect_name("부 김영철 1972년 12월 11일")] == ["김영철"]
    assert [f.text for f in detect_name("배우자 박여인 1970년")] == ["박여인"]


def test_fullwidth_punctuation_normalized():
    # OCR 이 전각 괄호/콜론/하이픈/별표를 출력해도 detect_all 경유 시 잡혀야 함
    found = detect_all("본인 김본인（金本人） 650101－1＊＊＊＊＊＊")
    assert sorted(d.type for d in found) == ["NAME", "RRN"]
    found2 = detect_all("신청인 ： 김본인")
    assert [d.type for d in found2] == ["NAME"]


def test_detect_name_keyword():
    found = detect_name("신청인: 홍길동 (서명)")
    assert [f.text for f in found] == ["홍길동"]
    assert [f.text for f in detect_name("전산운영책임관 홍길동")] == ["홍길동"]
    assert [f.text for f in detect_name("신청인 : 김본인")] == ["김본인"]


def test_detect_name_stopwords_excluded():
    assert detect_name("성명 본인 확인") == []


def test_family_cert_like_row_detected():
    # 가족관계증명서 견본 형태: 한자병기 이름 + 생년월일 + 마스킹 주민번호
    text = "본인 김본인(金本人) 1965년 01월 01일 650101-1****** 남 金海"
    types = sorted(d.type for d in detect_all(text))
    assert types == ["DATE", "NAME", "RRN"]


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
