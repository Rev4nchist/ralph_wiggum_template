#!/bin/bash
# Wait for a Telegram response with timeout
# Usage: ./wait-response.sh <timeout_seconds>

TIMEOUT=${1:-300}  # Default 5 minutes
POLL_INTERVAL=10   # Check every 10 seconds

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "Telegram not configured"
    exit 1
fi

echo "Waiting for Telegram response (timeout: ${TIMEOUT}s)..."

# Clear any existing response file
rm -f plans/.telegram_response

# Get the current update offset
INITIAL_OFFSET=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates?limit=1" | jq -r '.result[-1].update_id // 0')
NEXT_OFFSET=$((INITIAL_OFFSET + 1))

ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    # Check for new messages
    RESPONSE=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates?offset=${NEXT_OFFSET}&limit=1&timeout=5")

    # Check if we got a new message
    MESSAGE=$(echo "$RESPONSE" | jq -r '.result[0].message.text // empty')
    UPDATE_ID=$(echo "$RESPONSE" | jq -r '.result[0].update_id // empty')

    if [ -n "$MESSAGE" ] && [ -n "$UPDATE_ID" ]; then
        echo "Response received: $MESSAGE"

        # Save response
        echo "$MESSAGE" > plans/.telegram_response
        echo "$(date -Iseconds)" >> plans/.telegram_response

        # Acknowledge the update
        curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates?offset=$((UPDATE_ID + 1))" > /dev/null

        # Send acknowledgment
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=✓ Got it! Continuing..." \
            > /dev/null

        exit 0
    fi

    sleep $POLL_INTERVAL
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
    echo "Waiting... ($ELAPSED/${TIMEOUT}s)"
done

echo "Timeout waiting for response"
exit 1
