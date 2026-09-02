#!/usr/bin/env python3
"""
RK DAILY — Cloud-based Gita Lesson Generator + Telegram Sender
Runs via GitHub Actions at 7 AM IST (1:30 AM UTC) — No laptop, no server needed.
Sends daily spiritual lesson via Telegram Bot API (100% FREE).

Environment variables:
  TELEGRAM_BOT_TOKEN  - Bot token from @BotFather
  TELEGRAM_CHAT_ID     - Your Telegram chat ID
  LLM_API_KEY          - Google Gemini API key (free)
  LLM_BASE_URL         - https://generativelanguage.googleapis.com/v1beta/openai
  LLM_MODEL            - gemini-2.0-flash
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# ─── Data Loader ───
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_next_verse(data, progress):
    chapters = data["chapters"]
    current_ch = progress["chapter"]
    current_verse = progress["verse"]
    day_number = progress["day_number"]

    ch_data = None
    ch_index = 0
    for i, ch in enumerate(chapters):
        if ch["chapter"] == current_ch:
            ch_data = ch
            ch_index = i
            break

    if not ch_data:
        ch_data = chapters[0]
        ch_index = 0
        current_verse = 1

    verse_data = None
    for v in ch_data["verses"]:
        if v["verse"] == current_verse:
            verse_data = v
            break

    if not verse_data:
        verse_data = ch_data["verses"][0]
        current_verse = 1

    # Calculate next verse
    next_ch = current_ch
    next_verse = current_verse + 1
    if next_verse > ch_data["verse_count"]:
        if ch_index + 1 < len(chapters):
            next_ch = chapters[ch_index + 1]["chapter"]
            next_verse = 1
        else:
            next_ch = 1
            next_verse = 1

    return verse_data, ch_data, {
        "chapter": next_ch,
        "verse": next_verse,
        "day_number": day_number + 1
    }

# ─── LLM Lesson Generator ───
FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
]

def _extract_content(result):
    """Safely extract content from LLM response."""
    try:
        choice = result.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content")
        if content is None:
            reasoning = msg.get("reasoning_content") or msg.get("reasoning")
            if reasoning:
                return reasoning
            return None
        if not isinstance(content, str):
            content = str(content)
        return content
    except (IndexError, KeyError, TypeError):
        return None

def generate_lesson(verse_data, chapter_data, day_number):
    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
    configured_model = os.environ.get("LLM_MODEL", "gemini-3.5-flash-lite")

    if not api_key:
        print("ERROR: LLM_API_KEY not set")
        return None

    system_prompt = """You are Agent RK, a wise spiritual guru. Generate a daily Bhagavad Gita lesson in EXACTLY this Telegram HTML format.

KEEP IT SHORT AND POINT-WISE. No long paragraphs. Use simple language. Each section should be bullet points or 1-2 line answers.

🪻 <b>RK DAILY</b>
<i>Daily Wisdom from Sanatana Dharma</i>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 <b>Day {day}</b>
📖 <b>Bhagavad Gita — Chapter {ch}: {chapter_name}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🕉️ <b>VERSE/SHLOKA</b>
<code>{sanskrit}</code>

📝 <b>TRANSLITERATION</b>
<i>{transliteration}</i>

🇮🇳 <b>HINGLISH MEANING</b>
{hinglish_meaning}

🇬🇧 <b>ENGLISH MEANING</b>
{english_meaning}

📖 <b>VERSE IN SHORT (HINGLISH)</b>
• Is verse ka simple matlab 1-2 points mein
• Context — kab aur kyon bola gaya

📖 <b>VERSE IN SHORT (ENGLISH)</b>
• Simple meaning in 1-2 bullet points
• Context — when and why it was spoken

🌍 <b>REAL WORLD SCENARIO — HOW TO DEAL</b>
• <b>Situation:</b> [Modern real-life situation matching this verse — office, family, relationships, stress, failure, competition, etc.]
• <b>Problem:</b> [What problem arises in this situation]
• <b>How to handle:</b> [Step-by-step how to deal with it using this verse's wisdom — 2-3 bullet points]
• <b>Result:</b> [What happens when you apply this wisdom]

🦹🏹🦊 <b>3 LORDS — REAL LIFE EXAMPLES &amp; MINDSET</b>

🦹 <b>Krishna Ji — Real Situation &amp; Mindset</b>
• <b>Their real situation:</b> [Actual event from Krishna's life that matches this verse — e.g. Kurukshetra, Draupadi's disrobing, killing Kansa, etc.]
• <b>How Krishna dealt with it:</b> [What Krishna actually did in that situation — 1-2 points]
• <b>Krishna Mindset to adopt:</b> [What mindset Krishna used — how YOU can think like Krishna in your life]

🏹 <b>Rama Ji — Real Situation &amp; Mindset</b>
• <b>Their real situation:</b> [Actual event from Rama's life that matches this verse — e.g. exile, Sita's abduction, killing Ravana, leaving Sita, etc.]
• <b>How Rama dealt with it:</b> [What Rama actually did — 1-2 points]
• <b>Rama Mindset to adopt:</b> [What mindset Rama used — how YOU can think like Rama in your life]

🦊 <b>Hanuman Ji — Real Situation &amp; Mindset</b>
• <b>Their real situation:</b> [Actual event from Hanuman's life that matches this verse — e.g. jumping to Lanka, carrying mountain, opening chest showing Rama, burning Lanka, etc.]
• <b>How Hanuman dealt with it:</b> [What Hanuman actually did — 1-2 points]
• <b>Hanuman Mindset to adopt:</b> [What mindset Hanuman used — how YOU can think like Hanuman in your life]

 🕉️ <b>KRISHNA TEACHES HANUMAN &amp; RAMA</b>
• <b>Krishna says:</b> "Hanuman, is verse ka arth ye hai..." [Krishna explains this verse to Hanuman and Rama in a simple teaching dialogue — 2-3 lines]
• <b>Hanuman asks:</b> "Prabhu, main isse apne jivan mein kaise lagaoon?" [Hanuman asks a practical question about applying this]
• <b>Krishna answers:</b> [Krishna gives a simple practical answer — 1-2 lines]
• <b>Rama adds:</b> "Hanuman, ye bhi yaad rakh..." [Rama adds one more insight — 1 line]

🎯 <b>TODAY'S SADHANA — MAKE MINDSET LIKE 3 LORDS</b>
• Think like Krishna: [one practical step for today]
• Act like Rama: [one practical step for today]
• Serve like Hanuman: [one practical step for today]

🧠 <b>REMEMBER</b>
"[Short inspiring quote — 1 line]"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 Agent RK — Your Spiritual Guide
<i>For questions, just reply here</i>

CRITICAL RULES:
- SHORT and POINT-WISE — NO long paragraphs anywhere
- Simple language — as if explaining to a 15 year old
- Every section must be bullet points (•) or 1-2 line answers only
- REAL situations from Krishna, Rama, and Hanuman's actual lives (from scriptures) — not generic advice
- Krishna teaching Hanuman section must feel like a real conversation — dialogue format
- Show HOW each Lord dealt with similar situations in THEIR life, then tell reader how to adopt that SAME mindset
- Use HTML tags: <b>bold</b>, <i>italic</i>, <code>code</code> for formatting
- Do NOT use Markdown (*, _, `) — only HTML tags
- Escape &amp; as &amp;amp;, < as &amp;lt;, > as &amp;gt; in text content (but keep HTML tags intact)
- Keep the EXACT format above with all emojis and separators
- The entire message should be 2000-3500 characters
- Do NOT add any text before or after the formatted lesson"""

    user_prompt = f"""Generate the daily lesson for:

Day: {day_number}
Chapter: {chapter_data["chapter"]} — {chapter_data["name"]}
Verse: {verse_data["verse"]}

Sanskrit: {verse_data["sanskrit"]}
Transliteration: {verse_data["transliteration"]}
Hinglish Meaning: {verse_data["hinglish_meaning"]}
English Meaning: {verse_data["english_meaning"]}

Generate the FULL lesson in the exact format specified in the system prompt."""

    # Build model list: configured model first, then fallbacks (deduped)
    model_list = []
    if configured_model and configured_model not in model_list:
        model_list.append(configured_model)
    for m in FALLBACK_MODELS:
        if m not in model_list:
            model_list.append(m)
    
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    if "openrouter" in base_url.lower():
        headers["HTTP-Referer"] = "https://github.com/rk-guru/daily"
        headers["X-Title"] = "RK Daily Gita Lesson"
    
    max_attempts = 8
    max_tokens = 8000
    
    for attempt in range(max_attempts):
        model = model_list[attempt % len(model_list)]
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt.format(
                    day=day_number,
                    ch=chapter_data["chapter"],
                    chapter_name=chapter_data["name"],
                    sanskrit=verse_data["sanskrit"],
                    transliteration=verse_data["transliteration"],
                    hinglish_meaning=verse_data["hinglish_meaning"],
                    english_meaning=verse_data["english_meaning"]
                )},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": max_tokens
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
                lesson = _extract_content(result)
                if lesson and lesson.strip():
                    if attempt > 0:
                        print(f"✅ Lesson generated on retry {attempt+1} with model={model}")
                    return lesson
                print(f"⚠️ No content (attempt {attempt+1}) model={model}")
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            print(f"LLM API Error {e.code} (attempt {attempt+1}) model={model}: {error_body[:300]}")
            if e.code in (503, 429, 500, 502, 504) and attempt < max_attempts - 1:
                time.sleep(2 + attempt * 2)
                continue
            if attempt < max_attempts - 1:
                continue
        except Exception as e:
            print(f"LLM API Error (attempt {attempt+1}) model={model}: {e}")
            if attempt < max_attempts - 1:
                time.sleep(2)
                continue
    
    print("❌ All LLM retries failed")
    return None

# ─── Fallback Lesson ───
def generate_fallback_lesson(verse_data, chapter_data, day_number):
    return f"""🪻 <b>RK DAILY</b>
<i>Daily Wisdom from Sanatana Dharma</i>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 <b>Day {day_number}</b>
📖 <b>Bhagavad Gita — Chapter {chapter_data["chapter"]}: {chapter_data["name"]}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🕉️ <b>VERSE/SHLOKA</b>
<code>{verse_data["sanskrit"]}</code>

📝 <b>TRANSLITERATION</b>
<i>{verse_data["transliteration"]}</i>

🇮🇳 <b>HINGLISH MEANING</b>
{verse_data["hinglish_meaning"]}

🇬🇧 <b>ENGLISH MEANING</b>
{verse_data["english_meaning"]}

📖 <b>VERSE IN SHORT (HINGLISH)</b>
• Karma apne haath mein, phal Bhagwan par chhod do
• Arjuna yuddh se darr raha tha, Krishna ye sikha rahe the

📖 <b>VERSE IN SHORT (ENGLISH)</b>
• Do your duty, surrender results to God
• Arjuna was afraid to fight, Krishna taught this wisdom

🌍 <b>REAL WORLD SCENARIO — HOW TO DEAL</b>
• <b>Situation:</b> Office mein project par kaam karo, promotion ka result nahi tumhare haath mein
• <b>Problem:</b> Result ki chinta se kaam kharab hota hai, stress badhta hai
• <b>How to handle:</b> Best effort do, result ko Bhagwan par chhod do, daily kaam se pyaar karo
• <b>Result:</b> Mind shant rahega, kaam better hoga, success apne aap aayega

🦹🏹🦊 <b>3 LORDS — REAL LIFE EXAMPLES &amp; MINDSET</b>

🦹 <b>Krishna Ji — Real Situation &amp; Mindset</b>
• <b>Their real situation:</b> Kurukshetra mein Arjuna ka rath chalaya, khud fight nahi kiya
• <b>How Krishna dealt:</b> Sirf guide kiya, karma kiya bina phal ki chinta
• <b>Krishna Mindset to adopt:</b> Apna role samjho, best do, result chhod do

🏹 <b>Rama Ji — Real Situation &amp; Mindset</b>
• <b>Their real situation:</b> 14 saal vanvaas gaya bina complaint kiye
• <b>How Rama dealt:</b> Dharma follow kiya, acceptance se jiya, kingdom ka tyag kiya
• <b>Rama Mindset to adopt:</b> Jo situation hai us accept karo, dharma se mat hato

🦊 <b>Hanuman Ji — Real Situation &amp; Mindset</b>
• <b>Their real situation:</b> Lanka jaake Sita mata ko dhoondha, puri impossible task
• <b>How Hanuman dealt:</b> Bina result ke soche, Rama ke naam se sab kiya
• <b>Hanuman Mindset to adopt:</b> Seva bhaav se kaam karo, impossible nahi kuch bhi

🕉️ <b>KRISHNA TEACHES HANUMAN &amp; RAMA</b>
• <b>Krishna says:</b> "Hanuman, is verse ka arth ye hai — karma kar, phal mat soch. Tumne Lanka mein same kiya tha."
• <b>Hanuman asks:</b> "Prabhu, main result bilkul na sochun toh motivation kahan se aaye?"
• <b>Krishna answers:</b> "Motivation result se nahi, SEVA se aati hai. Tum mera naam leke udi the, wahi karo."
• <b>Rama adds:</b> "Hanuman, dharma ka kaam apna reward hota hai."

🎯 <b>TODAY'S SADHANA — MAKE MINDSET LIKE 3 LORDS</b>
• Think like Krishna: Aaj ek decision bina result ke chinta lo
• Act like Rama: Jo difficult hai us accept karke kar do
• Serve like Hanuman: Kisi ki bina expectation madad karo

🧠 <b>REMEMBER</b>
"Karma kar, phal ki chinta mat kar. Bhagwan sab kuch dekh raha hai."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 Agent RK — Your Spiritual Guide"""

# ─── Telegram Sender ───
def send_telegram(message):
    """Send message via Telegram Bot API (100% free, no limits)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "") or os.environ.get("BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "") or os.environ.get("AUTHORIZED_CHAT_ID", "")

    if not token or not chat_id:
        print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Telegram supports HTML formatting (more reliable than Markdown)
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            if result.get("ok"):
                print("✅ Telegram message sent successfully!")
                return True
            else:
                print(f"⚠️ Telegram API error: {result}")
                # Retry without Markdown if parsing failed
                return retry_without_markdown(token, chat_id, message)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"Telegram Error {e.code}: {error_body[:500]}")
        # Try without markdown
        if e.code == 400:
            print("Retrying without Markdown formatting...")
            return retry_without_markdown(token, chat_id, message)
        sys.exit(1)
    except Exception as e:
        print(f"Telegram Error: {e}")
        sys.exit(1)

def retry_without_markdown(token, chat_id, message):
    """Retry sending without HTML if formatting caused errors."""
    import re
    clean = re.sub(r'<[^>]+>', '', message)  # Strip all HTML tags
    clean = clean.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ')

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": clean,
        "disable_web_page_preview": True
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            if result.get("ok"):
                print("✅ Telegram message sent (plain text fallback)!")
                return True
            else:
                print(f"⚠️ Telegram API error: {result}")
                sys.exit(1)
    except Exception as e:
        print(f"Telegram retry failed: {e}")
        sys.exit(1)

# ─── Main ───
def main():
    print(f"🪻 RK DAILY — {datetime.now(IST).strftime('%Y-%m-%d %H:%M %Z')}")
    print("=" * 50)

    data = load_json("gita-data.json")
    progress = load_json("gita-progress.json")

    verse_data, chapter_data, new_progress = get_next_verse(data, progress)

    print(f"📖 Verse: Chapter {chapter_data['chapter']}, Verse {verse_data['verse']}")
    print(f"📅 Day: {progress['day_number']}")

    # Generate lesson via LLM
    print("✍️ Generating lesson via LLM...")
    lesson = generate_lesson(verse_data, chapter_data, progress["day_number"])

    if lesson:
        print("✅ Lesson generated via LLM!")
    else:
        print("⚠️ LLM failed, using fallback lesson...")
        lesson = generate_fallback_lesson(verse_data, chapter_data, progress["day_number"])
        print("✅ Fallback lesson generated!")

    # Send via Telegram
    print("📤 Sending to Telegram...")
    send_telegram(lesson)

    # Update progress
    save_json("gita-progress.json", new_progress)
    print(f"📊 Progress: Day {new_progress['day_number']}, "
          f"Ch {new_progress['chapter']}, Verse {new_progress['verse']}")
    print("=" * 50)
    print("🎉 Done! Lesson sent to Telegram.")

if __name__ == "__main__":
    main()