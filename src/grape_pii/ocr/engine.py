"""OCR 래퍼 — PaddleOCR(한국어 모델).

폐쇄망 반입 전이므로 import 는 생성 시점에 수행. 반입 목록:
paddleocr + paddlepaddle wheel, 한국어 det/rec 모델, angle classifier 모델.
"""


class OcrEngine:
    def __init__(self, lang: str = "korean", use_angle_cls: bool = True):
        from paddleocr import PaddleOCR
        self._ocr = PaddleOCR(lang=lang, use_angle_cls=use_angle_cls, show_log=False)

    def read(self, image) -> list[dict]:
        """이미지 → 토큰 목록 [{"text", "bbox": [x1,y1,x2,y2], "conf"}].

        PaddleOCR 는 라인 단위 4점 폴리곤을 반환하므로 축정렬 bbox 로 변환한다.
        단어 단위 분할이 필요하면 라인 bbox 를 공백 기준 비례 분할한다 (PoC 근사).
        """
        result = self._ocr.ocr(image, cls=True)
        tokens = []
        for line in result[0] or []:
            poly, (text, conf) = line
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            tokens.extend(self._split_words(text, conf, min(xs), min(ys), max(xs), max(ys)))
        return tokens

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
