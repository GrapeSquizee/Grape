"""파이프라인 실행기.

두 가지 모드:
- text 모드: OCR 결과 JSON([{"text": ..., "bbox": [...]}, ...])을 입력으로
  탐지→합성값 생성까지 수행. OCR/렌더링 없이 탐지 로직을 검증하는 PoC 용.
- image 모드(추후): 전처리→OCR→탐지→렌더링까지 전체 수행. PaddleOCR 반입 후 연결.

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


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="PII 탐지·치환 파이프라인 (text 모드)")
    parser.add_argument("ocr_json", help="OCR 결과 JSON ({\"tokens\": [{\"text\", \"bbox\"}]})")
    parser.add_argument("output", help="라벨 출력 JSON 경로")
    parser.add_argument("--use-llm", action="store_true",
                        help="GRAPE_LLM_BASE_URL 로 LLM 탐지 활성화")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    llm = LLMClient() if args.use_llm else None
    result = run_file(args.ocr_json, args.output, llm=llm, seed=args.seed)
    print(f"entities: {len(result['entities'])} → {args.output}")


if __name__ == "__main__":
    main()
