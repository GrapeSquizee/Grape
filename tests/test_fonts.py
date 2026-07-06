import pytest

from grape_pii.render import fonts


def test_resolve_font_explicit_missing():
    with pytest.raises(FileNotFoundError, match="폰트 파일이 없습니다"):
        fonts.resolve_font("/no/such/font.ttf")


def test_find_korean_font_none_available(monkeypatch):
    monkeypatch.setattr(fonts, "_CANDIDATES", ("/no/such/a.ttf", "/no/such/b.ttf"))
    with pytest.raises(FileNotFoundError, match="--font"):
        fonts.find_korean_font()


def test_find_korean_font_picks_first_existing(monkeypatch, tmp_path):
    fake = tmp_path / "font.ttf"
    fake.write_bytes(b"stub")
    monkeypatch.setattr(fonts, "_CANDIDATES", ("/no/such/a.ttf", str(fake)))
    assert fonts.find_korean_font() == str(fake)
    assert fonts.resolve_font(None) == str(fake)
