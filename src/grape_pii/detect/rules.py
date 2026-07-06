"""룰 기반 PII 탐지 — 정규식 + 체크섬/유효성 검증.

숫자형 PII(주민번호, 카드번호, 계좌번호, 전화번호)는 룰이 LLM보다 정확하고 싸다.
정책: 재현율 최우선 — 형태가 맞으면 일단 탐지하고, 체크섬 통과 여부는
confidence 로만 반영한다 (미탐 = 개인정보 유출).
"""
import calendar
import json
import re
from pathlib import Path

from .models import Detection

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "configs"

# ── 주민등록번호 ──────────────────────────────────────────────
# 2020.10 이후 발급분은 뒷자리가 무작위라 체크섬이 성립하지 않으므로,
# 체크섬은 탐지 여부가 아니라 confidence 에만 반영한다.
# 증명서 견본류는 뒷자리가 마스킹된 형태(650101-1******)로 나오므로 함께 탐지한다.
# OCR 이 * 를 ●·× 등으로 오독하는 경우까지 마스크 문자로 허용한다.
_RRN_RE = re.compile(r"(?<![\d-])(\d{6})[- ]?([0-9]\d{6})(?![\d-])")
# 마스크 문자 개수는 OCR 이 6개를 5~7개로 오독하는 경우가 흔해 3~10개 허용
_RRN_MASKED_RE = re.compile(r"(?<![\d-])(\d{6})[- ]?([0-9]) ?([*●○•xX×＊★☆]{3,10})")
_RRN_WEIGHTS = (2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5)
_GENDER_CENTURY = {"1": 1900, "2": 1900, "3": 2000, "4": 2000,
                   "5": 1900, "6": 1900, "7": 2000, "8": 2000,
                   "9": 1800, "0": 1800}


def rrn_checksum(digits12: str) -> int:
    s = sum(int(d) * w for d, w in zip(digits12, _RRN_WEIGHTS))
    return (11 - s % 11) % 10


def _valid_rrn_date(front6: str, gender: str) -> bool:
    century = _GENDER_CENTURY.get(gender)
    if century is None:
        return False
    year = century + int(front6[:2])
    month, day = int(front6[2:4]), int(front6[4:6])
    if not 1 <= month <= 12:
        return False
    return 1 <= day <= calendar.monthrange(year, month)[1]


def detect_rrn(text: str) -> list[Detection]:
    out = []
    for m in _RRN_RE.finditer(text):
        front, back = m.group(1), m.group(2)
        if not _valid_rrn_date(front, back[0]):
            continue
        digits = front + back
        conf = 1.0 if rrn_checksum(digits[:12]) == int(digits[12]) else 0.8
        out.append(Detection("RRN", m.group(0), m.start(), m.end(), conf))
    for m in _RRN_MASKED_RE.finditer(text):
        if not _valid_rrn_date(m.group(1), m.group(2)):
            continue
        out.append(Detection("RRN", m.group(0), m.start(), m.end(), 0.9))
    return out


# ── 카드번호 ─────────────────────────────────────────────────
# 13~19자리, 국내 카드 BIN 은 3/4/5/6/9 로 시작. 4-4-4-4 등 구분자가 있으면
# Luhn 실패여도 탐지(저해상도 OCR 오독 가능성), 구분자 없는 연속 숫자는
# Luhn 통과를 요구해 오탐을 줄인다.
_CARD_RE = re.compile(r"(?<![\d-])([3-69]\d{3}([- ]?)\d{4}\2\d{4}\2\d{1,4}|[3-69]\d{12,18})(?![\d-])")


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def detect_card(text: str) -> list[Detection]:
    out = []
    for m in _CARD_RE.finditer(text):
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if not 13 <= len(digits) <= 19:
            continue
        grouped = bool(re.search(r"[- ]", raw))
        if luhn_ok(digits):
            conf = 1.0
        elif grouped:
            conf = 0.7
        else:
            continue  # 구분자 없는 Luhn 실패 숫자열은 카드로 보지 않음
        out.append(Detection("CARD", raw, m.start(), m.end(), conf))
    return out


# ── 계좌번호 ─────────────────────────────────────────────────
# 은행별 자릿수 패턴은 configs/bank_patterns.json 에서 로드.
# 패턴 일치 + 주변 문맥 키워드(계좌/은행명)가 있으면 confidence 를 올린다.
_ACCOUNT_CONTEXT_RE = re.compile(
    r"계좌|입금|출금|송금|은행|뱅크|농협|국민|신한|우리|하나|기업|수협|새마을|카카오|케이뱅크|토스"
)
_CONTEXT_WINDOW = 30


def _load_bank_patterns() -> list[dict]:
    path = _CONFIG_DIR / "bank_patterns.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["patterns"]


_BANK_PATTERNS = None


def _bank_patterns() -> list[dict]:
    global _BANK_PATTERNS
    if _BANK_PATTERNS is None:
        _BANK_PATTERNS = [
            {"bank": p["bank"], "re": re.compile(p["regex"])}
            for p in _load_bank_patterns()
        ]
    return _BANK_PATTERNS


def detect_account(text: str) -> list[Detection]:
    # 은행별 패턴과 generic 패턴이 같은 스팬에 중복 매치될 수 있으므로,
    # 설정 파일 순서(특이적 패턴 우선)대로 겹치는 스팬은 최초 매치만 남긴다.
    out: list[Detection] = []
    for p in _bank_patterns():
        for m in p["re"].finditer(text):
            ctx = text[max(0, m.start() - _CONTEXT_WINDOW): m.end() + _CONTEXT_WINDOW]
            conf = 0.9 if _ACCOUNT_CONTEXT_RE.search(ctx) else 0.6
            d = Detection("ACCOUNT", m.group(0), m.start(), m.end(), conf)
            if not any(d.overlaps(existing) for existing in out):
                out.append(d)
    return out


# ── 전화번호 ─────────────────────────────────────────────────
_PHONE_RE = re.compile(
    r"(?<![\d-])(01[016789][- ]?\d{3,4}[- ]?\d{4}|0(2|[3-6]\d)[- ]?\d{3,4}[- ]?\d{4})(?![\d-])"
)


def detect_phone(text: str) -> list[Detection]:
    return [
        Detection("PHONE", m.group(0), m.start(), m.end(), 0.95)
        for m in _PHONE_RE.finditer(text)
    ]


# ── 생년월일/날짜 ────────────────────────────────────────────
# 1965년 01월 01일 / 1965.1.1 / 1965-01-01 형태. 발급일 등 비개인 날짜도
# 함께 잡히지만, 학습데이터 익명화 관점에서는 모두 치환해도 잃는 것이 없다
# (재현율 우선). 단 생년월일-주민번호 앞자리 일관성은 아직 연동하지 않는다.
_DATE_RE = re.compile(
    r"(?<!\d)((?:19|20)\d{2})[년.\-/]\s*(\d{1,2})[월.\-/]\s*(\d{1,2})일?(?!\d)"
)


def detect_date(text: str) -> list[Detection]:
    out = []
    for m in _DATE_RE.finditer(text):
        month, day = int(m.group(2)), int(m.group(3))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue
        out.append(Detection("DATE", m.group(0), m.start(), m.end(), 0.8))
    return out


# ── 주소 (룰 보조) ───────────────────────────────────────────
# 한국 주소는 시/도명으로 시작하는 정형성이 있어 룰로 1차 탐지한다.
# 상세주소(동/호 등) 꼬리는 놓칠 수 있으므로 LLM 탐지가 보완한다.
_ADDRESS_RE = re.compile(
    r"(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|"
    r"세종특별자치시|경기도|강원특별자치도|강원도|충청북도|충청남도|전북특별자치도|"
    r"전라북도|전라남도|경상북도|경상남도|제주특별자치도|제주도|"
    r"서울시|부산시|대구시|인천시|광주시|대전시|울산시)"
    r"[ ]?[가-힣\d\s\-·.]{2,60}?"
    r"\d+(?:-\d+)?(?:번지)?(?:의 ?\d+)?(?:호|층|동)?"
)


def detect_address(text: str) -> list[Detection]:
    return [
        Detection("ADDRESS", m.group(0), m.start(), m.end(), 0.7)
        for m in _ADDRESS_RE.finditer(text)
    ]


# ── 이름 (룰 보조) ───────────────────────────────────────────
# 문맥 전체를 보는 이름 탐지는 LLM 담당이지만, 형태만으로 확실한 두 경우는
# 룰로 잡는다: ① 한자 병기 이름 "김본인(金本人)" ② 성명/신청인 등 라벨 뒤 이름.
# 오탐 방지 제약:
# - 앞이 한글이면 제외 — "가족관계증명서(일반)" 의 "증명서(일반)" 같은 단어 꼬리 매치 방지
# - 괄호 안에 한자가 1자 이상 있어야 함 — "(일반)", "(서명)" 같은 한글 괄호 제외.
#   OCR 이 한자를 일부 한글로 오독해도(金晄쒜) 한자가 하나라도 남으면 잡힌다.
# - 이름과 괄호 사이 공백 허용 — OCR 토큰 분리 대응
_HANJA_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")
_NAME_HANJA_RE = re.compile(r"(?<![가-힣])([가-힣]{2,4}) ?\(([^)]{1,10})\)")
_NAME_KEYWORD_RE = re.compile(
    r"(성\s*명|이\s*름|신\s*청\s*인|예\s*금\s*주|세\s*대\s*주|보\s*호\s*자|"
    r"수\s*취\s*인|책\s*임\s*관|담\s*당\s*자|설\s*계\s*사|발\s*급\s*인)"
    r"\s*[:：]?\s*([가-힣]{2,4})(?![가-힣])"
)
_NAME_STOPWORDS = {
    "본인", "성명", "이름", "신청인", "예금주", "세대주", "보호자", "수취인",
    "대리인", "담당자", "배우자", "자녀", "서명", "날인", "확인", "책임관",
}


def detect_name(text: str) -> list[Detection]:
    out = []
    for m in _NAME_HANJA_RE.finditer(text):
        if m.group(1) in _NAME_STOPWORDS or not _HANJA_RE.search(m.group(2)):
            continue
        out.append(Detection("NAME", m.group(0), m.start(), m.end(), 0.8))
    for m in _NAME_KEYWORD_RE.finditer(text):
        if m.group(2) in _NAME_STOPWORDS:
            continue
        d = Detection("NAME", m.group(2), m.start(2), m.end(2), 0.6)
        if not any(d.overlaps(prev) for prev in out):  # 한자 병기 매치가 우선
            out.append(d)
    return out


# ── 이메일 ──────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def detect_email(text: str) -> list[Detection]:
    return [
        Detection("EMAIL", m.group(0), m.start(), m.end(), 0.95)
        for m in _EMAIL_RE.finditer(text)
    ]


# ── 통합 ────────────────────────────────────────────────────
# 우선순위: 겹치는 스팬은 먼저 탐지된(더 특이적인) 타입이 이긴다.
_DETECTORS = (detect_rrn, detect_card, detect_phone, detect_email,
              detect_account, detect_address, detect_date, detect_name)


def detect_all(text: str) -> list[Detection]:
    accepted: list[Detection] = []
    for detector in _DETECTORS:
        for d in detector(text):
            if not any(d.overlaps(a) for a in accepted):
                accepted.append(d)
    return sorted(accepted, key=lambda d: d.start)
