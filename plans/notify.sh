#!/bin/bash
# Telegram Notification Script for Ralph Wiggum
# Usage: ./notify.sh <type> <message>
# Types: status, question, error, complete

TYPE=${1:-status}
MESSAGE=${2:-"No message provided"}

# Check for Telegram credentials
if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
    exit 0
fi

# Emoji based on type
case $TYPE in
    question)
        EMOJI="❓"
        ;;
    error)
        EMOJI="🔴"
        ;;
    complete)
        EMOJI="✅"
        ;;
    blocked)
        EMOJI="🚫"
        ;;
    *)
        EMOJI="🤖"
        ;;
esac

# Format message
FORMATTED_MESSAGE="$EMOJI *Ralph Wiggum*

$MESSAGE

_$(date '+%Y-%m-%d %H:%M:%S')_"

# Send to Telegram
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" \
    -d "text=${FORMATTED_MESSAGE}" \
    -d "parse_mode=Markdown" \
    > /dev/null 2>&1

echo "Notification sent: $TYPE"
