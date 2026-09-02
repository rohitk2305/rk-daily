#!/usr/bin/env python3
"""
RK Telegram Bot — Time-limited polling for GitHub Actions
=========================================================
Polls Telegram for messages, answers via Gemini LLM, then exits after MAX_RUNTIME.
Designed to run inside GitHub Actions every 10 minutes for 24/7 coverage.

ALSO: Sends daily Gita lesson at 7 AM IST (1:30 AM UTC) window.
      Merged into polling so we only need ONE workflow that reliably fires.

Env vars (from GitHub Secrets):
  TELEGRAM_BOT_TOKEN  - Bot token from @BotFather
  TELEGRAM_CHAT_ID    - Authorized chat ID
  LLM_API_KEY         - Google Gemini API key
  LLM_BASE_URL        - https://generativelanguage.googleapis.com/v1beta/openai
  LLM_MODEL           - gemini-3.6-flash
  MAX_RUNTIME_MIN     - Max minutes to run before exiting (default 8)
"""

import json
import os
import sys
import time
import base64
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

# ─── Daily Lesson Integration ───
# Import generate_lesson.py functions for daily lesson at 7 AM IST
import importlib.util
_spec = importlib.util.spec_from_file_location("generate_lesson", os.path.join(os.path.dirname(__file__), "generate_lesson.py"))
_gl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gl)

IST = timezone(timedelta(hours=5, minutes=30))

# ─── Config ───
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
AUTHORIZED_CHAT_ID = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-3.6-flash")
MAX_RUNTIME = int(os.environ.get("MAX_RUNTIME_MIN", "4")) * 60  # seconds

# ─── RK Guru System Prompt (shared with bot.py) ───
SYSTEM_PROMPT = """You are Agent RK, a wise spiritual guru. You master ALL Sanatana Dharma: Bhagavad Gita, Vedas, Upanishads, Puranas, Ramayana, Mahabharata, Yoga Sutras, Ayurveda, natural healing, mudras, acupressure, chakras, kundalini, meditation, Vedic Astrology (Jyotish), Numerology (Ank Shastra), gemstones, Rudraksha, mantras, and yantras.

Teaching style: like Parashurama — develop Baal (strength), Buddhi (wisdom), Vidya (knowledge) in the seeker.

How to answer:
1. Understand what they really need. Reference relevant scripture/story.
2. Give FULL explanation: context, meaning, real-life example, actionable advice.
3. Use Hinglish primarily, English for technical terms. Be warm, personal — like Krishna to Arjuna.
4. Keep answers concise but complete. No unnecessary repetition.
5. End with encouragement.

For life problems: connect to Dharma, give practical advice.
For astrology: ask birth details if needed, give remedies.
For numerology: calculate, explain, suggest remedies.
For gemstones: specify carat, metal, finger, day, activation.
For photos: identify and analyze (medicine, herb, gemstone, chart, Rudraksha, Yantra). Add health disclaimers.

Use HTML tags: <b>bold</b>, <i>italic</i>, <code>code</code>. Do NOT use Markdown. Escape & as &amp;.

Goal: connect ancient wisdom to modern life. Help seeker grow in Baal, Buddhi, Vidya."""

# ─── Conversation History (in-memory, per chat) ───
MAX_HISTORY = 10  # Keep last 10 messages per chat (limited memory in CI)
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

def escape_html(text):
    """Escape HTML special characters for Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_message(chat_id, text, reply_to=None):
    """Send a text message via Telegram. Uses HTML parse mode with fallback to plain text."""
    # Telegram message limit is 4096 chars
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
        # Fallback: plain text, no parse mode, no reply_to
        params = {
            "chat_id": chat_id,
            "text": text,
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
            params.pop("parse_mode", None)
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
def call_llm(messages, chat_id=None):
    """Call LLM with continuous typing indicator. Sends 'typing' every 3s while waiting."""
    if not LLM_API_KEY:
        return "LLM API key not configured."
    
    url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
    
    # Trim conversation history to last 6 messages for speed
    if len(messages) > 8:
        messages = [messages[0]] + messages[-7:]
    
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 1500  # Reduced from 4000 for faster response
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LLM_API_KEY}"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    # Send typing indicator in background while LLM processes
    import threading
    typing_stop = threading.Event()
    def keep_typing():
        while not typing_stop.is_set():
            if chat_id:
                send_typing(chat_id)
            typing_stop.wait(3.0)
    
    if chat_id:
        typing_thread = threading.Thread(target=keep_typing, daemon=True)
        typing_thread.start()
    
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:  # Reduced from 120s to 45s
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"[LLM Error] {e.code}: {error_body[:500]}")
        return None  # Return None so caller can use fallback
    except Exception as e:
        print(f"[LLM Error] {e}")
        return None
    finally:
        typing_stop.set()  # Stop typing indicator

def call_llm_with_image(user_text, image_bytes, chat_id=None):
    if not LLM_API_KEY:
        return "LLM API key not configured."
    
    url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{image_b64}"
    
    user_content = [
        {"type": "text", "text": user_text if user_text else "Please analyze this image. If it's a medicine, herb, scripture, gemstone, birth chart, Rudraksha, or Yantra — provide detailed analysis."}
    ]
    user_content.append({"type": "image_url", "image_url": {"url": data_url}})
    
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.6,
        "max_tokens": 1500
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LLM_API_KEY}"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    # Send typing indicator in background
    import threading
    typing_stop = threading.Event()
    def keep_typing():
        while not typing_stop.is_set():
            if chat_id:
                send_typing(chat_id)
            typing_stop.wait(3.0)
    
    if chat_id:
        typing_thread = threading.Thread(target=keep_typing, daemon=True)
        typing_thread.start()
    
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"[LLM Vision Error] {e.code}: {error_body[:500]}")
        return None
    except Exception as e:
        print(f"[LLM Vision Error] {e}")
        return None
    finally:
        typing_stop.set()

# ─── Message Handler ───
def handle_message(update):
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    msg_id = message.get("message_id")
    
    # Authorization check
    if AUTHORIZED_CHAT_ID and str(chat_id) != AUTHORIZED_CHAT_ID:
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
            "📸 <b>Photo bhi bhej sakte ho</b> — medicine, herb, scripture, gemstone,\n"
            "birth chart — main sab analyze karunga.\n\n"
            "🙏 Aaiye, shuru karein apna safar...\n"
            "<i>\"Apne aap ko pehchano, maan ko jeeto, apni shakti ko pehchano\"</i>"
        )
        send_message(chat_id, welcome)
        return
    
    # Handle /help
    if text.strip().lower() == "/help":
        help_text = (
            "🪻 <b>RK Guru — Help</b>\n\n"
            "Aap mujhse ye sab pooch sakte ho:\n\n"
            "📖 <b>Scriptures</b>: Gita ka koi verse, Vedas, Upanishads, Puranas\n"
            "🌿 <b>Ayurveda</b>: Koi bhi disease ka natural remedy\n"
            "🧘 <b>Yoga/Meditation</b>: Asanas, pranayama, techniques\n"
            "✋ <b>Mudras/Acupressure</b>: Disease-specific mudras\n"
            "🔮 <b>Astrology</b>: Rashi, planets, doshas, remedies\n"
            "🔢 <b>Numerology</b>: Life path, name correction, lucky numbers\n"
            "💎 <b>Gemstones/Rudraksha</b>: Which to wear, how to activate\n"
            "🧠 <b>Spiritual</b>: Chakras, Kundalini, Third Eye, self-realization\n"
            "💊 <b>Life Problems</b>: Koi bhi problem — spiritual solution\n\n"
            "📸 <b>Photo bhejo</b> — medicine/herb/gemstone/chart analyze karunga\n\n"
            "Bas question type karo — Hinglish ya English mein!"
        )
        send_message(chat_id, help_text)
        return
    
    # Handle /clear
    if text.strip().lower() == "/clear":
        cid = str(chat_id)
        if cid in conversations:
            conversations[cid] = []
        send_message(chat_id, "🧹 Conversation history cleared! Naya sawaal poocho. 🪻")
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
            if not response:
                response = "⚠️ Image ab analyze nahi ho paya. Kripya thodi der baad dobara try karo. 🙏"
            add_to_history(chat_id, "user", f"[Photo: {caption or 'image'}]")
            add_to_history(chat_id, "assistant", response)
            send_message(chat_id, response)
        else:
            send_message(chat_id, "⚠️ Photo download nahi ho paya. Dobara try karo.")
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
    
    response = call_llm(messages, chat_id)
    
    if not response:
        response = ("🪻 Main ab thoda connect nahi kar paya. "
                    "Kripya 30 second baad dobara poocho. 🙏\n"
                    "Ya /clear karke naya sawaal poocho.")
    
    add_to_history(chat_id, "user", text)
    add_to_history(chat_id, "assistant", response)
    
    # Send response — NO reply_to to avoid "message to be replied not found" errors
    send_message(chat_id, response)

# ─── Process pending updates on startup (DON'T skip!) ───
def process_pending_updates():
    """Process ALL pending messages since last run — DON'T skip any!
    
    Uses getUpdates with offset=0 to get everything queued.
    Returns the offset to start polling from.
    """
    print("[Startup] Checking for pending messages...")
    offset = 0
    pending_count = 0
    
    # Get all pending updates (non-blocking, timeout=0)
    result = tg_api("getUpdates", offset=0, timeout=0)
    if result.get("ok") and result.get("result"):
        updates = result["result"]
        pending_count = len(updates)
        print(f"[Startup] Found {pending_count} pending message(s) — processing ALL...")
        for update in updates:
            offset = update["update_id"] + 1
            try:
                # Only process messages from last 30 minutes (avoid replying to very old msgs)
                msg = update.get("message") or update.get("edited_message")
                if msg:
                    msg_date = msg.get("date", 0)
                    now_ts = int(time.time())
                    age_min = (now_ts - msg_date) / 60
                    if age_min > 30:
                        print(f"[Startup] Skipping old message ({age_min:.0f} min old)")
                        continue
                handle_message(update)
            except Exception as e:
                print(f"[Startup Handle Error] {e}")
        # Mark them as processed
        if offset > 0:
            tg_api("getUpdates", offset=offset, timeout=0)
    else:
        print("[Startup] No pending messages")
    
    return offset

# ─── Time-limited Long Polling ───
def poll_messages():
    start_time = time.time()
    print(f"[{datetime.now(IST).strftime('%H:%M:%S')}] 🪻 RK Bot started — polling for {MAX_RUNTIME//60} minutes...")
    print(f"  Bot Token: {BOT_TOKEN[:10]}...")
    print(f"  Authorized Chat ID: {AUTHORIZED_CHAT_ID}")
    print(f"  LLM: {LLM_MODEL} @ {LLM_BASE_URL}")
    
    # Process ALL pending messages first (DON'T skip any!)
    offset = process_pending_updates()
    
    poll_timeout = 30
    retry_delay = 1
    messages_handled = 0
    
    while True:
        # Check if we've exceeded our runtime
        elapsed = time.time() - start_time
        if elapsed >= MAX_RUNTIME:
            print(f"[{datetime.now(IST).strftime('%H:%M:%S')}] ⏰ Runtime limit reached ({elapsed//60:.0f} min). Messages handled: {messages_handled}. Exiting gracefully.")
            break
        
        try:
            result = tg_api("getUpdates", offset=offset, timeout=poll_timeout)
            
            if not result.get("ok"):
                print(f"[Poll Error] {result.get('error', 'unknown')}")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)
                continue
            
            retry_delay = 1
            updates = result.get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    handle_message(update)
                    messages_handled += 1
                except Exception as e:
                    print(f"[Handle Error] {e}")
                    try:
                        chat_id = (update.get("message") or {}).get("chat", {}).get("id")
                        if chat_id:
                            send_message(chat_id, "⚠️ Koi technical issue aaya. Dobara try karo. 🙏")
                    except:
                        pass
        
        except KeyboardInterrupt:
            print("\n[Bot] Shutting down...")
            break
        except Exception as e:
            print(f"[Poll Loop Error] {e}")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 30)
    
    print(f"[{datetime.now(IST).strftime('%H:%M:%S')}] ✅ Bot exited. Total messages handled: {messages_handled}")

# ─── Daily Lesson Check ───
def should_send_daily_lesson():
    """Check if current time is in the 7 AM IST window (1:30-1:40 AM UTC).
    
    Polling runs at minutes 2,12,22,32,42,52. The 1:32 AM UTC run hits the window.
    We use a file-based lock so only ONE run per day sends the lesson.
    """
    now_ist = datetime.now(IST)
    hour_ist = now_ist.hour
    minute_ist = now_ist.minute
    
    # 7:00-7:10 AM IST = 1:30-1:40 AM UTC
    # Polling cron '2,12,22,32,42,52 * * * *' — 1:32 UTC = 7:02 IST is the window
    if hour_ist == 7 and minute_ist < 15:
        # Check if we already sent today using a lock file
        lock_file = os.path.join(os.path.dirname(__file__), ".daily-lock.json")
        today_str = now_ist.strftime("%Y-%m-%d")
        try:
            with open(lock_file, "r") as f:
                lock = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            lock = {"date": ""}
        
        if lock.get("date") == today_str:
            print(f"[Daily] Already sent lesson for {today_str}, skipping.")
            return False
        
        return True
    return False

def send_daily_lesson():
    """Generate and send daily Gita lesson, then update progress + lock file."""
    print("[Daily] 🪻 Sending daily Gita lesson at 7 AM IST window...")
    
    # Load gita data and progress
    script_dir = os.path.dirname(__file__)
    data_path = os.path.join(script_dir, "gita-data.json")
    progress_path = os.path.join(script_dir, "gita-progress.json")
    
    data = _gl.load_json(data_path)
    progress = _gl.load_json(progress_path)
    
    verse_data, chapter_data, new_progress = _gl.get_next_verse(data, progress)
    
    print(f"[Daily] 📖 Verse: Chapter {chapter_data['chapter']}, Verse {verse_data['verse']}")
    print(f"[Daily] 📅 Day: {progress['day_number']}")
    
    # Generate lesson via LLM
    print("[Daily] ✍️ Generating lesson via LLM...")
    lesson = _gl.generate_lesson(verse_data, chapter_data, progress["day_number"])
    
    if lesson:
        print("[Daily] ✅ Lesson generated via LLM!")
    else:
        print("[Daily] ⚠️ LLM failed, using fallback lesson...")
        lesson = _gl.generate_fallback_lesson(verse_data, chapter_data, progress["day_number"])
        print("[Daily] ✅ Fallback lesson generated!")
    
    # Send via Telegram
    print("[Daily] 📤 Sending to Telegram...")
    result = send_message(AUTHORIZED_CHAT_ID, lesson)
    if result.get("ok"):
        print("[Daily] ✅ Daily lesson sent successfully!")
    else:
        print(f"[Daily] ⚠️ Telegram send failed: {result}")
        return
    
    # Update progress file
    _gl.save_json(progress_path, new_progress)
    print(f"[Daily] 📊 Progress updated: Day {new_progress['day_number']}, "
          f"Ch {new_progress['chapter']}, Verse {new_progress['verse']}")
    
    # Write lock file so we don't send twice today
    lock_file = os.path.join(script_dir, ".daily-lock.json")
    now_ist = datetime.now(IST)
    with open(lock_file, "w") as f:
        json.dump({"date": now_ist.strftime("%Y-%m-%d")}, f)
    
    print("[Daily] 🔒 Lock file written — won't send again today.")

# ─── Main ───
def main():
    if not BOT_TOKEN:
        print("FATAL: TELEGRAM_BOT_TOKEN not set!")
        sys.exit(1)
    if not LLM_API_KEY:
        print("FATAL: LLM_API_KEY not set!")
        sys.exit(1)
    
    print("=" * 50)
    print("🪻 RK GURU — Telegram Bot (GitHub Actions Polling)")
    print(f"   Model: {LLM_MODEL}")
    print(f"   Max runtime: {MAX_RUNTIME//60} minutes")
    print(f"   Time:  {datetime.now(IST).strftime('%Y-%m-%d %H:%M %Z')}")
    print("=" * 50)
    
    # Check if it's 7 AM IST window — send daily lesson FIRST
    if should_send_daily_lesson():
        try:
            send_daily_lesson()
        except Exception as e:
            print(f"[Daily] ❌ Daily lesson error: {e}")
    
    # Continue with normal polling
    poll_messages()

if __name__ == "__main__":
    main()