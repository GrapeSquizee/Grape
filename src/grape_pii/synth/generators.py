"""합성(가짜) PII 생성기.

원칙:
- 원본과 동일한 포맷 보존: 구분자(하이픈/공백) 위치를 그대로 유지하고 숫자만 교체.
- 숫자형 PII 는 체크섬이 유효한 값을 생성 — 학습 모델이 "유효한 형태"를 배우도록.
- Faker(ko_KR) 가 있으면 이름/주소에 활용, 없으면 내장 목록으로 동작
  (폐쇄망 반입 전에도 파이프라인이 돌아가야 하므로).

생성값은 무작위이므로 실존 인물 정보와 우연히 일치할 가능성은 배제할 수 없다.
"""
import random
import re

from ..detect.rules import luhn_ok, rrn_checksum

try:
    from faker import Faker
    _faker = Faker("ko_KR")
except ImportError:  # 폐쇄망에서 Faker 미반입 시 내장 목록 사용
    _faker = None

_SURNAMES = "김이박최정강조윤장임한오서신권황안송류전홍"
_GIVEN = [
    "민준", "서연", "지후", "하은", "도윤", "지민", "서준", "수아", "예준", "지우",
    "현우", "채원", "건우", "유진", "우진", "소율", "지호", "예은", "준서", "다은",
]
_CITIES = ["서울특별시", "부산광역시", "대구광역시", "인천광역시", "대전광역시", "경기도 수원시", "경상남도 창원시"]
_DISTRICTS = ["중구", "동구", "서구", "남구", "북구", "성산구", "팔달구"]
_ROADS = ["중앙로", "번영로", "해안대로", "공단로", "산업로", "테헤란로", "가온길"]

_CARD_BINS = ["4", "51", "52", "53", "54", "55", "35", "62", "37", "94"]


def _rng(rng: random.Random | None) -> random.Random:
    return rng if rng is not None else random.Random()


def preserve_format(original: str, new_digits: str) -> str:
    """원본의 비숫자 문자(하이픈/공백 등) 위치를 유지하며 숫자만 교체."""
    it = iter(new_digits)
    return "".join(next(it) if ch.isdigit() else ch for ch in original)


def make_rrn_digits(rng: random.Random | None = None,
                    year_range: tuple[int, int] = (1950, 2005),
                    sex: str | None = None) -> str:
    """체크섬 유효한 주민등록번호 13자리 생성.

    sex: "M"/"F" 지정 시 성별 자리를 맞춘다 (문서 서식 생성용). None 이면 무작위.
    """
    r = _rng(rng)
    year = r.randint(*year_range)
    month = r.randint(1, 12)
    day = r.randint(1, 28)
    males, females = ("1", "3"), ("2", "4")
    pool = males if sex == "M" else females if sex == "F" else males + females
    gender = pool[0] if year < 2000 else pool[-1]
    if sex is None:
        gender = r.choice([g for g in pool if (year < 2000) == (g in "12")])
    front12 = f"{year % 100:02d}{month:02d}{day:02d}{gender}{r.randint(0, 99999):05d}"
    return front12 + str(rrn_checksum(front12))


def make_card_digits(length: int = 16, rng: random.Random | None = None) -> str:
    """Luhn 체크섬 유효한 카드번호 생성 (기본 16자리).

    요청 자릿수를 반드시 지킨다 — 포맷 보존 치환에서 원본 자릿수와 일치해야
    하므로, 자릿수에 안 맞는 BIN(예: 15자리 전용 Amex 37)은 후보에서 뺀다.
    """
    r = _rng(rng)
    candidates = [b for b in _CARD_BINS if len(b) < length and (b != "37" or length == 15)]
    bin_prefix = r.choice(candidates)
    body = bin_prefix + "".join(str(r.randint(0, 9)) for _ in range(length - len(bin_prefix) - 1))
    check = next(d for d in "0123456789" if luhn_ok(body + d))
    return body + check


def make_digits(n: int, rng: random.Random | None = None) -> str:
    r = _rng(rng)
    return "".join(str(r.randint(0, 9)) for _ in range(n))


def make_name(rng: random.Random | None = None) -> str:
    r = _rng(rng)
    if _faker is not None:
        return _faker.name()
    return r.choice(_SURNAMES) + r.choice(_GIVEN)


def make_address(rng: random.Random | None = None) -> str:
    r = _rng(rng)
    if _faker is not None:
        return _faker.address()
    return f"{r.choice(_CITIES)} {r.choice(_DISTRICTS)} {r.choice(_ROADS)} {r.randint(1, 200)}"


def make_replacement(entity_type: str, original: str, rng: random.Random | None = None) -> str:
    """엔티티 타입에 맞는 합성값 생성. 숫자형은 원본 포맷(구분자 위치) 보존."""
    r = _rng(rng)
    n_digits = sum(ch.isdigit() for ch in original)

    if entity_type == "RRN":
        return preserve_format(original, make_rrn_digits(r))
    if entity_type == "CARD":
        return preserve_format(original, make_card_digits(n_digits, r))
    if entity_type in ("ACCOUNT", "PHONE"):
        digits = make_digits(n_digits, r)
        if entity_type == "PHONE":  # 앞자리(통신망 번호)는 원본 유지해 형태 보존
            m = re.match(r"0\d{1,2}", re.sub(r"\D", "", original))
            prefix = m.group(0) if m else "010"
            digits = prefix + digits[len(prefix):]
        return preserve_format(original, digits)
    if entity_type == "NAME":
        return make_name(r)
    if entity_type == "ADDRESS":
        return make_address(r)
    if entity_type == "EMAIL":
        user = "".join(r.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(8))
        return f"{user}@example.com"
    raise ValueError(f"unknown entity type: {entity_type}")
