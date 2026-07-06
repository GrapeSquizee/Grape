"""OcrEngine 테스트 — paddleocr 스텁으로 API 판별과 oneDNN 폴백을 검증."""
import sys
import types

import pytest

from grape_pii.ocr.engine import OcrEngine, create_engine


class _StubPaddleOCR:
    """paddle 3.x 의 Windows oneDNN/PIR 버그를 흉내내는 스텁.

    enable_mkldnn 미지정(기본 켜짐) 상태의 predict 는 NotImplementedError,
    enable_mkldnn=False 로 만들면 정상 결과를 반환한다.
    """

    init_calls: list[dict] = []

    def __init__(self, **kwargs):
        _StubPaddleOCR.init_calls.append(kwargs)
        self.kwargs = kwargs

    def predict(self, image):
        if self.kwargs.get("enable_mkldnn") is not False:
            raise NotImplementedError(
                "(Unimplemented) ConvertPirAttribute2RuntimeAttribute not support"
            )
        return [{
            "rec_texts": ["주민등록번호", "900101-1234567"],
            "rec_scores": [0.99, 0.97],
            "rec_polys": [
                [[10, 10], [100, 10], [100, 30], [10, 30]],
                [[110, 10], [250, 10], [250, 30], [110, 30]],
            ],
        }]


@pytest.fixture
def stub_paddleocr(monkeypatch):
    _StubPaddleOCR.init_calls = []
    module = types.SimpleNamespace(PaddleOCR=_StubPaddleOCR)
    monkeypatch.setitem(sys.modules, "paddleocr", module)
    return _StubPaddleOCR


def test_mkldnn_fallback_on_notimplemented(stub_paddleocr):
    engine = OcrEngine()
    tokens = engine.read(image=None)

    # 1차 생성(기본) → predict 실패 → enable_mkldnn=False 로 재생성 후 성공
    assert len(stub_paddleocr.init_calls) == 2
    assert "enable_mkldnn" not in stub_paddleocr.init_calls[0]
    assert stub_paddleocr.init_calls[1]["enable_mkldnn"] is False

    assert [t["text"] for t in tokens] == ["주민등록번호", "900101-1234567"]
    assert tokens[1]["bbox"] == [110.0, 10.0, 250.0, 30.0]


def test_mkldnn_fallback_runs_once(stub_paddleocr):
    engine = OcrEngine(enable_mkldnn=False)
    engine.read(image=None)  # 정상 동작

    # 이미 꺼진 상태에서 또 NotImplementedError 가 나면 폴백 없이 전파돼야 함
    engine._ocr.kwargs["enable_mkldnn"] = True
    with pytest.raises(NotImplementedError):
        engine.read(image=None)


def test_create_engine_paddle(stub_paddleocr):
    engine = create_engine("paddle", enable_mkldnn=False)
    assert isinstance(engine, OcrEngine)


def test_create_engine_unknown():
    with pytest.raises(ValueError):
        create_engine("nope")
