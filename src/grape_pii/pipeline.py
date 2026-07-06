"""파이프라인 실행기.

두 가지 모드:
- text 모드: OCR 결과 JSON([{"text": ..., "bbox": [...]}, ...])을 입력으로
  탐지→합성값 생성까지 수행. OCR/렌더링 없이 탐지 로직을 검증하는 PoC 용.
- image 모드: 전처리(deskew)→OCR→탐지→치환 렌더링→라벨까지 전체 수행.
  PaddleOCR/OpenCV/Pillow 필요 (반입 목록 참조).

출력 라벨에는 원본 텍스트를 포함하지 않는다 — 원본값↔치환값 매핑은 그 자체가
개인정보이므로 기본 정책은 미저장 (계획서 6장).
"""
import json
import random
from pathlib import Path

from .detect.llm import LLMClient, detect_with_llm
from .detect.models import Detection
from .detect.rules import detect_all
from .synth.generators import make_replacement


def _join_tokens(tokens: list[dict]) -> tuple[str, list[tuple[int, int]]]:
    """토큰을 공백으로 이어붙이고 각 토큰의 (start, end) 문자 오프셋을 기록."""
    parts, spans, pos = [], [], 0
    for t in tokens:
        text = t["text"]
        spans.append((pos, pos + len(text)))
        parts.append(text)
        pos += len(text) + 1
    return " ".join(parts), spans


def _span_to_token_ids(det: Detection, spans: list[tuple[int, int]]) -> list[int]:
    return [i for i, (s, e) in enumerate(spans) if det.start < e and s < det.end]


def run_text(tokens: list[dict], llm: LLMClient | None = None,
             seed: int | None = None) -> dict:
    """토큰 목록에서 PII 탐지 + 합성 치환값 생성.

    반환: {"entities": [{type, token_ids, confidence, source, replacement}, ...]}
    """
    rng = random.Random(seed)
    joined, spans = _join_tokens(tokens)

    detections = detect_all(joined)
    for d in detections:
        d.token_ids = _span_to_token_ids(d, spans)

    if llm is not None and llm.available:
        taken = {i for d in detections for i in d.token_ids}
        for d in detect_with_llm(tokens, llm):
            if not taken.intersection(d.token_ids):  # 룰 탐지가 우선
                detections.append(d)
                taken.update(d.token_ids)

    entities = []
    for d in detections:
        entities.append({
            "type": d.type,
            "token_ids": d.token_ids,
            "confidence": d.confidence,
            "source": d.source,
            "replacement": make_replacement(d.type, d.text, rng),
        })
    return {"entities": entities}


def run_file(ocr_json_path: str | Path, output_path: str | Path,
             llm: LLMClient | None = None, seed: int | None = None) -> dict:
    """OCR 결과 JSON 파일 → 라벨 JSON 파일. 라벨에 bbox 를 포함한다."""
    with open(ocr_json_path, encoding="utf-8") as f:
        tokens = json.load(f)["tokens"]

    result = run_text(tokens, llm=llm, seed=seed)
    for ent in result["entities"]:
        ent["bboxes"] = [tokens[i].get("bbox") for i in ent["token_ids"]]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


def _entity_bbox(ent: dict, tokens: list[dict]) -> list[float] | None:
    """엔티티에 속한 토큰 bbox 들의 합집합 사각형."""
    boxes = [tokens[i]["bbox"] for i in ent["token_ids"] if tokens[i].get("bbox")]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def run_image(image_path: str | Path, output_image: str | Path,
              output_labels: str | Path, font_path: str | None = None,
              llm: LLMClient | None = None, seed: int | None = None,
              ocr=None, ocr_engine: str = "paddle",
              dump_tokens: str | Path | None = None) -> dict:
    """이미지 → 전처리 → OCR → 탐지 → 치환 렌더링 → 라벨.

    ocr: 엔진 인스턴스 (재사용을 위해 주입 가능, 없으면 ocr_engine 이름으로 생성).
    font_path: None 이면 OS 별 한글 폰트를 자동 탐색.
    """
    import cv2
    from PIL import Image

    from .ocr.engine import create_engine
    from .preprocess.geometry import deskew
    from .render.fonts import resolve_font
    from .render.redact import replace_text_region

    font_path = resolve_font(font_path)

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    image, skew_angle = deskew(image)

    if ocr is None:
        ocr = create_engine(ocr_engine)
    tokens = ocr.read(image)

    if dump_tokens is not None:
        # OCR 진단용 — 원본 텍스트가 그대로 담기므로 실문서에서는 확인 후 폐기할 것
        with open(dump_tokens, "w", encoding="utf-8") as f:
            json.dump({"tokens": tokens}, f, ensure_ascii=False, indent=2)

    result = run_text(tokens, llm=llm, seed=seed)

    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    for ent in result["entities"]:
        bbox = _entity_bbox(ent, tokens)
        ent["bbox"] = bbox
        if bbox is not None:
            pil_image = replace_text_region(pil_image, bbox, ent["replacement"], font_path)
    pil_image.save(output_image)

    result["meta"] = {"skew_angle": skew_angle, "n_tokens": len(tokens),
                      "source_image": str(Path(image_path).name)}
    with open(output_labels, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="PII 탐지·치환 파이프라인")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_text = sub.add_parser("text", help="OCR JSON → 라벨 JSON")
    p_text.add_argument("ocr_json", help="OCR 결과 JSON ({\"tokens\": [{\"text\", \"bbox\"}]})")
    p_text.add_argument("output", help="라벨 출력 JSON 경로")

    p_img = sub.add_parser("image", help="이미지 → 치환 이미지 + 라벨 JSON")
    p_img.add_argument("image", help="입력 문서 이미지")
    p_img.add_argument("output_image", help="치환 완료 이미지 경로")
    p_img.add_argument("output_labels", help="라벨 출력 JSON 경로")
    p_img.add_argument("--font", default=None,
                       help="한글 폰트 경로 (미지정 시 OS 별 자동 탐색)")
    p_img.add_argument("--ocr-engine", choices=("paddle", "tesseract"), default="paddle")
    p_img.add_argument("--dump-tokens", default=None, metavar="PATH",
                       help="OCR 토큰을 JSON 으로 저장 (탐지 안 될 때 OCR 품질 진단용)")

    for p in (p_text, p_img):
        p.add_argument("--use-llm", action="store_true",
                       help="GRAPE_LLM_BASE_URL 로 LLM 탐지 활성화")
        p.add_argument("--seed", type=int, default=None)

    args = parser.parse_args()
    llm = LLMClient() if args.use_llm else None

    if args.mode == "text":
        result = run_file(args.ocr_json, args.output, llm=llm, seed=args.seed)
        print(f"entities: {len(result['entities'])} → {args.output}")
    else:
        result = run_image(args.image, args.output_image, args.output_labels,
                           font_path=args.font, llm=llm, seed=args.seed,
                           ocr_engine=args.ocr_engine, dump_tokens=args.dump_tokens)
        print(f"entities: {len(result['entities'])} → {args.output_image}, {args.output_labels}")


if __name__ == "__main__":
    main()
