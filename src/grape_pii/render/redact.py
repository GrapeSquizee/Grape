"""치환 렌더링 — 원본 텍스트 영역을 지우고 합성값을 그린다.

방식(계획서 ⑤): 배경색은 bbox 주변 픽셀에서 추정, 폰트 크기는 bbox 높이에서
역산. 글자색은 bbox 내부에서 배경과 가장 먼 색으로 추정.
"""
from PIL import Image, ImageDraw, ImageFont


def _estimate_colors(image: Image.Image, bbox: tuple[int, int, int, int],
                     margin: int = 3) -> tuple[tuple, tuple]:
    """(배경색, 글자색) 추정. 배경은 bbox 바깥 테두리 중앙값, 글자는 내부 최빈 어두운 색."""
    x1, y1, x2, y2 = bbox
    w, h = image.size
    outer = image.crop((max(0, x1 - margin), max(0, y1 - margin),
                        min(w, x2 + margin), min(h, y2 + margin)))
    inner = image.crop(bbox)

    outer_px = list(outer.getdata())
    inner_px = set(inner.getdata())
    border_px = [p for p in outer_px if p not in inner_px] or outer_px

    def median_color(pixels):
        channels = list(zip(*pixels))
        return tuple(sorted(c)[len(c) // 2] for c in channels)

    bg = median_color(border_px)
    darkest = min(inner.getdata(), key=lambda p: sum(p[:3]))
    return bg, darkest


def _fit_font(font_path: str, text: str, box_w: int, box_h: int) -> ImageFont.FreeTypeFont:
    """bbox 높이에서 폰트 크기를 역산하고, 폭이 넘치면 줄인다."""
    size = max(8, int(box_h * 0.8))
    font = ImageFont.truetype(font_path, size)
    while size > 8 and font.getbbox(text)[2] > box_w:
        size -= 1
        font = ImageFont.truetype(font_path, size)
    return font


def replace_text_region(image: Image.Image, bbox: tuple[int, int, int, int],
                        new_text: str, font_path: str) -> Image.Image:
    """bbox 영역의 텍스트를 new_text 로 교체한 이미지를 반환 (원본 비파괴)."""
    out = image.copy().convert("RGB")
    draw = ImageDraw.Draw(out)
    x1, y1, x2, y2 = (int(v) for v in bbox)

    bg, fg = _estimate_colors(out, (x1, y1, x2, y2))
    draw.rectangle((x1, y1, x2, y2), fill=bg)

    font = _fit_font(font_path, new_text, x2 - x1, y2 - y1)
    text_h = font.getbbox(new_text)[3]
    draw.text((x1, y1 + ((y2 - y1) - text_h) // 2), new_text, fill=fg, font=font)
    return out
