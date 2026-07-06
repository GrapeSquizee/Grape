"""렌더링·OCR 검증용 가짜 문서 이미지 생성 (모든 값은 합성값).

사용: python scripts/make_sample_doc.py out.png [--font 경로] [--seed N]
"""
import argparse
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from grape_pii.render.fonts import resolve_font
from grape_pii.synth.generators import (
    make_address, make_card_digits, make_name, make_rrn_digits,
)


def build(font_path: str, seed: int) -> Image.Image:
    rng = random.Random(seed)
    rrn = make_rrn_digits(rng)
    card = make_card_digits(16, rng)
    name = make_name(rng)
    address = make_address(rng).replace("\n", " ")

    img = Image.new("RGB", (900, 620), "white")
    draw = ImageDraw.Draw(img)
    title_font = ImageFont.truetype(font_path, 34)
    body_font = ImageFont.truetype(font_path, 24)

    draw.text((280, 40), "개인정보 수집·이용 동의서", font=title_font, fill="black")
    draw.line((60, 100, 840, 100), fill="black", width=2)

    rows = [
        ("성명", name),
        ("주민등록번호", f"{rrn[:6]}-{rrn[6:]}"),
        ("주소", address),
        ("휴대전화", f"010-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}"),
        ("카드번호", "-".join(card[i:i + 4] for i in range(0, 16, 4))),
        ("환불계좌", f"국민은행 {rng.randint(100000, 999999)}-{rng.randint(10, 99)}-{rng.randint(100000, 999999)}"),
    ]
    y = 140
    for label, value in rows:
        draw.text((80, y), label, font=body_font, fill="black")
        draw.text((260, y), str(value), font=body_font, fill="black")
        y += 58

    draw.text((80, y + 20), "위와 같이 개인정보 수집·이용에 동의합니다.", font=body_font, fill="black")
    draw.text((560, y + 70), f"신청인: {name} (서명)", font=body_font, fill="black")
    return img


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--font", default=None, help="한글 폰트 경로 (미지정 시 자동 탐색)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    build(resolve_font(args.font), args.seed).save(args.output)
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
