# 내부망 개발 인수인계 문서

작성: 2026-07-06 / 브랜치: `claude/pii-redaction-project-0x7q1l`
외부(폐쇄망 밖)에서 개발·검증한 내용을 내부망(Cline + GPT-5.4)에서 이어가기 위한 문서.
전체 기획은 [PROJECT_PLAN.md](PROJECT_PLAN.md), 실행법은 [LOCAL_TESTING.md](LOCAL_TESTING.md) 참조.

## 1. 프로젝트 한 줄 요약

문서 이미지에서 개인정보(이름·주민번호·계좌·카드·주소·생년월일 등)를 탐지해
**체크섬이 유효한 합성값으로 교체한 이미지 + 라벨(bbox/타입)** 을 만들어
학습용 데이터셋으로 쓴다. 단순 마스킹이 아니라 형태 보존 치환.

## 2. 현재 완성도

| 모듈 | 상태 | 검증 수준 |
|---|---|---|
| 룰 탐지 (RRN/CARD/ACCOUNT/PHONE/EMAIL/DATE/ADDRESS/NAME) | ✅ 완성 | 단위테스트 + **실제 가족관계증명서 스캔으로 검증** (19/19 엔티티) |
| 합성값 생성 (체크섬 유효, 포맷 보존) | ✅ 완성 | 단위테스트 (생성값 재탐지 검증 포함) |
| 파이프라인 text 모드 (OCR JSON→라벨) | ✅ 완성 | 단위테스트 + 실측 토큰 파일 |
| 파이프라인 image 모드 (이미지→치환 이미지+라벨) | ✅ 완성 | Windows + PaddleOCR 실검증 완료 |
| 치환 렌더링 (배경 추정 + 폰트 크기 역산) | ✅ 완성 | 육안 검증 완료 |
| OCR — PaddleOCR (주력, 2.x/3.x 겸용) | ✅ 완성 | Windows 실검증 (oneDNN 버그 자동 폴백 포함) |
| OCR — Tesseract (대체) | ✅ 완성 | E2E 검증 완료 |
| 전처리 — deskew | ✅ 연결됨 | image 모드에 포함 |
| 전처리 — 90° 방향 보정 | 🔌 구현만 | `fix_orientation()` 휴리스틱 있음, 파이프라인 미연결 |
| **LLM 탐지 (이름/주소 문맥 탐지)** | 🔌 목 테스트만 | **내부 GPT-5.4 로 라이브 검증 필요 ← 최우선** |
| **VLM 텍스트 교정 (OCR 오독 보정)** | 🔌 목 테스트만 | **로컬 Gemma(gemma4-31b-4bit)로 라이브 검증 필요 ← 최우선** |

테스트: `python -m pytest -q` → **57 passed** 상태 유지할 것.

## 3. 아키텍처

```
이미지 → [preprocess] deskew → [ocr] PaddleOCR/Tesseract (bbox+텍스트)
       → (--vlm-correct) [ocr/vlm] 로컬 VLM 이 오독 텍스트 교정 (bbox 불변)
       → [detect/rules] 정규식+체크섬 (숫자형·정형 PII)
       → (--use-llm)   [detect/llm] LLM 이 문맥 엔티티(이름/주소) 보강
       → [synth] 체크섬 유효 합성값 생성 (포맷 보존)
       → [render] 원본 영역 지우고 합성값 렌더링
       → 치환 이미지 + labels.json (원본값 미포함)
```

| 경로 | 역할 |
|---|---|
| `src/grape_pii/detect/rules.py` | 룰 탐지 전부. 전각→반각 정규화(`normalize_text`)가 `detect_all` 입구에 있음 |
| `src/grape_pii/detect/llm.py` | OpenAI 호환 클라이언트(`LLMClient`, 비전 입력 지원) + 엔티티 탐지 |
| `src/grape_pii/detect/models.py` | `Detection` 데이터클래스 |
| `src/grape_pii/synth/generators.py` | 합성값 생성. `make_rrn_digits(year_range, sex)` 등 |
| `src/grape_pii/ocr/engine.py` | `OcrEngine`(Paddle 2.x/3.x 자동판별, oneDNN 폴백), `TesseractEngine`, `create_engine` |
| `src/grape_pii/ocr/vlm.py` | `VlmReader` — OCR 결과를 로컬 VLM 으로 교정하는 래퍼 |
| `src/grape_pii/preprocess/geometry.py` | deskew, 방향 보정 |
| `src/grape_pii/render/redact.py` | 영역 치환 렌더링 / `fonts.py` OS 별 한글 폰트 자동 탐색 |
| `src/grape_pii/pipeline.py` | CLI 진입점 (`text` / `image` 서브커맨드) |
| `configs/bank_patterns.json` | 은행별 계좌 패턴 (근사치 — 실데이터로 보정 필요) |
| `configs/prompts/` | LLM 엔티티 탐지 / VLM 토큰 교정 프롬프트 |
| `scripts/` | 가짜 문서 생성기 2종, 데모 2종 |

## 4. 핵심 설계 결정과 이유 (변경 전 반드시 읽을 것)

1. **재현율 최우선.** 미탐 = 개인정보가 학습데이터로 유출. 애매하면 잡아서 치환한다.
   오탐(불필요한 치환)은 학습데이터 품질에 거의 무해하므로 감수한다.
   confidence 는 탐지 여부가 아니라 검수 우선순위용.
2. **숫자형은 룰, 문맥형은 LLM.** 주민번호(검증식)·카드(Luhn)·계좌·전화·날짜는
   룰이 LLM 보다 정확하고 싸다. 이름·주소만 LLM 에 맡기되, 형태로 확실한 경우
   (한자병기, 라벨 키워드 뒤, 가족관계 구분 뒤)는 룰이 선점한다.
3. **합성값도 체크섬 유효 + 포맷 보존.** 학습 모델이 "유효한 형태"를 배우도록.
   주민번호는 검증식, 카드는 Luhn 통과값 생성. 하이픈/마스킹(*) 위치는 원본 그대로.
4. **라벨에 원본값 절대 미포함.** 원본↔치환 매핑은 그 자체가 개인정보.
   `test_labels_do_not_contain_original_pii` 가 이를 강제한다. 깨뜨리지 말 것.
5. **OCR bbox + VLM 텍스트 하이브리드.** VLM 은 텍스트를 잘 읽지만 좌표를 못 주고,
   OCR 은 반대. 치환 렌더링에 bbox 가 필수라 역할을 나눴다. 문서당 VLM 호출 1회.
6. **개인정보가 나가는 LLM/VLM 은 내부망·로컬 전용.** 외부 API(NIM 등)에는
   가짜 데이터만 보냈다. 내부에서는 GPT-5.4(탐지)와 로컬 Gemma(교정) 사용 예정.
7. **seed 재현성.** 같은 seed → 같은 치환 결과 (Faker 도 rng 로 시드 고정).

## 5. 실측에서 배운 OCR 오독 사례집 (룰이 이를 방어 중)

실제 스캔 문서(가족관계증명서, 저해상도+워터마터+도장)에서 PaddleOCR 한국어
모델이 실제로 낸 출력. 룰 수정 시 이 케이스들이 회귀하지 않도록 테스트에 있음.

| 원본 | OCR 실측 출력 | 대응 |
|---|---|---|
| 김본인(金本人) | `검본인(시)`, `김영천()`, `이은미()` | 한자 소실 → 빈 괄호 이름 룰, 구분 키워드(본인/부/모/배우자/자녀) 룰 |
| 650101-1****** | `650101-1*****`, `680202-2*`, `420402-2 ******` | 마스크 1~10개 + 공백 허용 |
| 신청인 | `신정인` | 키워드 오독 허용 `신[청정]인` |
| 책임관 | `재임관` | `[책재]임관` |
| 홍길동 | `홍질동` | 키워드 뒤 이름이라 탐지엔 영향 없음 |
| ( ) : - 숫자 | 전각 `（）：－＊` | `normalize_text` 전각→반각 (1:1, 오프셋 보존) |
| 구분 칸 "모" | `..` | 빈 괄호 이름 룰이 커버 |
| 가족관계증명서(일반) | `가족관계중명서(일반)` | 이름 오탐 방지: 앞글자 한글 제외 + 괄호 안 한자 필수 |

근본 해결은 VLM 교정(`--vlm-correct`)이고, 위 룰들은 VLM 없이/실패 시의 안전망.

## 6. 설정 레퍼런스

환경변수 (모두 OpenAI 호환 API 기준):

| 변수 | 용도 | 내부망 값 예시 |
|---|---|---|
| `GRAPE_LLM_BASE_URL` | 엔티티 탐지 LLM | `http://<GPT-5.4 엔드포인트>/v1` |
| `GRAPE_LLM_API_KEY` | (필요 시) | |
| `GRAPE_LLM_MODEL` | 모델명 | `gpt-5.4` (기본값) |
| `GRAPE_VLM_BASE_URL` | OCR 교정 VLM | `http://<로컬 Gemma 서버>/v1` |
| `GRAPE_VLM_MODEL` | 모델명 | `gemma4-31b-4bit` |

CLI:

```bash
python -m grape_pii.pipeline image <입력> <치환이미지> <라벨json> \
    [--ocr-engine paddle|tesseract] [--vlm-correct] [--use-llm] \
    [--font <경로>] [--seed N] [--dump-tokens tokens.json]
```

- `--dump-tokens`: OCR(+VLM 교정 후) 토큰 덤프. 탐지 문제 진단은 항상 여기서 시작.
  `"vlm_corrected": true` 가 붙은 토큰이 VLM 이 고친 것.
- API 스펙이 OpenAI 호환이 아니면 `LLMClient.chat()` 한 메서드만 교체하면 된다.

## 7. 내부망 전환 체크리스트

- [ ] Nexus 로 `pip install -r requirements.txt` (wheel 반입 불필요 확인됨)
- [ ] PaddleOCR 모델 폴더 반입: 외부에서 받은 `~/.paddlex/official_models`
      (Windows: `%USERPROFILE%\.paddlex\official_models`) 통째로 복사
- [ ] 한글 폰트 확인 (Windows 맑은고딕 내장 → 추가 작업 없음. Linux 서버면 나눔고딕 반입)
- [ ] (선택) Tesseract + kor 팩 — Paddle 문제 시 대체 엔진
- [ ] GPT-5.4 연결: `GRAPE_LLM_*` 설정 → `python scripts/demo_llm_detect.py` 로 검증
- [ ] GPT-5.4 확인사항: 멀티모달 여부 / JSON 출력 안정성 / **서버측 프롬프트 로깅 정책**
      (프롬프트에 원문 PII 가 들어가므로 로그도 개인정보 통제 대상)
- [ ] 로컬 VLM(Gemma) 서버 구동 → `--vlm-correct` 로 실문서 교정 품질 확인
- [ ] 원본 이미지 저장소와 치환 산출물 저장소 분리 (원본은 접근통제 구역)

## 8. 다음 작업 (우선순위순)

**P1 — 라이브 검증 (코드는 다 있음, 연결만)**
1. GPT-5.4 로 이름/주소 LLM 탐지 검증. JSON 이 깨지면
   `configs/prompts/detect_entities.txt` 튜닝. 룰 NAME/ADDRESS 와의 중복은
   파이프라인이 룰 우선으로 자동 정리함.
2. Gemma VLM 교정 검증. `--dump-tokens` 로 교정 전후 비교.
   프롬프트는 `configs/prompts/correct_tokens.txt`.

**P2 — 품질 측정과 정확도**
3. 재현율 측정 도구: 정답 라벨(사람이 만든) vs 탐지 결과를 비교해
   미탐/오탐 리포트를 내는 스크립트. QA 루프(계획서 Phase 3)의 기반.
4. 2차 스크리닝: 치환 완료 이미지를 다시 OCR(+VLM)→탐지에 통과시켜
   "남은 PII 0건" 확인하는 게이트. 미탐 최종 방어선.
5. 엔티티 일관성: 현재 생년월일·주민번호 앞자리·성별 칸이 서로 독립적으로
   치환됨. 같은 행(사람)의 값들을 연동 생성하도록 개선.
   (`make_rrn_digits(year_range, sex)` 는 이미 파라미터가 있음)
6. `configs/bank_patterns.json` 을 실계좌 형식 기준으로 보정.

**P3 — 규모화**
7. 배치 실행기: 폴더 단위 처리, 실패 재시도, 처리 이력(감사 로그).
8. 단어 bbox 정밀화: 지금은 라인 bbox 를 문자수 비례로 분할(근사).
   PaddleOCR det 폴리곤을 단어 단위로 쓰거나 문자 단위 분할로 개선.
9. 90° 방향 보정 파이프라인 연결 (`fix_orientation` + OCR 신뢰도, 또는
   PaddleOCR 3.x 의 `use_doc_orientation_classify=True`).
10. Label Studio 검수 연동 (라벨 포맷 변환기), COCO/YOLO 익스포터.

## 9. 알려진 한계·이슈

- **생년월일↔주민번호 불일치**: 각자 독립 치환 (P2-5 에서 해결 예정)
- `신정인:김본인` 처럼 라벨과 이름이 한 토큰이면 토큰 전체가 이름으로 치환되어
  "신청인:" 라벨 텍스트가 사라짐 (렌더링이 토큰 bbox 단위라서). 경미한 이슈.
- generic 계좌 패턴은 문맥 키워드 없으면 conf 0.6 — 전화번호 아닌 하이픈 숫자열
  오탐 가능 (재현율 우선 정책상 허용)
- paddle 3.x Windows CPU oneDNN 버그 → 자동 폴백 있음 (`engine.py` 참조, 느려질 뿐 정상)
- pytest 임시폴더 권한 오류(회사 PC) → `--basetemp .pytest-tmp`

## 10. 개발 규칙 (Cline/AI 어시스턴트 공통)

- 수정 후 `python -m pytest -q` 57+ 전부 통과 확인. 탐지 룰을 고치면
  §5 사례집의 회귀 테스트가 지켜준다.
- **테스트·데모에 실존 개인정보 금지.** 반드시 `synth.generators` 로 생성한 합성값만.
- 라벨 출력에 원본값을 넣는 코드 금지 (테스트가 막고 있음).
- 탐지 룰 추가 시: 재현율 우선, 오탐은 confidence 낮춰서 허용. 실측 오독
  케이스는 테스트로 남길 것.
- 외부로 나가는 API 호출 추가 금지 (폐쇄망). LLM/VLM 은 환경변수 기반
  OpenAI 호환 클라이언트(`LLMClient`)만 사용.
