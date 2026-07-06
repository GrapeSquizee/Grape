"""OCR 래퍼 — PaddleOCR(주력) / Tesseract(대체).

- PaddleOCR: 한국어 인식률이 높은 주력 엔진. paddleocr 3.x(predict API)와
  2.x(ocr API)를 모두 지원한다 — 폐쇄망 Nexus 에 어느 버전이 올라가 있어도
  동작하도록 생성 시점에 API 를 판별한다. 3.x 는 문서 방향 분류
  (use_doc_orientation_classify)를 내장하고 있어 계획서 ① 전처리의
  90° 단위 방향 보정을 여기서 켤 수 있다.
- Tesseract: 모델 파일 반입 없이 OS 패키지(tesseract-ocr-kor)만으로 도는
  대체 엔진. 인식률은 낮지만 PaddleOCR 모델을 받을 수 없는 환경에서
  파이프라인 E2E 검증용으로 쓴다. 단어 단위 bbox 를 직접 제공한다.

두 엔진 모두 동일한 인터페이스: read(image) -> [{"text", "bbox", "conf"}]
"""


def create_engine(name: str = "paddle", **kwargs):
    if name == "paddle":
        return OcrEngine(**kwargs)
    if name == "tesseract":
        return TesseractEngine(**kwargs)
    raise ValueError(f"unknown OCR engine: {name}")


class TesseractEngine:
    def __init__(self, lang: str = "kor+eng", min_conf: float = 0.0):
        import pytesseract
        self._pt = pytesseract
        self.lang = lang
        self.min_conf = min_conf

    def read(self, image) -> list[dict]:
        data = self._pt.image_to_data(
            image, lang=self.lang, output_type=self._pt.Output.DICT
        )
        tokens = []
        for text, conf, x, y, w, h in zip(
            data["text"], data["conf"], data["left"], data["top"],
            data["width"], data["height"],
        ):
            text = text.strip()
            conf = float(conf) / 100.0
            if not text or conf < self.min_conf:
                continue
            tokens.append({"text": text, "bbox": [x, y, x + w, y + h], "conf": conf})
        return tokens

    def mean_confidence(self, image) -> float:
        tokens = self.read(image)
        if not tokens:
            return 0.0
        return sum(t["conf"] for t in tokens) / len(tokens)


class OcrEngine:
    def __init__(self, lang: str = "korean", enable_doc_orientation: bool = False):
        from paddleocr import PaddleOCR
        try:  # paddleocr >= 3.x
            self._ocr = PaddleOCR(
                lang=lang,
                use_doc_orientation_classify=enable_doc_orientation,
                use_doc_unwarping=False,
                use_textline_orientation=True,
            )
            self._api = "v3"
        except TypeError:  # paddleocr 2.x
            self._ocr = PaddleOCR(lang=lang, use_angle_cls=True, show_log=False)
            self._api = "v2"

    def read(self, image) -> list[dict]:
        """이미지 → 토큰 목록 [{"text", "bbox": [x1,y1,x2,y2], "conf"}].

        OCR 는 라인 단위로 반환하므로 축정렬 bbox 로 변환 후, 단어 단위가
        필요하면 라인 bbox 를 공백 기준 비례 분할한다 (PoC 근사).
        """
        lines = self._read_v3(image) if self._api == "v3" else self._read_v2(image)
        tokens = []
        for text, conf, (x1, y1, x2, y2) in lines:
            tokens.extend(self._split_words(text, conf, x1, y1, x2, y2))
        return tokens

    def _read_v3(self, image) -> list[tuple]:
        out = []
        for res in self._ocr.predict(image):
            data = res if isinstance(res, dict) else res.json["res"]
            texts = data["rec_texts"]
            scores = data["rec_scores"]
            polys = data.get("rec_polys")
            boxes = data.get("rec_boxes")
            for i, (text, conf) in enumerate(zip(texts, scores)):
                if polys is not None and len(polys) > i:
                    xs = [p[0] for p in polys[i]]
                    ys = [p[1] for p in polys[i]]
                    bbox = (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))
                else:
                    x1, y1, x2, y2 = boxes[i]
                    bbox = (float(x1), float(y1), float(x2), float(y2))
                out.append((text, float(conf), bbox))
        return out

    def _read_v2(self, image) -> list[tuple]:
        result = self._ocr.ocr(image, cls=True)
        out = []
        for line in result[0] or []:
            poly, (text, conf) = line
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            out.append((text, float(conf), (min(xs), min(ys), max(xs), max(ys))))
        return out

    @staticmethod
    def _split_words(text: str, conf: float, x1: float, y1: float, x2: float, y2: float) -> list[dict]:
        """라인 bbox 를 공백 기준으로 문자수 비례 분할해 단어 단위 bbox 를 근사."""
        words = text.split()
        if len(words) <= 1:
            return [{"text": text, "bbox": [x1, y1, x2, y2], "conf": conf}]
        total_chars = len(text)
        tokens, cursor = [], 0
        width = x2 - x1
        for w in words:
            start = text.index(w, cursor)
            end = start + len(w)
            cursor = end
            tokens.append({
                "text": w,
                "bbox": [x1 + width * start / total_chars, y1,
                         x1 + width * end / total_chars, y2],
                "conf": conf,
            })
        return tokens

    def mean_confidence(self, image) -> float:
        """방향 보정 휴리스틱용 평균 신뢰도 (preprocess.fix_orientation 에 전달)."""
        tokens = self.read(image)
        if not tokens:
            return 0.0
        return sum(t["conf"] for t in tokens) / len(tokens)
