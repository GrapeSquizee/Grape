#!/usr/bin/env python3
"""
Daily AI News Digest
매일 아침 8시 aitimes.com 에서 TOP 10 기사를 수집하고 알림을 표시합니다.
"""

import subprocess
import sys
import json
import os
import re
from datetime import datetime
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("필요한 패키지를 설치합니다...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4"])
    import requests
    from bs4 import BeautifulSoup


BASE_URL = "https://www.aitimes.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
DIGEST_FILE = Path(__file__).parent / "digest_history.json"


def fetch_articles() -> list[dict]:
    """aitimes.com 메인 페이지에서 기사 목록을 가져옵니다."""
    try:
        resp = requests.get(BASE_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
    except requests.RequestException as e:
        print(f"[오류] 페이지 접속 실패: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []
    seen_urls = set()

    # 다양한 기사 선택자 시도
    selectors = [
        "article h2 a",
        "article h3 a",
        ".article-list li a",
        ".news-list li a",
        "h2.title a",
        "h3.title a",
        ".item-title a",
        ".headline a",
        "a.article-title",
        # 범용 fallback
        "a[href*='/news/']",
        "a[href*='/article/']",
        "a[href*='/view/']",
    ]

    for selector in selectors:
        for tag in soup.select(selector):
            href = tag.get("href", "")
            title = tag.get_text(strip=True)

            if not title or len(title) < 10:
                continue

            # 절대 URL 변환
            if href.startswith("http"):
                url = href
            elif href.startswith("/"):
                url = BASE_URL + href
            else:
                continue

            if url in seen_urls:
                continue
            seen_urls.add(url)

            # 광고/메뉴 링크 제외
            skip_keywords = ["login", "join", "subscribe", "privacy", "terms", "contact", "about"]
            if any(kw in url.lower() for kw in skip_keywords):
                continue

            articles.append({"title": title, "url": url})

        if len(articles) >= 30:
            break

    return articles[:30]


def score_article(article: dict) -> float:
    """기사의 흥미도 점수를 계산합니다."""
    title = article["title"].lower()

    # 흥미도 높은 키워드
    high_interest = [
        "gpt", "llm", "ai", "인공지능", "chatgpt", "openai", "google", "meta", "microsoft",
        "anthropic", "claude", "gemini", "deepmind", "nvidia", "삼성", "로봇", "자율주행",
        "생성", "혁신", "돌파", "최초", "세계", "획기적", "규제", "법", "윤리",
        "투자", "스타트업", "기술", "연구", "발표", "출시", "업데이트"
    ]

    score = 0.0
    for kw in high_interest:
        if kw in title:
            score += 1.0

    # 제목 길이 점수 (너무 짧거나 긴 제목 감점)
    length = len(article["title"])
    if 20 <= length <= 60:
        score += 0.5

    return score


def select_top10(articles: list[dict]) -> list[dict]:
    """흥미도 기준 TOP 10 기사를 선택합니다."""
    scored = [(score_article(a), a) for a in articles]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored[:10]]


def send_desktop_notification(title: str, body: str):
    """데스크톱 알림을 전송합니다 (Linux notify-send)."""
    try:
        subprocess.run(
            ["notify-send", "--app-name=AI뉴스 다이제스트", "--icon=dialog-information",
             "--expire-time=10000", title, body],
            check=False, capture_output=True
        )
    except FileNotFoundError:
        pass  # notify-send 없는 환경 무시


def save_digest(articles: list[dict], date_str: str):
    """오늘의 다이제스트를 JSON 파일에 저장합니다."""
    history = {}
    if DIGEST_FILE.exists():
        try:
            history = json.loads(DIGEST_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = {}

    history[date_str] = articles
    # 최근 30일치만 보관
    if len(history) > 30:
        oldest = sorted(history.keys())[0]
        del history[oldest]

    DIGEST_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def print_digest(articles: list[dict], date_str: str):
    """터미널에 다이제스트를 출력합니다."""
    separator = "=" * 65
    print(f"\n{separator}")
    print(f"  📰 AI Times 오늘의 TOP 10 뉴스  [{date_str}]")
    print(separator)

    if not articles:
        print("  기사를 가져오지 못했습니다. 네트워크를 확인하세요.")
        print(separator)
        return

    for i, article in enumerate(articles, 1):
        title = article["title"]
        url = article["url"]
        # 긴 제목 줄바꿈
        if len(title) > 55:
            title = title[:52] + "..."
        print(f"\n  {i:2d}. {title}")
        print(f"      {url}")

    print(f"\n{separator}\n")


def main():
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] aitimes.com 기사 수집 중...")

    articles_raw = fetch_articles()

    if not articles_raw:
        send_desktop_notification(
            "AI뉴스 다이제스트 오류",
            "aitimes.com 에서 기사를 가져오지 못했습니다."
        )
        print("[오류] 기사를 가져오지 못했습니다.")
        sys.exit(1)

    top10 = select_top10(articles_raw)
    print_digest(top10, date_str)
    save_digest(top10, date_str)

    # 요약 알림 (첫 3개 제목)
    preview = "\n".join(f"• {a['title'][:45]}" for a in top10[:3])
    send_desktop_notification(
        f"📰 AI Times TOP 10 [{date_str}]",
        preview + f"\n\n총 {len(top10)}개 기사 수집 완료"
    )

    print(f"[완료] {len(top10)}개 기사 저장 → {DIGEST_FILE}")


if __name__ == "__main__":
    main()
