#!/bin/bash
# Check for Telegram responses
# Properly tracks update_id to only return NEW messages from the user

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "Telegram not configured"
    exit 1
fi

# State file to track last processed update_id
STATE_FILE="plans/.telegram_state"
RESPONSE_FILE="plans/.telegram_response"

# Load last update_id or default to 0
if [ -f "$STATE_FILE" ]; then
    LAST_UPDATE_ID=$(cat "$STATE_FILE")
else
    LAST_UPDATE_ID=0
fi

# Get updates from Telegram (only new ones after our last processed)
OFFSET=$((LAST_UPDATE_ID + 1))
RESPONSE=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates?offset=${OFFSET}&limit=10")

# Find messages from our chat that are text replies
MESSAGES=$(echo "$RESPONSE" | jq -r --arg chat "$TELEGRAM_CHAT_ID" '
  .result[]? |
  select(.message.chat.id == ($chat | tonumber)) |
  select(.message.text != null) |
  {update_id: .update_id, text: .message.text, date: .message.date}
')

if [ -z "$MESSAGES" ] || [ "$MESSAGES" = "null" ]; then
    echo "No new messages"
    exit 1
fi

# Get the latest message
LATEST=$(echo "$RESPONSE" | jq -r --arg chat "$TELEGRAM_CHAT_ID" '
  [.result[]? |
   select(.message.chat.id == ($chat | tonumber)) |
   select(.message.text != null)] |
  last // empty')

if [ -z "$LATEST" ] || [ "$LATEST" = "null" ]; then
    echo "No new messages"
    exit 1
fi

# Extract text and update_id
MESSAGE=$(echo "$LATEST" | jq -r '.message.text')
NEW_UPDATE_ID=$(echo "$LATEST" | jq -r '.update_id')

# Save the new update_id so we don't process this message again
echo "$NEW_UPDATE_ID" > "$STATE_FILE"

# Output the message
echo "$MESSAGE"

# Save to response file for the loop to pick up
echo "$MESSAGE" > "$RESPONSE_FILE"
echo "$(date -Iseconds)" >> "$RESPONSE_FILE"

exit 0
