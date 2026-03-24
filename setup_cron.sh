#!/usr/bin/env bash
# setup_cron.sh
# 매일 아침 8시에 AI 뉴스 다이제스트를 실행하는 cron 작업을 등록합니다.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(command -v python3 || command -v python)"
SCRIPT="$SCRIPT_DIR/daily_news_digest.py"
LOG_FILE="$SCRIPT_DIR/digest.log"

if [ -z "$PYTHON" ]; then
    echo "[오류] python3 을 찾을 수 없습니다. Python 3를 먼저 설치하세요."
    exit 1
fi

# 의존성 설치
echo "[1/3] 패키지 설치 중..."
"$PYTHON" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"

# cron 작업 등록 (기존 동일 항목은 제거 후 재등록)
CRON_JOB="0 8 * * * DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/\$(id -u)/bus $PYTHON $SCRIPT >> $LOG_FILE 2>&1"

echo "[2/3] cron 작업 등록 중..."
# 기존 등록 항목 제거
(crontab -l 2>/dev/null | grep -v "daily_news_digest.py") | crontab -
# 새 항목 추가
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "[3/3] 완료!"
echo ""
echo "  등록된 cron 작업:"
crontab -l | grep "daily_news_digest"
echo ""
echo "  로그 파일: $LOG_FILE"
echo "  지금 바로 실행해 보려면:"
echo "    $PYTHON $SCRIPT"
echo ""
echo "  cron 작업 제거하려면:"
echo "    crontab -l | grep -v 'daily_news_digest.py' | crontab -"
