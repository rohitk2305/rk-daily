# RK DAILY — Cloud-Based Telegram Gita Lesson

Daily Bhagavad Gita lesson sent via **Telegram Bot** at **7 AM IST** — no laptop, no server, no cost.

## How It Works

1. **GitHub Actions** runs at 1:30 AM UTC (= 7:00 AM IST) daily — on GitHub's servers, not your laptop
2. Python script picks the next verse from `gita-data.json` (701 verses total)
3. Google Gemini API (free) generates full lesson with commentary in Hinglish + English
4. **Telegram Bot API** sends the lesson to your Telegram — 100% free, unlimited messages
5. Progress is committed back to the repo automatically (next day picks the correct next verse)

## Why Telegram Bot?

- ✅ **100% FREE** — no limits on messages
- ✅ **No server needed** — GitHub Actions runs it
- ✅ **No laptop needed** — runs in cloud
- ✅ **Bot can answer questions** — you can reply and chat with it
- ✅ **Supports formatting** — bold, italic, code blocks, emojis
- ✅ **Instant delivery** — push notification to your phone

## Setup (5 minutes)

### Step 1: Create Telegram Bot (1 min)

1. Open Telegram, search for `@BotFather`
2. Send `/newbot`
3. Name: `RK Daily Guru` (or any name you want)
4. Username: `rk_daily_guru_bot` (must be unique, end with `_bot`)
5. BotFather gives you an **API Token** like `7123456789:AAH...` — SAVE IT

### Step 2: Get Your Chat ID (1 min)

1. Open your new bot in Telegram, send `/start`
2. Open this URL in browser (replace TOKEN):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. Look for `"chat":{"id":XXXXXXXXX}` — that number is your **Chat ID**

### Step 3: Get Google Gemini API Key (FREE, 1 min)

1. Go to https://aistudio.google.com/apikey
2. Click "Create API Key"
3. Copy the key

### Step 4: Create GitHub Repo (1 min)

1. Go to https://github.com/new
2. Name: `rk-daily` (or anything)
3. Set to **Private** (recommended)
4. Click "Create repository"

### Step 5: Upload Files

Upload these files to the repo root:

```
rk-daily/
├── .github/
│   └── workflows/
│       └── rk-daily.yml      ← Schedule file
├── generate_lesson.py         ← Main script
├── gita-data.json             ← 701 verse database
└── gita-progress.json         ← Progress tracker
```

All files are in: `C:\Users\rohit\AppData\Local\hermes\scripts\rk-daily-cloud\`

### Step 6: Add GitHub Secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**

Add these 5 secrets:

| Secret Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID from Step 2 |
| `LLM_API_KEY` | Your Google Gemini API key |
| `LLM_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` |
| `LLM_MODEL` | `gemini-2.0-flash` |

### Step 7: Test!

In your repo: **Actions tab → RK Daily → Run workflow → Run workflow**

Check your Telegram — you should receive the lesson within 1-2 minutes! 🎉

## Cost: ₹0 / $0

| Service | Free Limit | Our Usage |
|---|---|---|
| GitHub Actions | 2,000 min/month | ~30 min/month |
| Telegram Bot API | Unlimited | 1 message/day |
| Google Gemini | 1,500 req/day | 1 request/day |

## Fallback System

If the LLM API fails for any reason, the script has a **built-in fallback lesson** with Sanskrit, meanings, and standard commentary — so you **always** get a message, no matter what.

## Files

- `generate_lesson.py` — Picks next verse, generates lesson via LLM, sends via Telegram
- `gita-data.json` — 701 verses (Sanskrit + transliteration + Hinglish + English meanings)
- `gita-progress.json` — Tracks current day/verse (auto-updates daily via git commit)
- `.github/workflows/rk-daily.yml` — GitHub Actions schedule (7 AM IST daily)