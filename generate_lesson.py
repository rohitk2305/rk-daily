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

# ─── Multi-Provider Config (same as webhook_bot.py) ───
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
LLM_API_KEY_GL = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL_GL = os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
LLM_MODEL_GL = os.environ.get("LLM_MODEL", "gemini-2.5-flash")

PROVIDERS = []
if GROQ_API_KEY:
    PROVIDERS.append({
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key": GROQ_API_KEY,
        "models": ["openai/gpt-oss-120b", "groq/compound", "openai/gpt-oss-20b", "groq/compound-mini"],
    })
if LLM_API_KEY_GL:
    gemini_models = [LLM_MODEL_GL] if LLM_MODEL_GL else []
    for m in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]:
        if m not in gemini_models:
            gemini_models.append(m)
    PROVIDERS.append({
        "name": "gemini",
        "base_url": LLM_BASE_URL_GL,
        "key": LLM_API_KEY_GL,
        "models": gemini_models,
    })
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
    })
if not PROVIDERS and LLM_API_KEY_GL:
    PROVIDERS.append({
        "name": "gemini",
        "base_url": LLM_BASE_URL_GL,
        "key": LLM_API_KEY_GL,
        "models": [LLM_MODEL_GL or "gemini-2.5-flash"],
    })

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
    if not PROVIDERS:
        print("ERROR: No LLM providers configured")
        return None

    system_prompt = """You are Agent RK, a wise spiritual guru. Generate a daily Bhagavad Gita lesson in EXACTLY this Telegram HTML format.

EVERY SECTION MUST BE IN BOTH HINGLISH AND ENGLISH. No section is Hinglish-only or English-only. Both languages side by side.

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

🌍 <b>REAL WORLD SCENARIO — HOW TO DEAL (HINGLISH)</b>
• <b>Situation:</b> [Modern real-life situation matching this verse — office, family, relationships, stress, failure, competition, etc. — in HINGLISH]
• <b>Problem:</b> [What problem arises — in HINGLISH]
• <b>How to handle:</b> [Step-by-step how to deal with it — 2-3 bullet points — in HINGLISH]
• <b>Result:</b> [What happens when you apply this wisdom — in HINGLISH]

🌍 <b>REAL WORLD SCENARIO — HOW TO DEAL (ENGLISH)</b>
• <b>Situation:</b> [Same situation — in ENGLISH]
• <b>Problem:</b> [Same problem — in ENGLISH]
• <b>How to handle:</b> [Same steps — in ENGLISH]
• <b>Result:</b> [Same result — in ENGLISH]

🦹🏹🦊 <b>3 LORDS — REAL LIFE EXAMPLES &amp; MINDSET</b>

🦹 <b>Krishna Ji — Hinglish</b>
• <b>Their real situation:</b> [Actual event from Krishna's life — in HINGLISH]
• <b>How Krishna dealt with it:</b> [What Krishna did — in HINGLISH]
• <b>Krishna Mindset to adopt:</b> [How YOU can think like Krishna — in HINGLISH]

🦹 <b>Krishna Ji — English</b>
• <b>Their real situation:</b> [Same event — in ENGLISH]
• <b>How Krishna dealt with it:</b> [What Krishna did — in ENGLISH]
• <b>Krishna Mindset to adopt:</b> [How YOU can think like Krishna — in ENGLISH]

🏹 <b>Rama Ji — Hinglish</b>
• <b>Their real situation:</b> [Actual event from Rama's life — in HINGLISH]
• <b>How Rama dealt with it:</b> [What Rama did — in HINGLISH]
• <b>Rama Mindset to adopt:</b> [How YOU can think like Rama — in HINGLISH]

🏹 <b>Rama Ji — English</b>
• <b>Their real situation:</b> [Same event — in ENGLISH]
• <b>How Rama dealt with it:</b> [What Rama did — in ENGLISH]
• <b>Rama Mindset to adopt:</b> [How YOU can think like Rama — in ENGLISH]

🦊 <b>Hanuman Ji — Hinglish</b>
• <b>Their real situation:</b> [Actual event from Hanuman's life — in HINGLISH]
• <b>How Hanuman dealt with it:</b> [What Hanuman did — in HINGLISH]
• <b>Hanuman Mindset to adopt:</b> [How YOU can think like Hanuman — in HINGLISH]

🦊 <b>Hanuman Ji — English</b>
• <b>Their real situation:</b> [Same event — in ENGLISH]
• <b>How Hanuman dealt with it:</b> [What Hanuman did — in ENGLISH]
• <b>Hanuman Mindset to adopt:</b> [How YOU can think like Hanuman — in ENGLISH]

🕉️ <b>KRISHNA TEACHES HANUMAN &amp; RAMA (HINGLISH)</b>
• <b>Krishna says:</b> "Hanuman, is verse ka arth ye hai..." [Krishna explains — in HINGLISH]
• <b>Hanuman asks:</b> "Prabhu, main isse apne jivan mein kaise lagaoon?" [In HINGLISH]
• <b>Krishna answers:</b> [Practical answer — in HINGLISH]
• <b>Rama adds:</b> "Hanuman, ye bhi yaad rakh..." [One more insight — in HINGLISH]

🕉️ <b>KRISHNA TEACHES HANUMAN &amp; RAMA (ENGLISH)</b>
• <b>Krishna says:</b> "Hanuman, the meaning of this verse is..." [Same explanation — in ENGLISH]
• <b>Hanuman asks:</b> "Lord, how can I apply this in my life?" [In ENGLISH]
• <b>Krishna answers:</b> [Same practical answer — in ENGLISH]
• <b>Rama adds:</b> "Hanuman, also remember..." [Same insight — in ENGLISH]

🎯 <b>TODAY'S SADHANA (HINGLISH)</b>
• Krishna ki tarah socho: [aaj ka practical step — HINGLISH]
• Rama ki tarah karo: [aaj ka practical step — HINGLISH]
• Hanuman ki tarah seva karo: [aaj ka practical step — HINGLISH]

🎯 <b>TODAY'S SADHANA (ENGLISH)</b>
• Think like Krishna: [same practical step — ENGLISH]
• Act like Rama: [same practical step — ENGLISH]
• Serve like Hanuman: [same practical step — ENGLISH]

🧠 <b>REMEMBER (HINGLISH)</b>
"[Short inspiring quote in HINGLISH — 1 line]"

🧠 <b>REMEMBER (ENGLISH)</b>
"[Same inspiring quote in ENGLISH — 1 line]"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 Agent RK — Your Spiritual Guide
<i>For questions, just reply here</i>

CRITICAL RULES:
- EVERY section must appear in BOTH Hinglish AND English — no exceptions
- Keep each language version short and point-wise — bullet points only
- Simple language — as if explaining to a 15 year old
- REAL situations from Krishna, Rama, and Hanuman's actual lives (from scriptures) — not generic advice
- Krishna teaching Hanuman section must feel like a real conversation — dialogue format
- Show HOW each Lord dealt with similar situations in THEIR life, then tell reader how to adopt that SAME mindset
- Use HTML tags: <b>bold</b>, <i>italic</i>, <code>code</code> for formatting
- Do NOT use Markdown (*, _, `) — only HTML tags
- Escape &amp; as &amp;amp;, < as &amp;lt;, > as &amp;gt; in text content (but keep HTML tags intact)
- Keep the EXACT format above with all emojis and separators
- The entire message should be 3000-5000 characters (it's longer because it's bilingual)
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

    # Build attempt list: each provider × each model
    attempts = []
    for provider in PROVIDERS:
        for model in provider["models"]:
            attempts.append((provider, model))
    
    max_attempts = min(len(attempts) * 2, 8)
    max_tokens = 4000
    
    for attempt in range(max_attempts):
        provider, model = attempts[attempt % len(attempts)]
        url = f"{provider['base_url'].rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider['key']}",
            "User-Agent": "RK-Guru-Bot/1.0"
        }
        if provider["name"] == "openrouter":
            headers["HTTP-Referer"] = "https://rk-guru-bot.onrender.com"
            headers["X-Title"] = "RK Daily Gita Lesson"
        
        provider_max = 4000  # bilingual lessons need more tokens
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
            "max_tokens": provider_max
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
                lesson = _extract_content(result)
                if lesson and lesson.strip():
                    if attempt > 0:
                        print(f"✅ Lesson generated on attempt {attempt+1} via {provider['name']}/{model}")
                    return lesson
                print(f"⚠️ No content (attempt {attempt+1}) {provider['name']}/{model}")
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            print(f"LLM API Error {e.code} (attempt {attempt+1}) {provider['name']}/{model}: {error_body[:300]}")
            if e.code in (503, 429, 500, 502, 504) and attempt < max_attempts - 1:
                time.sleep(2 + attempt)
                continue
            if attempt < max_attempts - 1:
                continue
        except Exception as e:
            print(f"LLM API Error (attempt {attempt+1}) {provider['name']}/{model}: {e}")
            if attempt < max_attempts - 1:
                time.sleep(2)
                continue
    
    print("❌ All LLM retries failed across all providers")
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

🌍 <b>REAL WORLD SCENARIO — HOW TO DEAL (HINGLISH)</b>
• <b>Situation:</b> Office mein project par kaam karo, promotion ka result nahi tumhare haath mein
• <b>Problem:</b> Result ki chinta se kaam kharab hota hai, stress badhta hai
• <b>How to handle:</b> Best effort do, result ko Bhagwan par chhod do, daily kaam se pyaar karo
• <b>Result:</b> Mind shant rahega, kaam better hoga, success apne aap aayega

🌍 <b>REAL WORLD SCENARIO — HOW TO DEAL (ENGLISH)</b>
• <b>Situation:</b> Work on your project, but the promotion result is not in your hands
• <b>Problem:</b> Worrying about results ruins the work and increases stress
• <b>How to handle:</b> Give your best effort, surrender results to God, love the daily work
• <b>Result:</b> Mind stays calm, work improves, success comes naturally

🦹🏹🦊 <b>3 LORDS — REAL LIFE EXAMPLES &amp; MINDSET</b>

🦹 <b>Krishna Ji — Hinglish</b>
• <b>Their real situation:</b> Kurukshetra mein Arjuna ka rath chalaya, khud fight nahi kiya
• <b>How Krishna dealt:</b> Sirf guide kiya, karma kiya bina phal ki chinta
• <b>Krishna Mindset to adopt:</b> Apna role samjho, best do, result chhod do

🦹 <b>Krishna Ji — English</b>
• <b>Their real situation:</b> Drove Arjuna's chariot at Kurukshetra, did not fight himself
• <b>How Krishna dealt:</b> Only guided, acted without worrying about results
• <b>Krishna Mindset to adopt:</b> Know your role, do your best, surrender results

🏹 <b>Rama Ji — Hinglish</b>
• <b>Their real situation:</b> 14 saal vanvaas gaya bina complaint kiye
• <b>How Rama dealt:</b> Dharma follow kiya, acceptance se jiya, kingdom ka tyag kiya
• <b>Rama Mindset to adopt:</b> Jo situation hai us accept karo, dharma se mat hato

🏹 <b>Rama Ji — English</b>
• <b>Their real situation:</b> Went into 14-year exile without complaint
• <b>How Rama dealt:</b> Followed dharma, lived with acceptance, gave up kingdom
• <b>Rama Mindset to adopt:</b> Accept your situation, never abandon dharma

🦊 <b>Hanuman Ji — Hinglish</b>
• <b>Their real situation:</b> Lanka jaake Sita mata ko dhoondha, puri impossible task
• <b>How Hanuman dealt:</b> Bina result ke soche, Rama ke naam se sab kiya
• <b>Hanuman Mindset to adopt:</b> Seva bhaav se kaam karo, impossible nahi kuch bhi

🦊 <b>Hanuman Ji — English</b>
• <b>Their real situation:</b> Went to Lanka to find Sita mata, a seemingly impossible task
• <b>How Hanuman dealt:</b> Acted without worrying about results, did everything in Rama's name
• <b>Hanuman Mindset to adopt:</b> Work with spirit of service, nothing is impossible

🕉️ <b>KRISHNA TEACHES HANUMAN &amp; RAMA (HINGLISH)</b>
• <b>Krishna says:</b> "Hanuman, is verse ka arth ye hai — karma kar, phal mat soch. Tumne Lanka mein same kiya tha."
• <b>Hanuman asks:</b> "Prabhu, main result bilkul na sochun toh motivation kahan se aaye?"
• <b>Krishna answers:</b> "Motivation result se nahi, SEVA se aati hai. Tum mera naam leke udi the, wahi karo."
• <b>Rama adds:</b> "Hanuman, dharma ka kaam apna reward hota hai."

🕉️ <b>KRISHNA TEACHES HANUMAN &amp; RAMA (ENGLISH)</b>
• <b>Krishna says:</b> "Hanuman, the meaning of this verse is — do your duty, don't think of results. You did the same in Lanka."
• <b>Hanuman asks:</b> "Lord, if I don't think of results at all, where will motivation come from?"
• <b>Krishna answers:</b> "Motivation comes from SERVICE, not results. You flew in my name — do the same."
• <b>Rama adds:</b> "Hanuman, the act of dharma is its own reward."

🎯 <b>TODAY'S SADHANA (HINGLISH)</b>
• Krishna ki tarah socho: Aaj ek decision bina result ke chinta lo
• Rama ki tarah karo: Jo difficult hai us accept karke kar do
• Hanuman ki tarah seva karo: Kisi ki bina expectation madad karo

🎯 <b>TODAY'S SADHANA (ENGLISH)</b>
• Think like Krishna: Make one decision today without worrying about the result
• Act like Rama: Accept what is difficult and do it
• Serve like Hanuman: Help someone without any expectation

🧠 <b>REMEMBER (HINGLISH)</b>
"Karma kar, phal ki chinta mat kar. Bhagwan sab kuch dekh raha hai."

🧠 <b>REMEMBER (ENGLISH)</b>
"Do your duty, don't worry about results. God is watching everything."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 Agent RK — Your Spiritual Guide"""

# ─── Telegram Sender ───
def send_telegram(message):
    """Send message via Telegram Bot API (100% free, no limits).
    Splits into multiple messages if >4096 chars (Telegram limit)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "") or os.environ.get("BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "") or os.environ.get("AUTHORIZED_CHAT_ID", "")

    if not token or not chat_id:
        print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        sys.exit(1)

    # Split message into chunks of <=4000 chars (safe margin under 4096 limit)
    # Try to split on line boundaries to avoid breaking HTML tags
    MAX_LEN = 4000
    if len(message) <= MAX_LEN:
        chunks = [message]
    else:
        chunks = []
        lines = message.split('\n')
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > MAX_LEN:
                if current:
                    chunks.append(current)
                current = line
            else:
                current = current + '\n' + line if current else line
        if current:
            chunks.append(current)
    
    print(f"📤 Sending {len(chunks)} message(s) to Telegram...")
    
    for i, chunk in enumerate(chunks):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": chunk,
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
                    print(f"✅ Telegram message {i+1}/{len(chunks)} sent successfully!")
                else:
                    print(f"⚠️ Telegram API error on chunk {i+1}: {result}")
                    # Retry without HTML for this chunk
                    retry_without_markdown(token, chat_id, chunk)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            print(f"Telegram Error {e.code} on chunk {i+1}: {error_body[:500]}")
            if e.code == 400:
                print("Retrying without HTML formatting...")
                retry_without_markdown(token, chat_id, chunk)
            else:
                sys.exit(1)
        except Exception as e:
            print(f"Telegram Error on chunk {i+1}: {e}")
            sys.exit(1)
    
    return True

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