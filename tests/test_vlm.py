"""VlmReader 테스트 — 목 서버로 비전 요청 형식과 교정 적용을 검증."""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from grape_pii.detect.llm import LLMClient
from grape_pii.ocr.vlm import VlmReader


class _MockVlmHandler(BaseHTTPRequestHandler):
    captured = {}
    reply_content = '{"tokens": []}'

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _MockVlmHandler.captured = body
        payload = {"choices": [{"message": {"content": _MockVlmHandler.reply_content}}]}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class _StubBaseEngine:
    def __init__(self, tokens):
        self.tokens = tokens

    def read(self, image):
        return [dict(t) for t in self.tokens]

    def mean_confidence(self, image):
        return 0.5


@pytest.fixture
def mock_vlm():
    server = HTTPServer(("127.0.0.1", 0), _MockVlmHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def _image():
    return np.full((20, 40, 3), 255, dtype=np.uint8)


def _base_tokens():
    return [
        {"text": "검본인(시)", "bbox": [0, 0, 10, 5], "conf": 0.7},
        {"text": "650101-1*", "bbox": [12, 0, 30, 5], "conf": 0.8},
    ]


def test_vlm_corrects_tokens_and_sends_image(mock_vlm):
    _MockVlmHandler.reply_content = json.dumps({
        "tokens": [
            {"id": 0, "text": "김본인(金本人)"},
            {"id": 99, "text": "범위밖"},          # 무시돼야 함
            {"id": 1, "text": ""},                 # 빈 교정 무시
        ]
    })
    reader = VlmReader(_StubBaseEngine(_base_tokens()),
                       LLMClient(base_url=mock_vlm, model="gemma-test"))
    tokens = reader.read(_image())

    assert tokens[0]["text"] == "김본인(金本人)"
    assert tokens[0]["vlm_corrected"] is True
    assert tokens[1]["text"] == "650101-1*"  # 교정 없음 → 원본 유지
    assert tokens[1]["bbox"] == [12, 0, 30, 5]  # bbox 는 절대 불변

    body = _MockVlmHandler.captured
    assert body["model"] == "gemma-test"
    content = body["messages"][1]["content"]
    kinds = {part["type"] for part in content}
    assert kinds == {"text", "image_url"}
    image_url = next(p for p in content if p["type"] == "image_url")["image_url"]["url"]
    assert image_url.startswith("data:image/png;base64,")
    base64.b64decode(image_url.split(",", 1)[1])  # 유효한 base64 인지


def test_vlm_passthrough_when_unavailable():
    reader = VlmReader(_StubBaseEngine(_base_tokens()),
                       LLMClient(base_url="", model="x"))
    tokens = reader.read(_image())
    assert tokens[0]["text"] == "검본인(시)"  # 교정 없이 원본 그대로
