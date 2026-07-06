"""LLM 엔티티 탐지(NAME/ADDRESS) 라이브 데모.

외부 테스트 (NVIDIA NIM, OpenAI 호환 — build.nvidia.com 에서 무료 키 발급):
  export GRAPE_LLM_BASE_URL=https://integrate.api.nvidia.com/v1
  export GRAPE_LLM_API_KEY=nvapi-...
  export GRAPE_LLM_MODEL=meta/llama-3.3-70b-instruct
  python scripts/demo_llm_detect.py

내부망 (GPT-5.4, OpenAI 호환):
  export GRAPE_LLM_BASE_URL=http://<내부엔드포인트>/v1
  export GRAPE_LLM_MODEL=gpt-5.4

주의: 프롬프트에 토큰 텍스트가 그대로 전달된다. 외부 API 로는 반드시
가짜 데이터만 보낼 것 (이 데모의 값은 전부 합성값이다).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from grape_pii.detect.llm import LLMClient, detect_with_llm
from grape_pii.pipeline import run_text

# 전부 가짜 값 (데모용)
TOKENS = [
    {"text": "보험금"}, {"text": "청구서"},
    {"text": "청구인"}, {"text": "성명:"}, {"text": "박서준"},
    {"text": "피보험자와의"}, {"text": "관계:"}, {"text": "본인"},
    {"text": "주소:"}, {"text": "경기도"}, {"text": "수원시"}, {"text": "팔달구"},
    {"text": "정조로"}, {"text": "825,"}, {"text": "304동"}, {"text": "1102호"},
    {"text": "연락처:"}, {"text": "010-4821-9375"},
    {"text": "지급계좌:"}, {"text": "신한은행"}, {"text": "110-482-193757"},
    {"text": "담당"}, {"text": "설계사:"}, {"text": "이하은"},
]


def main() -> None:
    client = LLMClient()
    if not client.available:
        sys.exit("GRAPE_LLM_BASE_URL 이 설정되지 않았습니다. 스크립트 상단 사용법 참조.")

    print(f"endpoint: {client.base_url}  model: {client.model}\n")

    print("=== LLM 단독 탐지 (NAME/ADDRESS) ===")
    for d in detect_with_llm(TOKENS, client):
        text = " ".join(TOKENS[i]["text"] for i in d.token_ids)
        print(f"  {d.type:8s} conf={d.confidence:.2f} tokens={d.token_ids} | {text}")

    print("\n=== 파이프라인 통합 (룰 + LLM) ===")
    for e in run_text(TOKENS, llm=client, seed=42)["entities"]:
        original = " ".join(TOKENS[i]["text"] for i in e["token_ids"])
        print(f"  {e['type']:8s} conf={e['confidence']:.2f} src={e['source']:4s} "
              f"| {original} → {e['replacement']}")


if __name__ == "__main__":
    main()
