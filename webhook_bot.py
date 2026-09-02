#!/usr/bin/env python3
"""
RK Telegram Bot — Webhook Mode for Koyeb (24/7 always-on)
=========================================================
Receives messages INSTANTLY via Telegram webhook. No polling delay.
Also sends daily Gita lesson at 7 AM IST via internal scheduler.

Env vars:
  TELEGRAM_BOT_TOKEN  - Bot token from @BotFather
  TELEGRAM_CHAT_ID    - Authorized chat ID
  LLM_API_KEY         - Google Gemini API key
  LLM_BASE_URL        - https://generativelanguage.googleapis.com/v1beta/openai
  LLM_MODEL           - gemini-3.5-flash
  PORT                - Port to listen on (Koyeb sets this)
  WEBHOOK_URL         - Full HTTPS URL Koyeb assigned (for setting webhook)
"""

import json
import os
import sys
import re
import time
import base64
import threading
import urllib.request
import urllib.parse
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
import importlib.util

# Import generate_lesson.py for daily lesson
_spec = importlib.util.spec_from_file_location("generate_lesson", os.path.join(os.path.dirname(__file__), "generate_lesson.py"))
_gl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gl)

IST = timezone(timedelta(hours=5, minutes=30))

# ─── Config ───
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "") or os.environ.get("BOT_TOKEN", "")
AUTHORIZED_CHAT_ID = str(os.environ.get("TELEGRAM_CHAT_ID", "") or os.environ.get("AUTHORIZED_CHAT_ID", ""))
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-3.5-flash")
PORT = int(os.environ.get("PORT", "8000"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# ─── Multi-Provider Config (24/7, no single-provider limit) ───
# Groq: 14,400 req/day FREE — primary provider (get key from console.groq.com)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
# OpenRouter: free models available — last resort fallback
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Provider chain: Groq (fastest, highest limit) → Gemini (existing) → OpenRouter (free models)
# Each provider has its own key, base_url, and model list
PROVIDERS = []

# 1. Groq — primary (14,400 req/day, Llama 3.3 70B, fastest inference)
if GROQ_API_KEY:
    PROVIDERS.append({
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key": GROQ_API_KEY,
        "models": ["openai/gpt-oss-120b", "groq/compound", "openai/gpt-oss-20b", "groq/compound-mini"],
        "vision": False,  # Groq doesn't support vision yet
    })

# 2. Gemini — fallback (existing key, ~1,500 req/day, supports vision)
if LLM_API_KEY:
    gemini_models = [LLM_MODEL] if LLM_MODEL else []
    for m in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]:
        if m not in gemini_models:
            gemini_models.append(m)
    PROVIDERS.append({
        "name": "gemini",
        "base_url": LLM_BASE_URL,
        "key": LLM_API_KEY,
        "models": gemini_models,
        "vision": True,
    })

# 3. OpenRouter — last resort (free models, ~200 req/day)
if OPENROUTER_API_KEY:
    PROVIDERS.append({
        "name": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "key": OPENROUTER_API_KEY,
        "models": [
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
            "mistralai/mistral-small-3.1-24b-instruct:free",
        ],
        "vision": True,
    })

# If no providers configured, fall back to old single-provider mode
if not PROVIDERS and LLM_API_KEY:
    PROVIDERS.append({
        "name": "gemini",
        "base_url": LLM_BASE_URL,
        "key": LLM_API_KEY,
        "models": [LLM_MODEL or "gemini-2.5-flash"],
        "vision": True,
    })

# ─── System Prompt (compact for speed) ───
SYSTEM_PROMPT = """You are Agent RK, a wise spiritual guru mastering ALL Sanatana Dharma: Bhagavad Gita, Vedas, Upanishads, Puranas, Ramayana, Mahabharata, Yoga Sutras, Ayurveda, natural healing, mudras, acupressure, chakras, kundalini, meditation, Vedic Astrology (Jyotish), Numerology (Ank Shastra), gemstones, Rudraksha, mantras, yantras.

Teaching style: like Parashurama — develop Baal (strength), Buddhi (wisdom), Vidya (knowledge).

RESPONSE FORMAT (always follow this structure):
- Start with a warm greeting + emoji
- Use <b>bold</b> for KEY POINTS, important terms, and main sentences
- Use <i>italic</i> for Sanskrit words, verse references
- Use bullet points (•) for lists and steps
- Use line breaks between sections — never one big paragraph
- Use relevant emojis as section headers: 📖 🧘 💎 🔮 ✋ 🌿
- End with a short encouraging line + 🙏

Example format:
🪻 Namaste! Bahut accha prashna...
📖 <b>Gita 2.47</b> kehta hai:
• Point 1
• Point 2
💡 <b>Real-life example:</b> ...
🧘 <i>Practical tip:</i> ...
🙏 Aap zaroor safal honge!

RULES:
1. Use Hinglish primarily, English for technical terms
2. Use ONLY HTML tags: <b> <i> <u> <code>. Do NOT use Markdown (* or # or -).
3. Escape & as &amp;
4. Keep answers concise but complete — short paragraphs, bullet points
5. For life problems: connect to Dharma, give practical advice
6. For astrology: ask birth details if needed, give remedies
7. For gemstones: specify carat, metal, finger, day, activation
8. For photos: identify and analyze. Add health disclaimers.

Goal: connect ancient wisdom to modern life. Help seeker grow in Baal, Buddhi, Vidya."""

# ─── Debug: capture recent errors ───
recent_errors = []
recent_logs = []
def log_debug(msg):
    """Log a debug message visible via /debug endpoint."""
    from datetime import datetime
    ts = datetime.utcnow().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    recent_logs.append(entry)
    if len(recent_logs) > 20:
        recent_logs.pop(0)
    print(entry)

def log_error(msg):
    """Log an error visible via /debug endpoint."""
    from datetime import datetime
    ts = datetime.utcnow().strftime("%H:%M:%S")
    entry = f"[{ts}] ERROR: {msg}"
    recent_errors.append(entry)
    if len(recent_errors) > 20:
        recent_errors.pop(0)
    print(entry)

# ─── Conversation History (in-memory, per chat) ───
MAX_HISTORY = 10
conversations = {}

def get_history(chat_id):
    cid = str(chat_id)
    if cid not in conversations:
        conversations[cid] = []
    return conversations[cid]

def add_to_history(chat_id, role, content):
    cid = str(chat_id)
    if cid not in conversations:
        conversations[cid] = []
    conversations[cid].append({"role": role, "content": content})
    if len(conversations[cid]) > MAX_HISTORY:
        conversations[cid] = conversations[cid][-MAX_HISTORY:]

# ─── Telegram API Helpers ───
def tg_api(method, **params):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(params).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"[TG API Error] {method}: {e.code} - {error_body[:300]}")
        return {"ok": False, "error": error_body}
    except Exception as e:
        print(f"[TG API Error] {method}: {e}")
        return {"ok": False, "error": str(e)}

# ─── HTML Sanitizer — fix unclosed tags ───
def sanitize_html(text):
    """Sanitize LLM output for Telegram HTML parse_mode.
    Strips unsupported tags (p, br, ul, li, etc.) and keeps only b/i/u/s/code/pre/a."""
    # Remove <p> and </p> tags
    text = re.sub(r'</?p>', '', text)
    # Convert <br> to \n
    text = re.sub(r'<br\s*/?>', '\n', text)
    # Remove <ul>, </ul>; convert <li> to bullet
    text = re.sub(r'</?ul>', '', text)
    text = re.sub(r'<li>', '• ', text)
    text = re.sub(r'</li>', '\n', text)
    # Remove <h1>-<h6>, <div>, <span>
    text = re.sub(r'</?h[1-6]>', '', text)
    text = re.sub(r'</?div>', '', text)
    text = re.sub(r'</?span[^>]*>', '', text)
    # Convert **bold** to <b>bold</b> if LLM used markdown despite instructions
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Convert *italic* to <i>italic</i>
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    # Remove markdown code blocks ```...```
    text = re.sub(r'```[a-z]*\n?', '', text)
    text = re.sub(r'```', '', text)
    # Convert backtick code spans to <code>
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    # Fix double-encoding
    text = text.replace('&amp;amp;', '&amp;')
    text = text.replace('&amp;lt;', '&lt;').replace('&amp;gt;', '&gt;')
    # Allowed tags
    allowed = ["b", "i", "u", "s", "code", "pre", "a"]
    for tag in allowed:
        open_pattern = re.compile(rf'<{tag}(\s[^>]*)?>')
        close_pattern = re.compile(rf'</{tag}>')
        open_count = len(open_pattern.findall(text))
        close_count = len(close_pattern.findall(text))
        if open_count > close_count:
            text += f'</{tag}>' * (open_count - close_count)
    # Remove any other HTML tags not in allowed list
    text = re.sub(r'</?(?!/?[bius]|/?code|/?pre|/?a\b)[^>]+>', '', text)
    # Collapse excessive newlines (max 3 in a row)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    # NOTE: Do NOT truncate here — send_message() handles splitting long
    # messages into multiple Telegram messages via send_long_message().
    return text.strip()

def strip_html(text):
    """Strip all HTML tags for plain-text fallback."""
    text = re.sub(r'<[^>]+>', '', text)
    return text

def send_message(chat_id, text, reply_to=None):
    """Send a text message via Telegram. Uses HTML with sanitizer + plain-text fallback."""
    # Sanitize HTML first
    text = sanitize_html(text)
    
    if len(text) <= 4096:
        return _send_single(chat_id, text, reply_to)
    else:
        return send_long_message(chat_id, text, reply_to)

def _send_single(chat_id, text, reply_to=None):
    # Try HTML first
    params = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_to:
        params["reply_to_message_id"] = reply_to
    result = tg_api("sendMessage", **params)
    if not result.get("ok"):
        log_error(f"sendMessage HTML failed: {result.get('description', '?')}")
        # Fallback: strip ALL HTML, send plain text
        plain = strip_html(text)
        params = {
            "chat_id": chat_id,
            "text": plain,
            "disable_web_page_preview": True
        }
        result = tg_api("sendMessage", **params)
    return result

def send_long_message(chat_id, text, reply_to=None):
    """Split and send long messages."""
    chunks = []
    while len(text) > 4096:
        break_at = 4096
        nl = text.rfind("\n", 0, 4096)
        if nl > 3000:
            break_at = nl
        chunks.append(text[:break_at])
        text = text[break_at:].lstrip()
    chunks.append(text)
    
    last_result = None
    for i, chunk in enumerate(chunks):
        params = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if i == 0 and reply_to:
            params["reply_to_message_id"] = reply_to
        result = tg_api("sendMessage", **params)
        if not result.get("ok"):
            plain = strip_html(chunk)
            params = {"chat_id": chat_id, "text": plain, "disable_web_page_preview": True}
            result = tg_api("sendMessage", **params)
        last_result = result
        time.sleep(0.3)
    return last_result

def send_typing(chat_id):
    tg_api("sendChatAction", chat_id=chat_id, action="typing")

def download_file(file_id):
    result = tg_api("getFile", file_id=file_id)
    if not result.get("ok"):
        return None
    file_path = result["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except Exception as e:
        print(f"[Download Error] {e}")
        return None

# ─── LLM Helpers ───

def _extract_content(result):
    """Safely extract content from LLM response. Handles None, missing keys, string responses."""
    try:
        choice = result.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content")
        finish_reason = choice.get("finish_reason", "?")
        # Some models return None content (thinking models use all tokens for thinking)
        if content is None:
            # Check if there's a reasoning field
            reasoning = msg.get("reasoning_content") or msg.get("reasoning")
            if reasoning:
                return reasoning, finish_reason
            return None, finish_reason
        # Some models return non-string content
        if not isinstance(content, str):
            content = str(content)
        return content, finish_reason
    except (IndexError, KeyError, TypeError) as e:
        return None, f"parse_error: {e}"

def call_llm(messages, chat_id=None):
    """Call LLM with multi-provider fallback chain.
    Tries: Groq (14,400/day) → Gemini (1,500/day) → OpenRouter (200/day).
    NEVER shows error messages to user — always returns content or None."""
    if not PROVIDERS:
        return None
    
    # Trim conversation history to last 8 messages for context
    if len(messages) > 10:
        messages = [messages[0]] + messages[-9:]
    
    # Typing indicator in background
    typing_stop = threading.Event()
    def keep_typing():
        while not typing_stop.is_set():
            if chat_id:
                send_typing(chat_id)
            typing_stop.wait(3.0)
    
    if chat_id:
        typing_thread = threading.Thread(target=keep_typing, daemon=True)
        typing_thread.start()
    
    max_tokens = 4000
    
    # Build attempt list: each provider × each model, in priority order
    # Groq model 1, Groq model 2, Gemini model 1, Gemini model 2, ...
    attempts = []
    for provider in PROVIDERS:
        for model in provider["models"]:
            attempts.append((provider, model))
    
    # If we have few attempts, cycle through them more times
    max_tries = min(len(attempts) * 2, 8)  # up to 8 tries
    
    for attempt_num in range(max_tries):
        provider, model = attempts[attempt_num % len(attempts)]
        url = f"{provider['base_url'].rstrip('/')}/chat/completions"
        
        # Groq free tier: 8000 TPM — use smaller max_tokens to avoid 413
        provider_max = 3000 if provider["name"] == "groq" else max_tokens
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": provider_max
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider['key']}",
            "User-Agent": "RK-Guru-Bot/1.0"
        }
        # OpenRouter needs extra headers
        if provider["name"] == "openrouter":
            headers["HTTP-Referer"] = "https://rk-guru-bot.onrender.com"
            headers["X-Title"] = "RK Guru Bot"
        
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content, finish_reason = _extract_content(result)
                
                if content and content.strip():
                    if attempt_num > 0:
                        log_debug(f"LLM OK on attempt {attempt_num+1} provider={provider['name']} model={model}")
                    typing_stop.set()
                    return content
                
                # content is None — try next
                log_debug(f"LLM no content (finish={finish_reason}) attempt {attempt_num+1} {provider['name']}/{model}")
                if attempt_num < max_tries - 1:
                    time.sleep(1)
                    continue
                else:
                    log_error(f"LLM no content after all {max_tries} attempts")
                    typing_stop.set()
                    return None
                    
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")[:300]
            log_error(f"LLM {provider['name']}/{model} HTTP {e.code} (attempt {attempt_num+1}): {error_body}")
            if e.code in (503, 429, 500, 502, 504) and attempt_num < max_tries - 1:
                # progressive backoff: 2s, 3s, 4s, 5s...
                time.sleep(2 + attempt_num)
                continue
            if attempt_num < max_tries - 1:
                continue
            typing_stop.set()
            return None
        except Exception as e:
            log_error(f"LLM {provider['name']}/{model} error (attempt {attempt_num+1}): {e}")
            if attempt_num < max_tries - 1:
                time.sleep(2)
                continue
            typing_stop.set()
            return None
    
    typing_stop.set()
    return None

def call_llm_with_image(user_text, image_bytes, chat_id=None):
    """Call LLM with image — uses vision-capable providers only (Gemini, OpenRouter).
    Groq doesn't support vision yet, so it's skipped for image queries."""
    vision_providers = [p for p in PROVIDERS if p.get("vision", False)]
    if not vision_providers:
        return None
    
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{image_b64}"
    
    user_content = [
        {"type": "text", "text": user_text if user_text else "Please analyze this image."}
    ]
    user_content.append({"type": "image_url", "image_url": {"url": data_url}})
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]
    
    # Typing indicator
    typing_stop = threading.Event()
    def keep_typing():
        while not typing_stop.is_set():
            if chat_id:
                send_typing(chat_id)
            typing_stop.wait(3.0)
    if chat_id:
        typing_thread = threading.Thread(target=keep_typing, daemon=True)
        typing_thread.start()
    
    max_tokens = 4000
    
    # Build attempt list from vision-capable providers only
    attempts = []
    for provider in vision_providers:
        for model in provider["models"]:
            attempts.append((provider, model))
    
    max_tries = min(len(attempts) * 2, 8)
    
    for attempt_num in range(max_tries):
        provider, model = attempts[attempt_num % len(attempts)]
        url = f"{provider['base_url'].rstrip('/')}/chat/completions"
        
        provider_max = 3000 if provider["name"] == "groq" else max_tokens
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": provider_max
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider['key']}",
            "User-Agent": "RK-Guru-Bot/1.0"
        }
        if provider["name"] == "openrouter":
            headers["HTTP-Referer"] = "https://rk-guru-bot.onrender.com"
            headers["X-Title"] = "RK Guru Bot"
        
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content, finish_reason = _extract_content(result)
                if content and content.strip():
                    typing_stop.set()
                    return content
                log_debug(f"Vision LLM no content (finish={finish_reason}) attempt {attempt_num+1} {provider['name']}/{model}")
                if attempt_num < max_tries - 1:
                    time.sleep(1)
                    continue
                typing_stop.set()
                return None
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")[:300]
            log_error(f"Vision LLM {provider['name']}/{model} HTTP {e.code} (attempt {attempt_num+1}): {error_body}")
            if e.code in (503, 429, 500, 502, 504) and attempt_num < max_tries - 1:
                time.sleep(2 + attempt_num)
                continue
            if attempt_num < max_tries - 1:
                continue
            typing_stop.set()
            return None
        except Exception as e:
            log_error(f"Vision LLM {provider['name']}/{model} error (attempt {attempt_num+1}): {e}")
            if attempt_num < max_tries - 1:
                time.sleep(2)
                continue
            typing_stop.set()
            return None
    
    typing_stop.set()
    return None

# ─── Message Handler ───
def handle_message(update):
    try:
        message = update.get("message") or update.get("edited_message")
        if not message:
            log_debug("No message in update")
            return
        
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")
        msg_id = message.get("message_id")
        
        log_debug(f"Message from chat_id={chat_id}: '{text[:50]}'")
        
        # Authorization check
        if AUTHORIZED_CHAT_ID and str(chat_id) != AUTHORIZED_CHAT_ID:
            log_debug(f"Unauthorized: {chat_id} != {AUTHORIZED_CHAT_ID}")
            send_message(chat_id, "Namaste! Ye bot private hai. Sirf authorized user hi use kar sakte hain.")
            return
    
        # Handle /start
        if text.strip().lower() == "/start":
            welcome = (
                "🪻🕉️ <b>Namaste, Seeker!</b>\n\n"
                "Main <b>Agent RK</b> hoon — aapka spiritual guru.\n\n"
                "Main aapko sikha sakta hoon:\n"
                "📖 <b>Bhagavad Gita, Vedas, Upanishads, Puranas</b>\n"
                "🌿 <b>Ayurveda, Natural Healing, Herbs</b>\n"
                "🧘 <b>Yoga, Meditation, Chakras, Kundalini</b>\n"
                "✋ <b>Mudras, Acupressure</b>\n"
                "🔮 <b>Vedic Astrology (Jyotish)</b>\n"
                "🔢 <b>Numerology (Ank Shastra)</b>\n"
                "💎 <b>Gemstones, Rudraksha, Remedies</b>\n\n"
                "Aap mujhse <b>kuch bhi pooch sakte ho</b> — koi bhi spiritual question,\n"
                "life problem, ya scripture ka doubt.\n\n"
                "📸 <b>Photo bhi bhej sakte ho</b>\n\n"
                "🙏 Aaiye, shuru karein apna safar..."
            )
            send_message(chat_id, welcome)
            return
        
        if text.strip().lower() == "/help":
            help_text = (
                "🪻 <b>RK Guru — Help</b>\n\n"
                "📖 <b>Scriptures</b>: Gita, Vedas, Upanishads, Puranas\n"
                "🌿 <b>Ayurveda</b>: Natural remedies\n"
                "🧘 <b>Yoga/Meditation</b>: Asanas, pranayama\n"
                "✋ <b>Mudras/Acupressure</b>\n"
                "🔮 <b>Astrology</b>: Rashi, planets, remedies\n"
                "🔢 <b>Numerology</b>: Life path, lucky numbers\n"
                "💎 <b>Gemstones/Rudraksha</b>\n"
                "🧠 <b>Spiritual</b>: Chakras, Kundalini, Third Eye\n"
                "💊 <b>Life Problems</b>: Spiritual solutions\n\n"
                "📸 Photo bhejo — analyze karunga\n\n"
                "Bas question type karo — Hinglish ya English!"
            )
            send_message(chat_id, help_text)
            return
        
        if text.strip().lower() == "/clear":
            cid = str(chat_id)
            if cid in conversations:
                conversations[cid] = []
            send_message(chat_id, "🧹 Conversation history cleared! Naya sawaal poocho. 🪻")
            return
        
        # /lesson command — manually trigger today's Gita lesson
        if text.strip().lower() == "/lesson":
            send_message(chat_id, "📖 Generating today's Gita lesson... 🪻")
            try:
                send_daily_lesson()
                global last_lesson_date
                last_lesson_date = datetime.now(IST).strftime("%Y-%m-%d")
            except Exception as e:
                log_error(f"/lesson command error: {e}")
                send_message(chat_id, "⚠️ Lesson generate nahi ho paya. Thodi der baad /lesson try karo.")
            return
        
        # Send typing indicator
        send_typing(chat_id)
        
        # Check for photo
        photo = message.get("photo")
        caption = message.get("caption", "")
        
        if photo:
            largest = photo[-1]
            file_id = largest["file_id"]
            send_typing(chat_id)
            image_bytes = download_file(file_id)
            if image_bytes:
                user_text = caption if caption else "Please analyze this image."
                response = call_llm_with_image(user_text, image_bytes, chat_id)
                add_to_history(chat_id, "user", f"[Photo: {caption or 'image'}]")
                if response and response.strip():
                    clean = sanitize_html(response)
                    add_to_history(chat_id, "assistant", response)
                    send_long_message(chat_id, clean)
                else:
                    # Graceful retry — try once more with text-only fallback
                    add_to_history(chat_id, "assistant", "Image analyze nahi ho paya abhi.")
                    send_message(chat_id, "📸 Image abhi analyze nahi ho paya. Thodi der baad dobara bhejo. 🙏")
            else:
                send_message(chat_id, "📸 Photo download nahi ho paya. Dobara bhejo. 🙏")
            return
        
        # Regular text message
        if not text.strip():
            return
        
        # Build messages with history
        history = get_history(chat_id)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": text})
        
        # Regular text → call LLM, send single formatted response
        response = call_llm(messages, chat_id)
        if response and response.strip():
            clean = sanitize_html(response)
            add_to_history(chat_id, "user", text)
            add_to_history(chat_id, "assistant", response)
            send_long_message(chat_id, clean)
            log_debug(f"Reply sent to chat_id={chat_id}")
        else:
            # All 8 retries failed across 5 models — extremely rare
            # Retry once more with a fresh call (different model order due to timing)
            add_to_history(chat_id, "user", text)
            log_error("LLM returned empty after all retries — trying one final time")
            response = call_llm(messages, chat_id)
            if response and response.strip():
                clean = sanitize_html(response)
                add_to_history(chat_id, "assistant", response)
                send_long_message(chat_id, clean)
            else:
                send_message(chat_id,
                    "🪻 Abhi LLM servers overload ho rahe hain.\\n"
                    "Thodi der (2-3 min) baad dobara message bhejo. 🙏")
                log_error("LLM returned empty/None response after ALL retries including final retry")
    
    except Exception as e:
        log_error(f"handle_message crashed: {e}")
        import traceback
        log_error(traceback.format_exc())

# ─── Daily Gita Lesson Scheduler (7 AM IST) ───
last_lesson_date = None

def daily_lesson_checker():
    """Background thread that checks every 60s if it's 7 AM IST.
    Window: 7:00-7:59 AM IST. Also does a startup catch-up check."""
    global last_lesson_date
    # On startup, check if today's lesson was already sent
    now_ist = datetime.now(IST)
    today = now_ist.strftime("%Y-%m-%d")
    # If bot starts after 7 AM and lesson not sent yet, send it
    if now_ist.hour >= 7 and last_lesson_date != today:
        print(f"[Daily Lesson] Startup catch-up: sending for {today}...")
        try:
            send_daily_lesson()
            last_lesson_date = today
        except Exception as e:
            print(f"[Daily Lesson] Startup catch-up error: {e}")
    
    while True:
        try:
            now_ist = datetime.now(IST)
            today = now_ist.strftime("%Y-%m-%d")
            # 7:00-7:59 AM IST window — wide window so even if Render wakes up late, it still fires
            if now_ist.hour == 7 and last_lesson_date != today:
                print(f"[Daily Lesson] Sending Gita lesson for {today}...")
                send_daily_lesson()
                last_lesson_date = today
        except Exception as e:
            print(f"[Daily Lesson Error] {e}")
        time.sleep(60)

def send_daily_lesson():
    """Generate and send daily Gita lesson using generate_lesson module."""
    try:
        data = _gl.load_json("gita-data.json")
        progress = _gl.load_json("gita-progress.json")
        verse_data, chapter_data, new_progress = _gl.get_next_verse(data, progress)
        
        print(f"[Daily Lesson] Ch{chapter_data['chapter']} V{verse_data['verse']} Day {progress['day_number']}")
        lesson = _gl.generate_lesson(verse_data, chapter_data, progress["day_number"])
        
        if not lesson:
            lesson = _gl.generate_fallback_lesson(verse_data, chapter_data, progress["day_number"])
        
        if lesson:
            send_message(AUTHORIZED_CHAT_ID, lesson)
            _gl.save_json("gita-progress.json", new_progress)
            print("[Daily Lesson] ✅ Sent successfully")
        else:
            print("[Daily Lesson] ⚠️ No lesson generated")
    except Exception as e:
        print(f"[Daily Lesson Error] {e}")

# ─── Webhook HTTP Server ───
class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Health check + debug endpoint."""
        if self.path == "/" or self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write("RK Bot is running!".encode("utf-8"))
        elif self.path == "/debug":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            info = [
                f"=== RK BOT DEBUG ===",
                f"BOT_TOKEN: {'set' if BOT_TOKEN else 'MISSING'}",
                f"AUTHORIZED_CHAT_ID: {AUTHORIZED_CHAT_ID or 'MISSING'}",
                f"LLM_API_KEY (Gemini): {'set' if LLM_API_KEY else 'MISSING'}",
                f"LLM_MODEL: {LLM_MODEL}",
                f"LLM_BASE_URL: {LLM_BASE_URL}",
                f"GROQ_API_KEY: {'set' if GROQ_API_KEY else 'MISSING'}",
                f"OPENROUTER_API_KEY: {'set' if OPENROUTER_API_KEY else 'MISSING'}",
                f"Providers: {[p['name'] + '/' + p['models'][0] for p in PROVIDERS]}",
                f"PORT: {PORT}",
                f"WEBHOOK_URL: {WEBHOOK_URL or '(not set)'}",
                f"Conversations: {list(conversations.keys())}",
                f"",
                f"=== RECENT LOGS ===",
            ]
            for l in recent_logs:
                info.append(l)
            info.append(f"\n=== RECENT ERRORS ===")
            for e in recent_errors:
                info.append(e)
            if not recent_errors:
                info.append("(none)")
            self.wfile.write("\n".join(info).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        """Receive Telegram webhook updates."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        
        # Respond to Telegram immediately (200 OK)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')
        
        # Process message in background thread (don't block webhook response)
        try:
            update = json.loads(body.decode("utf-8"))
            log_debug(f"Webhook POST received: {str(update)[:200]}")
            # Handle in background so we don't block
            t = threading.Thread(target=handle_message, args=(update,), daemon=True)
            t.start()
        except Exception as e:
            log_error(f"Webhook POST error: {e}")
    
    def log_message(self, format, *args):
        # Suppress default logging, use our own
        pass

def set_webhook():
    """Set Telegram webhook to this server's URL."""
    if not WEBHOOK_URL:
        print("[Webhook] No WEBHOOK_URL set — skipping webhook setup")
        return
    
    webhook_path = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    result = tg_api("setWebhook", url=webhook_path, drop_pending_updates=True)
    if result.get("ok"):
        print(f"[Webhook] ✅ Set to {webhook_path}")
    else:
        print(f"[Webhook] ❌ Failed: {result}")

def main():
    print("=" * 50)
    print("🪻 RK GURU — Webhook Bot (Render 24/7)")
    print("=" * 50)
    print(f"Port: {PORT}")
    print(f"Webhook URL: {WEBHOOK_URL or '(not set)'}")
    print(f"Providers: {[p['name'] + '/' + p['models'][0] for p in PROVIDERS]}")
    print(f"Chat ID: {AUTHORIZED_CHAT_ID}")
    print()
    
    # Set webhook
    set_webhook()
    
    # Start daily lesson checker in background
    lesson_thread = threading.Thread(target=daily_lesson_checker, daemon=True)
    lesson_thread.start()
    print("[Daily Lesson] ✅ 7 AM IST scheduler started")
    
    # Start HTTP server
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    print(f"\n🚀 Server listening on port {PORT}")
    print("Waiting for messages...\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

if __name__ == "__main__":
    main()