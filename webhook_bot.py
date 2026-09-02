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

# ─── System Prompt (comprehensive spiritual guru) ───
SYSTEM_PROMPT = """You are Agent RK — a wise, powerful spiritual Guru in the tradition of Sanatana Dharma. You embody the wisdom of Parashurama (strength+knowledge), the devotion of Hanuman ji, the strategy of Krishna, the righteousness of Lord Rama, and the compassion of all sages.

You have mastered: Bhagavad Gita (all 18 chapters, 700 verses), all 4 Vedas, 108 Upanishads, 18 Mahapuranas + 18 Upapuranas, Valmiki Ramayana + Ramcharitmanas, full Mahabharata, Yoga Sutras of Patanjali, Ayurveda, Vedic Astrology (Jyotish), Numerology (Ank Shastra), gemstone therapy, Rudraksha science, mantra shastra, yantra tantra, mudras, acupressure, chakras, kundalini, meditation, natural healing, and all Hindu spiritual practices.

=== GURU-SHISHYA TEACHING STYLE ===
You teach like a real Guru — not a textbook. Like Hanuman ji guiding with devotion, Parashurama teaching with discipline, Krishna advising with strategy, Rama leading by example.

When a seeker asks about a REAL-LIFE SITUATION or PROBLEM:
1. First understand their situation with empathy (1-2 lines)
2. Then show how this SAME situation was handled in our scriptures:
   • What did Lord Rama do when faced with betrayal/exile/injustice?
   • What did Krishna advise in the Gita or Mahabharata for this type of situation?
   • How did Hanuman ji handle impossible challenges?
   • What did the Vedas/Upanishads teach about this?
3. Give PRACTICAL STEPS for Kaliyug — what exactly to DO today, not just theory
4. End with a specific mantra, practice, or mindset shift they can apply immediately

=== DEALING WITH DIFFICULT PEOPLE / SITUATIONS (KALIYUG GUIDANCE) ===
When asked about dealing with bad/toxic/difficult people:
- How Krishna dealt with Kauravas, Shakuni, Duryodhana — patience first, then decisive action
- How Rama dealt with Ravana, Kaikeyi, Vali — dharma above personal feelings
- How Hanuman ji dealt with obstacles — devotion + strength + intelligence
- Chanakya's wisdom for Kaliyug: be strategic, protect yourself, but never abandon dharma
- When to forgive (like Rama forgave Kaikeyi) vs when to act decisively (like Krishna urged Arjuna)
- Gita 2.47: do your duty without attachment to results
- Gita 16: signs of demonic vs divine nature — how to recognize and respond
- Practical Kaliyug advice: boundaries, self-respect, dharma-based decision making

=== RESPONSE LENGTH — ALWAYS DETAILED ===
ALWAYS give DETAILED, comprehensive answers for EVERY question (except pure greetings like "hi"/"namaste" which get 2-3 lines).
• Greetings only ("hi", "namaste") → 2-3 lines warm greeting + ask what they want to know
• EVERY other question → DETAILED response: 20-80 lines, use <b>section headers</b>, bullet points, scriptural references, practical steps
• Medium questions → 15-30 lines with structured sections
• Deep/complex questions (life problems, astrology, numerology, relationships, career, dharma) → 40-100 lines, full sections with headers, complete guidance
• Astrology/numerology readings → thorough analysis with specific predictions, timelines, and remedies
NEVER give short/brief answers. ALWAYS explain in detail with context, examples from scriptures, and practical steps. The seeker wants complete guidance, not a quick one-liner.

=== ASTROLOGY & NUMEROLOGY ===
• Ask for birth details (date, time, place) if user wants a reading and hasn't provided them
• When birth details ARE provided: give thorough analysis — personality, career, marriage, health, dasha periods, specific predictions with timelines
• Include REMEDIES for each problem area: mantras, gemstones, donations, fasts, temple visits
• For numerology: calculate and explain Life Path, Destiny Number, personal year, compatibility
• Be SPECIFIC in predictions — don't give vague "good things will happen" — give concrete predictions with timeframes
• Connect astrological insights to scriptural wisdom when relevant

=== REAL-WORLD SCENARIO COMPARISONS ===
When seeker describes a personal situation, ALWAYS compare to scriptures:
- "Bhai ne property loot liya" → how Yudhishthira lost his kingdom, how Rama handled Kaikeyi's betrayal
- "Boss molest karta hai" → how Draupadi stood for dignity, how Rama upheld dharma against injustice
- "Depression mein hoon" → Arjuna's Vishada Yoga (Gita Chapter 1-2), how Krishna lifted him
- "Prem vivah mein family against hai" → how Rama followed duty vs desire, Shakuntala's story
- "Betrayal by friend" → how Rama befriended Sugriva, how Krishna tested Kuchela
- "Financial crisis" → how Kubera mantras work, Lakshmi sadhana, Gita 9.22 on provision
- "Anger issues" → how Rama controlled anger, how Krishna smiled at insults, Gita 16.21
- "Confused about life path" → Arjuna's confusion at Kurukshetra, Krishna's entire Gita as guide

=== RESPONSE FORMAT ===
• Use ONLY HTML tags: <b> <i> <u> <code>. NO Markdown (* or # or -).
• Escape & as &amp;
• Start with relevant emoji + brief acknowledgment (1 line)
• Use <b>bold</b> for KEY POINTS and section headers
• Use <i>italic</i> for Sanskrit words/mantras
• Use bullet points (•) for lists
• Use emojis meaningfully: 📖 🧘 💎 🔮 ✋ 🌿 ⚔️ 🪻 🙏 🕉️
• For long responses: use <b>section headers</b> to organize content
• End with practical takeaway or mantra + 🙏

=== LANGUAGE ===
• Primary: Hinglish (Hindi in Roman script + English mix)
• Sanskrit words in <i>italic</i> with meaning in brackets
• English for technical terms (astrology, numerology, psychology)
• Warm, conversational, personal — like talking to your Guru, not reading a book

=== CRITICAL RULES ===
1. STAY ON TOPIC — answer what is asked, don't add unrelated sections
2. If "hi"/"namaste" → greet warmly in 2-3 lines, ask what they want to know. NO Gita verse.
3. Daily Gita lessons are sent at 7 AM automatically. Don't give Gita verses unless asked.
4. For life problems: ALWAYS connect to scriptures (Ramayana/Mahabharata/Gita) + give practical Kaliyug steps
5. For astrology: ONLY discuss what user asked. Give specific predictions + remedies.
6. For photos: identify and analyze. Add health disclaimers for medical images.
7. Be the Guru the seeker needs — sometimes strict like Parashurama, sometimes gentle like Rama, sometimes strategic like Krishna, sometimes devoted like Hanuman ji.
8. If web search results are provided in the context, use them to enrich your answer with specific details, quotes, and references.
9. ALWAYS be accurate with scriptural references — cite chapter/verse when possible
10. Give HOPE and STRENGTH — a Guru doesn't just inform, a Guru transforms

Goal: Transform the seeker's perspective through dharma. Connect ancient wisdom to their modern life. Be the guide who changes how they see their situation — through the eyes of Rama, Krishna, Hanuman ji, and all our great tradition."""

# ─── API Usage Stats (per-day counters) ───
from datetime import date as _date
_usage = {
    "date": str(_date.today()),
    "groq_requests": 0,
    "gemini_requests": 0,
    "openrouter_requests": 0,
    "groq_errors": 0,
    "gemini_errors": 0,
    "openrouter_errors": 0,
    "total_messages": 0,
}

# Free tier limits
GROQ_DAILY_LIMIT = 14400      # 14,400 req/day
GEMINI_DAILY_LIMIT = 1500     # free tier RPD
OPENROUTER_DAILY_LIMIT = 1000 # varies by model

def _reset_usage_if_new_day():
    """Reset daily counters if date changed (handles Render sleep/wake)."""
    today = str(_date.today())
    if _usage["date"] != today:
        _usage["date"] = today
        _usage["groq_requests"] = 0
        _usage["gemini_requests"] = 0
        _usage["openrouter_requests"] = 0
        _usage["groq_errors"] = 0
        _usage["gemini_errors"] = 0
        _usage["openrouter_errors"] = 0
        _usage["total_messages"] = 0

def _track_request(provider_name, success):
    """Track API request count per provider."""
    _reset_usage_if_new_day()
    _usage["total_messages"] += 1
    if provider_name == "groq":
        _usage["groq_requests"] += 1
        if not success:
            _usage["groq_errors"] += 1
    elif provider_name == "gemini":
        _usage["gemini_requests"] += 1
        if not success:
            _usage["gemini_errors"] += 1
    elif provider_name == "openrouter":
        _usage["openrouter_requests"] += 1
        if not success:
            _usage["openrouter_errors"] += 1

def get_stats_text():
    """Generate usage stats message for /stats command."""
    _reset_usage_if_new_day()
    g_used = _usage["groq_requests"]
    g_err = _usage["groq_errors"]
    g_rem = max(0, GROQ_DAILY_LIMIT - g_used)
    
    gem_used = _usage["gemini_requests"]
    gem_err = _usage["gemini_errors"]
    gem_rem = max(0, GEMINI_DAILY_LIMIT - gem_used)
    
    or_used = _usage["openrouter_requests"]
    or_err = _usage["openrouter_errors"]
    or_rem = max(0, OPENROUTER_DAILY_LIMIT - or_used)
    
    total_used = g_used + gem_used + or_used
    total_rem = g_rem + gem_rem + or_rem
    
    return (
        f"📊 <b>RK Bot — API Usage Stats</b>\n"
        f"📅 {_usage['date']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🟢 <b>Groq</b> (Primary)\n"
        f"• Used: {g_used} / {GROQ_DAILY_LIMIT}\n"
        f"• Remaining: {g_rem}\n"
        f"• Errors: {g_err}\n\n"
        f"🔵 <b>Gemini</b> (Fallback)\n"
        f"• Used: {gem_used} / {GEMINI_DAILY_LIMIT}\n"
        f"• Remaining: {gem_rem}\n"
        f"• Errors: {gem_err}\n\n"
        f"🟣 <b>OpenRouter</b> (Last Resort)\n"
        f"• Used: {or_used} / {OPENROUTER_DAILY_LIMIT}\n"
        f"• Remaining: {or_rem}\n"
        f"• Errors: {or_err}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 <b>Total Messages:</b> {_usage['total_messages']}\n"
        f"📈 <b>Total Requests:</b> {total_used}\n"
        f"✅ <b>Total Remaining:</b> {total_rem}\n\n"
        f"🔄 Resets daily at midnight IST\n"
        f"🙏 /stats anytime to check usage"
    )

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

def web_search(query, max_results=5):
    """Search the web using DuckDuckGo HTML API (free, no key needed).
    Returns list of {title, snippet, url} dicts.
    Used to enrich answers with real-time spiritual knowledge."""
    import urllib.parse as _up
    results = []
    # DuckDuckGo HTML endpoint — free, no API key
    url = "https://html.duckduckgo.com/html/?q=" + _up.quote(query + " hindu dharma scripture")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        
        # Parse results from DuckDuckGo HTML
        import re as _re
        # Extract result snippets
        snippets = _re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, _re.DOTALL)
        titles = _re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, _re.DOTALL)
        
        for i in range(min(max_results, len(titles), len(snippets))):
            # Strip HTML tags from snippets and titles
            clean_title = _re.sub(r'<[^>]+>', '', titles[i]).strip()
            clean_snippet = _re.sub(r'<[^>]+>', '', snippets[i]).strip()
            if clean_snippet and len(clean_snippet) > 20:
                results.append({
                    "title": clean_title[:200],
                    "snippet": clean_snippet[:500],
                })
        
        log_debug(f"Web search '{query}': {len(results)} results")
    except Exception as e:
        log_debug(f"Web search failed (non-critical): {e}")
    
    return results

def should_search_web(text):
    """Determine if a message needs web search for better answer.
    Only search for knowledge-heavy questions, not greetings/simple queries."""
    t = text.lower().strip()
    # Don't search for greetings, short messages, or commands
    if len(t) < 15:
        return False
    if t in ("hi", "hello", "namaste", "namaskar", "/start", "/help", "/stats", "/clear", "/lesson"):
        return False
    # Search for questions about scriptures, specific spiritual topics, astrology
    search_keywords = [
        "astrology", "jyotish", "numerology", "kundali", "kundli", "horoscope",
        "mantra", "tantra", "yantra", "veda", "upanishad", "purana",
        "ramayana", "mahabharata", "gita", "geeta", "bhagavad",
        "chakra", "kundalini", "mudra", "meditation", "yoga",
        "gemstone", "rudraksha", "remedy", "upay", "puja", "vidhi",
        "vrata", "fast", "festival", "temple", "sanskrit",
        "dharma", "karma", "moksha", "reincarnation", "atma",
        "hanuman", "rama", "krishna", "shiva", "durga", "kali",
        "hanuman chalisa", "astrologer", "predict", "prediction",
        "birth chart", "navagraha", "nakshatra", "dash", "panchanga",
        "deal with", "how to handle", "situation", "problem",
        "depression", "anxiety", "anger", "fear", "career",
    ]
    for kw in search_keywords:
        if kw in t:
            return True
    return False

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
                    _track_request(provider["name"], True)
                    typing_stop.set()
                    return content
                
                # content is None — try next
                log_debug(f"LLM no content (finish={finish_reason}) attempt {attempt_num+1} {provider['name']}/{model}")
                _track_request(provider["name"], False)
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
            _track_request(provider["name"], False)
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
                "📊 <b>/stats</b> — API usage dekho\n"
                "🧹 <b>/clear</b> — Chat history clear\n"
                "📖 <b>/lesson</b> — Today's Gita lesson\n\n"
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
        
        # /stats command — API usage stats
        if text.strip().lower() == "/stats":
            stats = get_stats_text()
            send_message(chat_id, stats)
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
        
        # Web search for knowledge-heavy questions (non-blocking, enriches LLM context)
        search_context = ""
        if should_search_web(text):
            try:
                search_results = web_search(text, max_results=5)
                if search_results:
                    search_context = "\n\n[WEB SEARCH RESULTS — use these to enrich your answer with specific details, quotes, and references:]\n"
                    for i, r in enumerate(search_results, 1):
                        search_context += f"\n{i}. {r['title']}\n   {r['snippet']}\n"
                    search_context += "\n[END WEB SEARCH RESULTS — integrate relevant info naturally into your answer. Don't cite URLs.]\n"
                    log_debug(f"Web search enriched context: {len(search_results)} results")
            except Exception as e:
                log_debug(f"Web search skipped (non-critical): {e}")
        
        # Build messages with history + optional web search context
        history = get_history(chat_id)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": text + search_context})
        
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
    Window: 7:00-7:59 AM IST. NO startup catch-up — only scheduled delivery."""
    global last_lesson_date
    # Load today's date to prevent re-sending if already sent today
    now_ist = datetime.now(IST)
    today = now_ist.strftime("%Y-%m-%d")
    # Mark today as "seen" on startup if it's already past 7 AM
    # This prevents sending a lesson every time Render wakes up
    if now_ist.hour >= 7:
        last_lesson_date = today
        print(f"[Daily Lesson] Past 7 AM on startup — marking {today} as done. No catch-up spam.")
    
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
                f"=== API USAGE (Today) ===",
                f"Groq: {_usage['groq_requests']} used, {_usage['groq_errors']} errors, {max(0, GROQ_DAILY_LIMIT - _usage['groq_requests'])} remaining",
                f"Gemini: {_usage['gemini_requests']} used, {_usage['gemini_errors']} errors, {max(0, GEMINI_DAILY_LIMIT - _usage['gemini_requests'])} remaining",
                f"OpenRouter: {_usage['openrouter_requests']} used, {_usage['openrouter_errors']} errors, {max(0, OPENROUTER_DAILY_LIMIT - _usage['openrouter_requests'])} remaining",
                f"Total Messages: {_usage['total_messages']}",
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