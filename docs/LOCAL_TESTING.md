# 로컬 테스트 가이드 (Windows / PowerShell 기준)

clone 후 아래 순서대로 진행하면 룰 탐지 → 이미지 E2E → LLM 탐지까지 전부
로컬에서 검증할 수 있다. 원격 세션에서 이미 통과한 항목: 단위테스트 29건,
Tesseract 기반 이미지 E2E, LLM 목 서버 테스트.

Linux/macOS 명령은 각 절 끝의 비고 참조.

## 0. 준비

Python 3.10 이상 필요 (3.11에서 검증됨). `python --version` 으로 확인.

```powershell
git clone https://github.com/GrapeSquizee/Grape.git
cd Grape
git checkout claude/pii-redaction-project-0x7q1l

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"        # 코어 + pytest
```

`Activate.ps1` 이 실행 정책에 막히면 (관리자 아님, 현재 사용자만):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

> Linux/macOS: `source .venv/bin/activate`

## 1. 단위테스트 + text 모드 데모 (의존성 추가 없이 바로)

```powershell
python -m pytest -q                    # 29 passed 나와야 정상
python scripts\demo_text_mode.py       # 탐지→치환 E2E (가짜 PII)
```

## 2. 이미지 E2E

### 2-1. 한글 폰트

Windows 는 맑은고딕이 기본 내장이므로 설치 불필요. 모든 image 명령에
`--font C:\Windows\Fonts\malgun.ttf` 를 붙인다.

> Ubuntu: `sudo apt install fonts-nanum` → 기본값 그대로 사용 가능.
> macOS: `--font /System/Library/Fonts/Supplemental/AppleGothic.ttf`

### 2-2. 가짜 문서 이미지 생성

```powershell
pip install pillow faker
python scripts\make_sample_doc.py sample.png --seed 42 --font C:\Windows\Fonts\malgun.ttf
```

### 2-3-A. Tesseract 경로 (가볍게 빠른 확인)

Tesseract 설치 (둘 중 하나):

```powershell
winget install UB-Mannheim.TesseractOCR
# 또는 https://github.com/UB-Mannheim/tesseract/wiki 인스톨러 실행
# 설치 시 "Additional language data" 에서 Korean 체크
```

한국어 팩을 설치에서 빠뜨렸다면 kor.traineddata 를 받아
`C:\Program Files\Tesseract-OCR\tessdata\` 에 복사한다.

```powershell
$env:PATH += ";C:\Program Files\Tesseract-OCR"   # 현재 세션에만 적용
pip install pytesseract opencv-python-headless numpy

python -m grape_pii.pipeline image sample.png redacted.png labels.json `
    --seed 7 --ocr-engine tesseract --font C:\Windows\Fonts\malgun.ttf
```

`redacted.png` 에서 주민번호/전화/카드/계좌가 새 값으로 바뀌었는지,
`labels.json` 에 bbox·타입이 기록됐는지 확인.

> Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-kor`
> macOS: `brew install tesseract tesseract-lang`

### 2-3-B. PaddleOCR 경로 (주력 엔진 — 내부망 반입 전 필수 확인)

```powershell
pip install paddleocr paddlepaddle

python -m grape_pii.pipeline image sample.png redacted_paddle.png labels_paddle.json `
    --seed 7 --font C:\Windows\Fonts\malgun.ttf
```

- 최초 실행 시 한국어 모델을 자동 다운로드한다 →
  **`$env:USERPROFILE\.paddlex\official_models` 폴더가 생기면 통째로 보관할 것.
  이 폴더가 내부망 반입 대상이다.**
- 다운로드 실패 시: `$env:PADDLE_PDX_MODEL_SOURCE = "BOS"` (또는 `"HuggingFace"`) 후 재실행.
- Tesseract 결과와 토큰 수·탐지 수를 비교해보면 엔진 간 품질 차이가 보인다.

## 3. LLM 탐지 라이브 테스트 (NVIDIA NIM)

```powershell
$env:GRAPE_LLM_BASE_URL = "https://integrate.api.nvidia.com/v1"
$env:GRAPE_LLM_API_KEY  = "nvapi-..."          # build.nvidia.com 발급 키
$env:GRAPE_LLM_MODEL    = "upstage/solar-10.7b-instruct"

python scripts\demo_llm_detect.py
```

확인 포인트:
- `LLM 단독 탐지` 에서 NAME(박서준, 이하은)과 ADDRESS(경기도…1102호)가 잡히는지
- JSON 파싱 오류가 나면 모델이 형식을 안 지킨 것 — `configs/prompts/detect_entities.txt`
  를 다듬거나 더 큰 모델로 교체 (내부망 GPT-5.4 에서는 문제 없을 가능성이 높음)

파이프라인에 통합해서 돌리려면:

```powershell
python -m grape_pii.pipeline image sample.png out.png labels.json `
    --ocr-engine tesseract --use-llm --seed 7 --font C:\Windows\Fonts\malgun.ttf
```

**주의: 외부 API(NIM)에는 반드시 가짜 데이터만 보낼 것.** 실문서 테스트는
내부망 GPT-5.4 연결 후에만 한다. 내부망에서는 `$env:GRAPE_LLM_BASE_URL` 을
내부 엔드포인트로, `$env:GRAPE_LLM_MODEL = "gpt-5.4"` 로 바꾸면 코드 수정 없이 동작한다.

## 4. 결과 체크리스트

| 항목 | 기준 |
|---|---|
| 단위테스트 | 29 passed |
| text 데모 | RRN/PHONE/CARD/ACCOUNT/EMAIL 5종 탐지, 치환값 형태 유지 |
| 이미지 E2E | 치환 이미지가 자연스러움 (배경/크기), 라벨 bbox 가 실제 위치와 일치 |
| PaddleOCR | 모델 자동 다운로드 성공, Tesseract 보다 토큰 인식 우수 |
| LLM 탐지 | NAME 2건 + ADDRESS 1건 탐지, JSON 형식 준수 |
| 보안 | labels.json 에 원본값이 없음 (매핑 미저장 정책) |

## 5. 문제 생기면

- `ModuleNotFoundError: grape_pii` → 리포 루트에서 `pip install -e .` 실행했는지 확인
- `TesseractNotFoundError` → PATH 에 Tesseract 폴더 추가 안 됨. 위의 `$env:PATH` 줄
  실행, 그래도 안 되면 파이썬에서
  `pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"`
- 렌더링 글자가 □□□ → `--font` 로 한글 폰트 경로 지정했는지 확인
- PowerShell 에서 여러 줄 명령이 안 이어짐 → 줄 끝의 백틱(`` ` ``) 뒤에 공백이 있으면
  안 된다. 한 줄로 붙여 써도 무방
- 스크립트 출력 한글이 깨짐 → `chcp 65001` 또는 `$OutputEncoding = [Text.Encoding]::UTF8`
- PaddleOCR 설치 시 PyYAML 충돌(리눅스 데비안 계열) → `pip install --ignore-installed PyYAML ...`
- PaddleOCR 실행 중 `NotImplementedError: ... ConvertPirAttribute2RuntimeAttribute not support`
  → paddle 3.x 의 Windows CPU(oneDNN/PIR) 버그. 엔진이 자동으로 oneDNN 을 끄고
  재시도한다 (`git pull` 로 최신 코드 필요). 추론이 다소 느려질 뿐 결과는 동일.
  pytest 임시폴더 권한 오류가 나면 → `python -m pytest -q --basetemp .pytest-tmp`
