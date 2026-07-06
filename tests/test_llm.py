"""LLM 탐지 모듈 테스트 — 로컬 목 서버로 OpenAI 호환 요청/파싱을 검증.

실제 엔드포인트 없이 LLMClient 의 요청 형식과 detect_with_llm 의 응답 파싱을
확인한다. 라이브 테스트는 scripts/demo_llm_detect.py 로 수행.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from grape_pii.detect.llm import LLMClient, _extract_json, detect_with_llm


class _MockHandler(BaseHTTPRequestHandler):
    captured = {}
    reply_content = '{"entities": []}'

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _MockHandler.captured = {"path": self.path, "body": body,
                                 "auth": self.headers.get("Authorization")}
        payload = {"choices": [{"message": {"content": _MockHandler.reply_content}}]}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def mock_server():
    server = HTTPServer(("127.0.0.1", 0), _MockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def test_client_sends_openai_compatible_request(mock_server):
    client = LLMClient(base_url=mock_server, api_key="test-key", model="test-model")
    reply = client.chat("system prompt", "user prompt")

    assert reply == '{"entities": []}'
    cap = _MockHandler.captured
    assert cap["path"] == "/v1/chat/completions"
    assert cap["auth"] == "Bearer test-key"
    assert cap["body"]["model"] == "test-model"
    assert cap["body"]["messages"][0] == {"role": "system", "content": "system prompt"}


def test_detect_with_llm_parses_entities(mock_server):
    _MockHandler.reply_content = json.dumps({
        "entities": [
            {"token_ids": [1], "type": "NAME", "confidence": 0.95},
            {"token_ids": [3, 4], "type": "ADDRESS", "confidence": 0.9},
            {"token_ids": [99], "type": "NAME", "confidence": 0.5},   # 범위 밖 → 무시
            {"token_ids": [0], "type": "RRN", "confidence": 0.5},     # 룰 담당 → 무시
        ]
    })
    tokens = [{"text": "성명"}, {"text": "홍길동"}, {"text": "주소"},
              {"text": "서울시"}, {"text": "중구"}]
    client = LLMClient(base_url=mock_server, model="test-model")

    found = detect_with_llm(tokens, client)
    assert [(d.type, d.token_ids) for d in found] == [("NAME", [1]), ("ADDRESS", [3, 4])]
    assert all(d.source == "llm" for d in found)


def test_extract_json_tolerates_code_fences():
    raw = '설명입니다.\n```json\n{"entities": [{"token_ids": [0], "type": "NAME"}]}\n```'
    assert _extract_json(raw)["entities"][0]["type"] == "NAME"


def test_client_unavailable_without_base_url(monkeypatch):
    monkeypatch.delenv("GRAPE_LLM_BASE_URL", raising=False)
    assert not LLMClient().available
