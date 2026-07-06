"""LLM(GPT-5.4 내부 API) 기반 문맥 엔티티 탐지 — 이름, 주소 등.

내부 엔드포인트가 OpenAI 호환(chat/completions)이라고 가정한 기본 구현.
내부망 API 스펙이 다르면 LLMClient.chat() 만 교체하면 된다.

환경변수:
  GRAPE_LLM_BASE_URL  예: http://llm.internal:8000/v1
  GRAPE_LLM_API_KEY   (불필요하면 미설정)
  GRAPE_LLM_MODEL     기본값 gpt-5.4
"""
import json
import os
import re
import urllib.request
from pathlib import Path

from .models import Detection

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "configs" / "prompts" / "detect_entities.txt"


class LLMClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: int = 120):
        self.base_url = (base_url or os.environ.get("GRAPE_LLM_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("GRAPE_LLM_API_KEY", "")
        self.model = model or os.environ.get("GRAPE_LLM_MODEL", "gpt-5.4")
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.base_url)

    def chat(self, system: str, user: str, image_png_b64: str | None = None) -> str:
        """OpenAI 호환 chat. image_png_b64 를 주면 비전 입력(VLM)으로 전송."""
        if image_png_b64 is not None:
            user_content = [
                {"type": "text", "text": user},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{image_png_b64}"}},
            ]
        else:
            user_content = user
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]


def _load_prompt() -> str:
    with open(_PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def _extract_json(text: str) -> dict:
    """응답에서 첫 JSON 객체를 관대하게 추출 (코드펜스 등 허용)."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON object in LLM response: {text[:200]!r}")
    return json.loads(m.group(0))


def detect_with_llm(tokens: list[dict], client: LLMClient) -> list[Detection]:
    """OCR 토큰 목록에서 문맥 의존 엔티티(NAME/ADDRESS)를 LLM 으로 탐지.

    tokens: [{"text": str, ...}, ...] — 인덱스가 곧 token_id.
    반환되는 Detection 의 start/end 는 파이프라인에서 채우므로 -1.
    """
    numbered = "\n".join(f"{i}\t{t['text']}" for i, t in enumerate(tokens))
    raw = client.chat(_load_prompt(), numbered)
    parsed = _extract_json(raw)

    out = []
    for ent in parsed.get("entities", []):
        ids = [i for i in ent.get("token_ids", []) if isinstance(i, int) and 0 <= i < len(tokens)]
        if not ids or ent.get("type") not in ("NAME", "ADDRESS"):
            continue
        text = " ".join(tokens[i]["text"] for i in sorted(ids))
        conf = float(ent.get("confidence", 0.8))
        out.append(Detection(ent["type"], text, -1, -1, conf, source="llm", token_ids=sorted(ids)))
    return out
