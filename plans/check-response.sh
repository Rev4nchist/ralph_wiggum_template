#!/bin/bash
# Check for Telegram responses
# Returns the latest message from the user if available

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "Telegram not configured"
    exit 1
fi

# Get updates from Telegram
RESPONSE=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates?offset=-1&limit=1")

# Extract the latest message
MESSAGE=$(echo "$RESPONSE" | jq -r '.result[-1].message.text // empty')

if [ -n "$MESSAGE" ]; then
    echo "$MESSAGE"

    # Save to response file for the loop to pick up
    echo "$MESSAGE" > plans/.telegram_response
    echo "$(date -Iseconds)" >> plans/.telegram_response
else
    echo "No new messages"
    exit 1
fi
