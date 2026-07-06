"""가족관계증명서 형태의 테스트용 가짜 문서 이미지 생성.

모든 값(이름, 주민번호, 주소)은 합성값이며, 하단에 테스트용 문서임을 명시한다.

사용: python scripts/make_family_cert.py out.png [--font 경로] [--seed N]
"""
import argparse
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from grape_pii.synth.generators import make_address, make_name, make_rrn_digits

DEFAULT_FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
BON_LIST = ["김해(金海)", "밀양(密陽)", "전주(全州)", "경주(慶州)", "파평(坡平)", "안동(安東)"]
_CENTURY = {"1": 1900, "2": 1900, "3": 2000, "4": 2000}


def _birth_from_rrn(rrn: str) -> str:
    year = _CENTURY[rrn[6]] + int(rrn[:2])
    return f"{year}년 {int(rrn[2:4]):02d}월 {int(rrn[4:6]):02d}일"


def _person(rng: random.Random, year_range: tuple[int, int], sex: str) -> dict:
    rrn = make_rrn_digits(rng, year_range=year_range, sex=sex)
    return {
        "name": make_name(rng),
        "rrn": f"{rrn[:6]}-{rrn[6:]}",
        "birth": _birth_from_rrn(rrn),
        "sex": "남" if sex == "M" else "여",
        "bon": rng.choice(BON_LIST),
    }


def build(font_path: str, seed: int) -> Image.Image:
    rng = random.Random(seed)
    self_sex = rng.choice(["M", "F"])
    spouse_sex = "F" if self_sex == "M" else "M"
    rows = [
        ("본인", _person(rng, (1975, 1990), self_sex)),
        ("부", _person(rng, (1950, 1962), "M")),
        ("모", _person(rng, (1952, 1965), "F")),
        ("배우자", _person(rng, (1975, 1992), spouse_sex)),
        ("자녀", _person(rng, (2005, 2018), rng.choice(["M", "F"]))),
        ("자녀", _person(rng, (2005, 2018), rng.choice(["M", "F"]))),
    ]
    reg_base = make_address(rng).replace("\n", " ")

    W, H = 1000, 1180
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(font_path, 38)
    f_body = ImageFont.truetype(font_path, 20)
    f_small = ImageFont.truetype(font_path, 16)

    title = "가 족 관 계 증 명 서 (일반)"
    tw = draw.textlength(title, font=f_title)
    draw.text(((W - tw) / 2, 50), title, font=f_title, fill="black")

    # 등록기준지
    y0 = 140
    draw.rectangle((60, y0, W - 60, y0 + 46), outline="black", width=2)
    draw.line((200, y0, 200, y0 + 46), fill="black", width=2)
    draw.text((80, y0 + 12), "등록기준지", font=f_body, fill="black")
    draw.text((216, y0 + 12), reg_base, font=f_body, fill="black")

    # 가족사항 표
    cols = [("구분", 90), ("성명", 150), ("출생연월일", 210), ("주민등록번호", 220), ("성별", 70), ("본", 140)]
    x_start, y = 60, y0 + 80
    row_h = 52
    x_edges = [x_start]
    for _, w in cols:
        x_edges.append(x_edges[-1] + w)
    table_w = x_edges[-1] - x_start

    draw.rectangle((x_start, y, x_start + table_w, y + row_h), fill=(238, 238, 238))
    for i, (label, _) in enumerate(cols):
        cw = draw.textlength(label, font=f_body)
        draw.text((x_edges[i] + (x_edges[i + 1] - x_edges[i] - cw) / 2, y + 14),
                  label, font=f_body, fill="black")

    for r, (rel, p) in enumerate(rows, start=1):
        ry = y + r * row_h
        values = (rel, p["name"], p["birth"], p["rrn"], p["sex"], p["bon"])
        for i, val in enumerate(values):
            cw = draw.textlength(val, font=f_body)
            draw.text((x_edges[i] + (x_edges[i + 1] - x_edges[i] - cw) / 2, ry + 14),
                      val, font=f_body, fill="black")

    n_rows = len(rows) + 1
    for r in range(n_rows + 1):
        draw.line((x_start, y + r * row_h, x_start + table_w, y + r * row_h), fill="black", width=2)
    for xe in x_edges:
        draw.line((xe, y, xe, y + n_rows * row_h), fill="black", width=2)

    # 하단 문구
    fy = y + n_rows * row_h + 50
    draw.text((60, fy), "위 가족관계증명서(일반)는 가족관계등록부의 기록사항과 틀림없음을 증명합니다.",
              font=f_body, fill="black")
    issue_date = f"{rng.randint(2023, 2026)}년 {rng.randint(1, 12):02d}월 {rng.randint(1, 28):02d}일"
    dw = draw.textlength(issue_date, font=f_body)
    draw.text(((W - dw) / 2, fy + 60), issue_date, font=f_body, fill="black")
    org = "법원행정처 전산정보중앙관리소 전산운영책임관"
    ow = draw.textlength(org, font=f_body)
    draw.text(((W - ow) / 2, fy + 100), org, font=f_body, fill="black")

    draw.text((60, H - 60), f"발급번호: {rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}-"
              f"{rng.randint(1000, 9999)}-{rng.randint(10000, 99999)}",
              font=f_small, fill="black")
    notice = "※ 본 문서는 파이프라인 테스트용 가상 문서이며 모든 정보는 무작위 합성값임"
    nw = draw.textlength(notice, font=f_small)
    draw.text((W - 60 - nw, H - 60), notice, font=f_small, fill=(150, 150, 150))
    return img


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--font", default=DEFAULT_FONT)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    build(args.font, args.seed).save(args.output)
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
