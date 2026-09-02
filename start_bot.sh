#!/bin/bash
# Load API keys
eval "$(grep -v '^#' "/c/Users/rohit/AppData/Local/hermes/scripts/rk-daily-cloud/API_KEYS.env" | grep -v '^$' | sed 's/^/export /')"

# Map to bot env vars
export TELEGRAM_CHAT_ID="5408076321"
export LLM_API_KEY="$GEMINI_API_KEY"
export LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"
export LLM_MODEL="gemini-3.6-flash"
export PORT="8000"

cd "/c/Users/rohit/AppData/Local/hermes/scripts/rk-daily-cloud"
python bot.py