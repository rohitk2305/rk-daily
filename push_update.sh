#!/bin/bash
# Push update to GitHub
eval "$(grep -v '^#' "/c/Users/rohit/AppData/Local/hermes/scripts/rk-daily-cloud/API_KEYS.env" | grep -v '^$' | sed 's/^/export /')"

# Make repo public (unlimited GitHub Actions minutes)
gh repo edit rohitk2305/rk-daily --visibility public 2>&1
echo "=== Repo visibility updated ==="

cd /tmp/rk-daily
git pull origin main 2>&1 | tail -3

# Copy new/updated files
cp "/c/Users/rohit/AppData/Local/hermes/scripts/rk-daily-cloud/poll_bot.py" .
cp "/c/Users/rohit/AppData/Local/hermes/scripts/rk-daily-cloud/.github/workflows/rk-bot-poll.yml" .github/workflows/
cp "/c/Users/rohit/AppData/Local/hermes/scripts/rk-daily-cloud/bot.py" .

echo "=== Files ready ==="
ls -la poll_bot.py .github/workflows/
git add -A
git commit -m "🤖 Update bot files (auto-push)" 2>&1
git push origin main 2>&1 | tail -5
echo "=== Push complete ==="