# Grape

문서 이미지 개인정보(PII) 탐지·합성 치환 파이프라인. 폐쇄망(내부망) 환경에서
문서 이미지 속 이름·주민등록번호·계좌번호·카드번호·주소 등을 탐지해 임의의
합성값으로 교체하고, 학습용 라벨(바운딩박스 + 엔티티 타입)을 생성한다.

전체 계획은 [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) 참조.

## 현재 상태 (Phase 1 PoC)

| 모듈 | 상태 |
|---|---|
| 룰 탐지 (주민번호/카드/계좌/전화/이메일, 체크섬 검증) | ✅ 동작 + 테스트 |
| 합성값 생성 (체크섬 유효, 포맷 보존) | ✅ 동작 + 테스트 |
| 파이프라인 text 모드 (OCR JSON → 라벨 JSON) | ✅ 동작 + 테스트 |
| LLM 탐지 (GPT-5.4, 이름/주소) | 🔌 구현됨 — 내부 엔드포인트 연결 필요 |
| 전처리 (방향 보정 + deskew) | 🔌 구현됨 — OpenCV 반입 후 검증 |
| OCR (PaddleOCR 한국어) | 🔌 래퍼만 — 모델 반입 후 검증 |
| 치환 렌더링 (인페인팅 + 텍스트) | 🔌 구현됨 — 폰트 반입 후 검증 |

## 빠른 시작

```bash
pip install -e ".[dev]"        # 코어는 의존성 없음 (faker 는 선택)
python -m pytest               # 단위테스트
python scripts/demo_text_mode.py   # 탐지→치환 E2E 데모 (가짜 PII 사용)
```

파이프라인 실행 (text 모드):

```bash
python -m grape_pii.pipeline ocr_result.json labels.json --seed 42
# LLM 탐지 포함: GRAPE_LLM_BASE_URL=http://<내부엔드포인트>/v1 붙여서 --use-llm
```

## 폐쇄망 반입

```bash
# 외부망에서 수집
pip download -r requirements.txt -d wheels/
# 폐쇄망에서 설치
pip install --no-index --find-links wheels/ -r requirements.txt
```

추가 반입 목록: PaddleOCR 한국어 det/rec 모델 + 방향 분류 모델, 한글 폰트(나눔고딕 등).

## 구조

```
src/grape_pii/
├── preprocess/   # 방향 보정(90°단위) + 미세 기울기 보정(deskew)
├── ocr/          # PaddleOCR 래퍼 (단어 단위 bbox)
├── detect/       # 룰 탐지(정규식+체크섬) + LLM 탐지(GPT-5.4)
├── synth/        # 합성값 생성 (Faker 선택, 내장 목록 폴백)
├── render/       # 배경 추정 + 텍스트 재렌더링
└── pipeline.py   # 실행기 (text 모드 / image 모드)
configs/          # 은행 계좌 패턴, LLM 프롬프트
tests/            # 단위테스트 (가짜 PII 만 사용)
```

## 정책

- **재현율 최우선**: 미탐 = 개인정보 유출. 형태가 맞으면 낮은 confidence 로라도 탐지.
- **매핑 미저장**: 라벨 출력에 원본값을 포함하지 않는다 (테스트로 강제).
- **체크섬 유효 합성값**: 치환값도 실제와 같은 형태 규칙을 만족 (Luhn, 주민번호 검증식).
