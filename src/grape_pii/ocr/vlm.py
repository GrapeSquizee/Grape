"""VLM 텍스트 교정 — "OCR bbox + VLM 판독" 하이브리드.

OCR(PaddleOCR/Tesseract)은 위치(bbox)는 정확하지만 저해상도·워터마크·한자에서
텍스트를 자주 오독한다(중명서, 홍질동, 한자 소실 등). VLM 은 반대로 텍스트는
잘 읽지만 좌표를 못 준다. 그래서 bbox 는 OCR 에서, 텍스트는 VLM 교정으로 얻는다.

문서 이미지 1장 + OCR 토큰 목록을 VLM 에 한 번에 보내 교정된 텍스트를 받는
구조라 문서당 VLM 호출은 1회다.

개인정보가 프롬프트와 이미지로 전달되므로 반드시 로컬/내부망 VLM 을 쓸 것
(Ollama·LM Studio·vLLM 등 OpenAI 호환 서버 + Gemma 등 로컬 모델).

환경변수:
  GRAPE_VLM_BASE_URL  예: http://localhost:11434/v1 (Ollama)
  GRAPE_VLM_API_KEY   (로컬 서버는 보통 불필요)
  GRAPE_VLM_MODEL     예: gemma4-31b-4bit
"""
import base64
import os
from pathlib import Path

from ..detect.llm import LLMClient, _extract_json

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "configs" / "prompts" / "correct_tokens.txt"


def vlm_client_from_env() -> LLMClient:
    return LLMClient(
        base_url=os.environ.get("GRAPE_VLM_BASE_URL"),
        api_key=os.environ.get("GRAPE_VLM_API_KEY"),
        model=os.environ.get("GRAPE_VLM_MODEL"),
    )


class VlmReader:
    """기존 OCR 엔진을 감싸 read() 결과의 텍스트를 VLM 으로 교정한다."""

    def __init__(self, base_engine, client: LLMClient | None = None):
        self.base = base_engine
        self.client = client or vlm_client_from_env()

    def read(self, image) -> list[dict]:
        tokens = self.base.read(image)
        if not tokens or not self.client.available:
            return tokens
        return self._correct(image, tokens)

    def _correct(self, image, tokens: list[dict]) -> list[dict]:
        import cv2

        ok, buffer = cv2.imencode(".png", image)
        if not ok:
            return tokens
        image_b64 = base64.b64encode(buffer.tobytes()).decode("ascii")

        with open(_PROMPT_PATH, encoding="utf-8") as f:
            system = f.read()
        numbered = "\n".join(f"{i}\t{t['text']}" for i, t in enumerate(tokens))

        raw = self.client.chat(system, numbered, image_png_b64=image_b64)
        parsed = _extract_json(raw)

        for item in parsed.get("tokens", []):
            idx = item.get("id")
            text = item.get("text")
            if (isinstance(idx, int) and 0 <= idx < len(tokens)
                    and isinstance(text, str) and text.strip()):
                tokens[idx]["text"] = text.strip()
                tokens[idx]["vlm_corrected"] = True
        return tokens

    def mean_confidence(self, image) -> float:
        return self.base.mean_confidence(image)
