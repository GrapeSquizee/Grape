"""OS별 한글 폰트 자동 탐색.

--font 미지정 시 아래 후보를 순서대로 찾는다. 폐쇄망 서버에는 나눔고딕을
반입해 첫 번째 경로에 두는 것을 권장.
"""
from pathlib import Path

_CANDIDATES = (
    # Linux
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    # Windows
    "C:/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/gulim.ttc",
    "C:/Windows/Fonts/batang.ttc",
    # macOS
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
)


def find_korean_font() -> str:
    for candidate in _CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        "한글 폰트를 찾지 못했습니다. --font 로 경로를 지정하세요. "
        "예) Windows: C:\\Windows\\Fonts\\malgun.ttf, "
        "Linux: apt install fonts-nanum 후 기본 경로 사용"
    )


def resolve_font(font_path: str | None) -> str:
    """지정 경로가 있으면 존재 검증, 없으면(None) 자동 탐색."""
    if font_path is None:
        return find_korean_font()
    if not Path(font_path).exists():
        raise FileNotFoundError(
            f"폰트 파일이 없습니다: {font_path} — --font 경로를 확인하세요."
        )
    return font_path
