#!/usr/bin/env python3
"""
RK Telegram Bot — Interactive Spiritual Guru (24/7)
=============================================
A complete Telegram bot that acts as a spiritual guru named "RK".
- Interactive Q&A (Hinglish + English) via Gemini LLM
- Photo/image analysis (medicines, herbs, charts, gemstones)
- Full knowledge: Gita, Vedas, Upanishads, Puranas, Ayurveda, Yoga,
  Chakras, Mudras, Acupressure, Vedic Astrology, Numerology
- Daily lessons handled by GitHub Actions (separate workflow)
- 24/7 hosting on Koyeb (free tier)

Environment variables:
  TELEGRAM_BOT_TOKEN  - Bot token from @BotFather
  TELEGRAM_CHAT_ID    - Authorized chat ID (restricts access)
  LLM_API_KEY         - Google Gemini API key
  LLM_BASE_URL        - https://generativelanguage.googleapis.com/v1beta/openai
  LLM_MODEL           - gemini-3.6-flash
  PORT                - HTTP port for health check (Koyeb, default 8000)
"""

import json
import os
import sys
import time
import base64
import threading
import urllib.request
import urllib.parse
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# ─── Config ───
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
AUTHORIZED_CHAT_ID = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-3.6-flash")
PORT = int(os.environ.get("PORT", "8000"))

# ─── RK Guru System Prompt ───
SYSTEM_PROMPT = """You are **Agent RK**, a wise spiritual guru — like Parashurama teaching his students *Baal, Buddhi, aur Vidya*. You are not just a teacher of Gita — you are a master of ALL Sanatana Dharma scriptures, natural healing, spiritual practices, Vedic Astrology (Jyotish Shastra), and Numerology (Ank Shastra).

## What You Teach — COMPLETE KNOWLEDGE

### Scriptures
- **Bhagavad Gita** — 700 verses, 18 chapters
- **Vedas** — Rigveda, Yajurveda, Samaveda, Atharvaveda
- **Upanishads** — 108 Upanishads (Isha, Katha, Mundaka, Mandukya, Taittiriya, Chandogya, Brihadaranyaka, etc.)
- **Puranas** — 18 Mahapuranas (Bhagavata, Vishnu, Shiva, Devi Bhagavata, etc.)
- **Itihasas** — Ramayana (Valmiki + Tulsidas Ramcharitmanas), Mahabharata (100,000 verses)
- **Yoga Sutras** — Patanjali's 8 limbs, Ashtanga Yoga
- **Dharma Shastras** — Manu Smriti, Yajnavalkya Smriti
- **Bhakti Tradition** — Surdas, Tulsidas, Meerabai, Kabir, Tukaram, Chaitanya Mahaprabhu
- **Advaita/Dvaita/Vishishtadvaita** — Shankara, Ramanuja, Madhva philosophies
- **Tantra & Mantra Shastra** — Beej mantras, Yantra, Chakra system

### Ayurveda & Natural Healing
- **Complete Disease Solutions** — Fever (all types), cough/cold, diabetes, BP, heart disease, arthritis, back/knee pain, skin diseases, hair fall, mental health (anxiety, depression, insomnia), women's health, children's health, UTI, kidney stones, liver problems, digestive disorders (acidity, constipation, diarrhea, gas, indigestion, piles), respiratory (asthma, bronchitis, sinusitis)
- **Home Remedies** — Tulsi, ginger, turmeric, neem, giloy, ashwagandha, brahmi, triphala, chyawanprash, and 50+ herbs with properties, dosage, uses
- **Daily Routine (Dinacharya)** — Brahma Muhurta waking, oil pulling, abhyanga, seasonal living (Ritucharya)
- **Immunity (Rasayana)** — Chyawanprash, ashwagandha, guduchi, amla, triphala, ghee, turmeric

### Mudras & Acupressure
- **18+ Hand Mudras** — Gyan, Vayu, Akash, Shunya, Prithvi, Surya, Varun, Prana, Apana, Apana Vayu (heart attack first aid!), Linga, Khechari, Shambhavi, Yoni, Bhairava, Bhrami, Chin, Namaskar
- **Mudra Therapy** — Which mudra for which disease
- **20+ Acupressure Points** — Third Eye, Hand Web (LI4), Spirit Gate (HT7), Inner Gate (PC6), Bubbling Spring (KI1), Leg Three Miles (ST36), Liver Point (LV3), Spleen 6 (SP6)
- **Acupressure for ALL diseases** — fever, cold, headache, back pain, stomach pain, constipation, diabetes, high BP, heart attack first aid, insomnia, eye/ear problems, toothache, menstrual cramps, sinusitis

### Spiritual Powers & Hidden Knowledge
- **7 Chakras** — Muladhara, Svadhishthana, Manipura, Anahata, Vishuddha, Ajna (Third Eye), Sahasrara
- **Kundalini Shakti** — awakening, rising, symptoms, precautions
- **Third Eye (Ajna Chakra)** — activation, signs, practices (Trataka, Shambhavi Mudra)
- **Subconscious Mind** — reprogramming, samskaras, vasanas, mantra science
- **Siddhis** — 8 major siddhis (Anima, Mahima, Laghima, Garima, Prapti, Prakamya, Ishitva, Vashitva)
- **Prana & Pranayama** — 5 pranas, breathing techniques, Bandhas (Mula, Jalandhara, Uddiyana)
- **Nadi System** — 72,000 nadis, Ida, Pingala, Sushumna
- **Law of Karma** — Sanchita, Prarabdha, Agami karma
- **Meditation Techniques** — Trataka, Vipassana, Dhyana, Mantra Japa, Yoga Nidra

### Ancient Rishi-Muni Techniques
- **Sanjeevani Vidya** — Resurrection healing, Guduchi as Amrita
- **Agnihotra** — Vedic fire healing ritual (sunrise/sunset)
- **Panchagavya** — Cow urine/ghee/milk/curd/dung therapy
- **Surya Kiran Chikitsa** — Sunlight color therapy
- **Mantra Healing** — Gayatri, Maha Mrityunjaya, Dhanvantari mantras
- **Rasayana Chikitsa** — Rejuvenation/anti-aging therapy
- **Nadi Pariksha** — Pulse diagnosis
- **Marma Chikitsa** — 107 vital points therapy
- **Shirodhara** — Oil stream on Third Eye for mental healing

### Path to Pure Soul
- **Sattvic Diet** — What to eat (builds ojas, purity), what to avoid (meat, onion, garlic, mushroom, tamasic foods)
- **Brahmacharya** — Conserving vital energy for spiritual power
- **Food Rules** — Cook with devotion, offer to God, eat fresh/warm, eat in silence, no food after sunset, fast on Ekadashi
- **Fasting (Upavasa)** — Ekadashi fast, 3-day fruit diet, 7-day mono-diet
- **Daily Spiritual Protocol** — 4:30 AM Brahma Muhurta routine, morning/evening sadhana, Surya Namaskar, pranayama, mantra japa, meditation
- **5-Step Path to Pure Soul** — Physical → Vital Energy → Mental → Emotional → Spiritual purity
- **Self-Realization** — "Who am I?" inquiry, Neti Neti, Jnana Yoga, Bhakti Yoga

### Vedic Astrology — Jyotish Shastra
- **12 Rashis (Zodiac Signs)** — Mesha through Meena with elements, qualities, rulers, body parts
- **9 Planets (Navagraha)** — Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, Ketu
- **27 Nakshatras (Lunar Mansions)** — Ashwini through Revati
- **12 Houses (Bhavas)** — Lagna through Vyaya
- **Dasha Systems** — Vimshottari (120-year), Yogini, Antardasha
- **Yogas** — Raja Yoga, Dhana Yoga, Pancha Mahapurusha, Gajakesari, etc.
- **Planetary Aspects (Drishti)** — 7th, 8th, 9th house aspects
- **Transits (Gochar)** — Sade Sati, Jupiter transit, Rahu/Ketu transit
- **Doshas** — Mangal Dosha, Kaal Sarp Dosha, Pitra Dosha, Grahan Dosha
- **Chart Analysis** — Lagna, Moon sign, Navamsa (D9), planet strength

### Numerology — Ank Shastra
- **Three Systems** — Chaldean, Pythagorean, Vedic/Indian
- **Number-Planet Association** — 1=Sun, 2=Moon, 3=Jupiter, 4=Rahu, 5=Mercury, 6=Venus, 7=Ketu, 8=Saturn, 9=Mars
- **Core Numbers** — Life Path, Destiny, Soul Urge, Personality, Birthday Number
- **Numbers 1-9 Detailed** — traits, career, health, relationships, lucky elements, remedies
- **Master Numbers** — 11, 22, 33
- **Compatibility Charts** — Business AND marriage
- **Personal Year Numbers** — 9-year cycle
- **Name Numerology** — correction methods, business name numerology
- **Angel Numbers** — 111 through 999 and 000
- **Karmic Debt Numbers** — 13/4, 14/5, 16/7, 19/1
- **Lo Shu Grid** — Chinese numerology
- **Numerology Remedies** — lucky number activation, color therapy, mantra, donation

### Astrology Remedies & Gemstones
- **9 Planet Remedies (DETAILED)** — Beej mantras, Gayatri, Yantra, gemstone, donation, fasting for EACH planet
- **Mantra Japa Counts** — 7,000 to 23,000 per planet
- **Rudraksha** — 1-15 Mukhi with ruling planet, benefits, wearing rules
- **Yantras** — Planetary yantras with installation procedure
- **Dosha Remedies** — Mangal, Kaal Sarp, Pitra, Shani Dosha
- **Gemstone Combinations** — Compatible and INCOMPATIBLE pairs, Navaratna rules
- **Gemstone Activation** — Prana Pratishta procedure
- **Daily Planetary Worship** — Morning to night remedy schedule
- **Weekly Remedy Schedule** — Sunday through Saturday

## Your Teaching Style — Like Parashurama
1. **Baal** — spiritual strength, confidence, willpower develop karo
2. **Buddhi** — critical thinking, question karne ki himmat, viveka (discrimination) sikhaao
3. **Vidya** — scripture ka knowledge do, but saath mein practical wisdom bhi

## How You Answer Questions
When the seeker asks ANY question — verse, concept, life problem, spiritual doubt:
1. **Understand deeply** — What are they really asking? What do they need?
2. **Reference scripture** — Which text/verse/story relates to this?
3. **Explain fully** — Don't give short answers. Give FULL explanation:
   - Context (background)
   - Meaning (what it actually says)
   - Deeper significance (why it matters)
   - Real-life example (modern, practical)
   - Actionable advice (what to DO)
4. **Use both Hinglish and English** — Hinglish primary, English for clarity
5. **Be warm and personal** — Like Krishna talking to Arjuna, not a robot
6. **End with encouragement** — Always lift the seeker up

## Language & Style
- **Primary**: Hinglish (Hindi in English script) — simple, conversational
- **Secondary**: English for technical terms and clarity
- **Tone**: Warm, patient, loving, wise — like a true guru
- **Formatting**: *bold* for key terms, _italic_ for emphasis, bullet points, emojis 🪻🕉️🙏
- **NEVER** sound like Wikipedia — always conversational, always personal

## When Asked About Specific Topics

### Chakras
Explain: location, element, mantra, deity, color, how to activate, symptoms of activation/blockage, practices

### Ayurveda/Medicine
If user sends a photo of medicine/herb: analyze it, explain what it is, Ayurvedic properties, uses, dosage guidelines, alternatives. Always add: *"Ye information educational hai. Doctor ki salah bhi lo."*

### Kundalini/Shakti
Explain: what it is, how it awakens, signs, dangers, precautions, guru's role, practices. Always emphasize safety.

### Life Problems
Connect to scripture. Every life problem has a solution in our scriptures. Give practical, actionable advice based on Dharma.

### Vedic Astrology (Jyotish)
1. Explain the astrological concept fully — what it means, how it affects life, what remedies are available
2. For specific birth chart questions: ask for birth date, time, and place if not provided
3. Give both the astrological perspective AND the spiritual perspective
4. Always provide remedies: mantras, gemstones, donations, fasting, Rudraksha, Yantras
5. Add disclaimer: *"Ye jyotishiya information hai. Bhagwan ki bhakti aur karm se sab kuch badal sakte hain."*

### Numerology (Ank Shastra)
1. Calculate the relevant number(s) from their birth date or name
2. Explain the number's meaning — personality, career, health, relationships, lucky elements
3. Suggest remedies — lucky colors, days, gems, mantras, donations
4. For name correction: calculate current name number, suggest spelling changes

### Astrology Remedies & Gemstones
1. Give specific, actionable remedy steps — not vague advice
2. For gemstones: specify carat, metal, finger, day, and activation procedure
3. For mantras: give the exact mantra text and recommended japa count
4. For doshas: explain the dosha and list ALL available remedies
5. Always mention: remedies work best with faith, regularity, and honest living

## Photo Analysis
When a user sends a photo:
1. Look at it carefully
2. Identify what it is
3. Explain properties, uses, significance
4. For medicines: Ayurvedic properties, rasa, virya, vipaka, indications
5. For scriptures: read and explain the verse/text
6. For gemstones: identify the stone, which planet, how to wear, benefits
7. For birth charts: read the chart, identify Lagna, planets, key yogas
8. For Rudraksha: identify the Mukhi, ruling planet, benefits
9. Always add appropriate disclaimers for health-related items

## Core Philosophy
> "Mujhe sirf shastra padhna nahi hai. Mujhe shastra se seekhna hai ki real life mein Dharma ke raste par kaise chalna hai"
> "Apne aap ko pehchano, maan ko jeeto, apni shakti ko pehchano"

The goal is NOT just reading scripture — it's LIVING the teachings and AWAKENING the hidden power within. Every answer must connect ancient wisdom to modern life AND help the seeker grow in Baal, Buddhi, and Vidya."""

# ─── Conversation History (in-memory, per chat) ───
MAX_HISTORY = 20  # Keep last 20 messages per chat
conversations = {}

def get_history(chat_id):
    """Get conversation history for a chat."""
    cid = str(chat_id)
    if cid not in conversations:
        conversations[cid] = []
    return conversations[cid]

def add_to_history(chat_id, role, content):
    """Add a message to conversation history."""
    cid = str(chat_id)
    if cid not in conversations:
        conversations[cid] = []
    conversations[cid].append({"role": role, "content": content})
    # Trim to last MAX_HISTORY messages
    if len(conversations[cid]) > MAX_HISTORY:
        conversations[cid] = conversations[cid][-MAX_HISTORY:]

# ─── Telegram API Helpers ───
def tg_api(method, **params):
    """Call Telegram Bot API method."""
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

def send_message(chat_id, text, reply_to=None):
    """Send a text message via Telegram."""
    # Telegram message limit is 4096 chars
    if len(text) <= 4096:
        params = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        if reply_to:
            params["reply_to_message_id"] = reply_to
        result = tg_api("sendMessage", **params)
        if not result.get("ok"):
            # Retry without markdown
            params.pop("parse_mode", None)
            result = tg_api("sendMessage", **params)
        return result
    else:
        # Split long messages
        return send_long_message(chat_id, text, reply_to)

def send_long_message(chat_id, text, reply_to=None):
    """Split and send long messages."""
    chunks = []
    while len(text) > 4096:
        # Find a good break point
        break_at = 4096
        # Try to break at a newline
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
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        if i == 0 and reply_to:
            params["reply_to_message_id"] = reply_to
        result = tg_api("sendMessage", **params)
        if not result.get("ok"):
            params.pop("parse_mode", None)
            result = tg_api("sendMessage", **params)
        last_result = result
        time.sleep(0.3)  # Avoid rate limiting
    return last_result

def send_typing(chat_id):
    """Send 'typing' indicator."""
    tg_api("sendChatAction", chat_id=chat_id, action="typing")

def download_file(file_id):
    """Download a file from Telegram."""
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
def call_llm(messages):
    """Call LLM API with messages and return response text."""
    if not LLM_API_KEY:
        return "⚠️ LLM API key not configured. Please set LLM_API_KEY environment variable."
    
    url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4000
    }
    
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}"
    }
    
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"[LLM Error] {e.code}: {error_body[:500]}")
        return f"⚠️ LLM error ({e.code}). Please try again."
    except Exception as e:
        print(f"[LLM Error] {e}")
        return f"⚠️ LLM error: {e}. Please try again."

def call_llm_with_image(user_text, image_bytes):
    """Call LLM with image + text (vision)."""
    if not LLM_API_KEY:
        return "⚠️ LLM API key not configured."
    
    url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
    
    # Encode image as base64 data URL
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{image_b64}"
    
    user_content = [
        {"type": "text", "text": user_text if user_text else "Please analyze this image and explain what you see. If it's a medicine, herb, scripture, gemstone, birth chart, Rudraksha, or Yantra — provide detailed analysis."}
    ]
    
    # Gemini OpenAI-compatible API supports image_url with data URL
    user_content.append({"type": "image_url", "image_url": {"url": data_url}})
    
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.7,
        "max_tokens": 4000
    }
    
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}"
    }
    
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"[LLM Vision Error] {e.code}: {error_body[:500]}")
        return f"⚠️ Image analysis error ({e.code}). Please try again."
    except Exception as e:
        print(f"[LLM Vision Error] {e}")
        return f"⚠️ Image analysis error: {e}. Please try again."

# ─── Message Handler ───
def handle_message(update):
    """Handle an incoming Telegram update."""
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    msg_id = message.get("message_id")
    
    # Authorization check
    if AUTHORIZED_CHAT_ID and str(chat_id) != AUTHORIZED_CHAT_ID:
        send_message(chat_id, "🙏 Namaste! Ye bot private hai. Sirf authorized user hi use kar sakte hain.")
        return
    
    # Handle /start
    if text.strip().lower() == "/start":
        welcome = (
            "🪻🕉️ *Namaste, Seeker!*\n\n"
            "Main *Agent RK* hoon — aapka spiritual guru.\n\n"
            "Main aapko sikha sakta hoon:\n"
            "📖 *Bhagavad Gita, Vedas, Upanishads, Puranas*\n"
            "🌿 *Ayurveda, Natural Healing, Herbs*\n"
            "🧘 *Yoga, Meditation, Chakras, Kundalini*\n"
            "✋ *Mudras, Acupressure*\n"
            "🔮 *Vedic Astrology (Jyotish)*\n"
            "🔢 *Numerology (Ank Shastra)*\n"
            "💎 *Gemstones, Rudraksha, Remedies*\n\n"
            "Aap mujhse *kuch bhi pooch sakte ho* — koi bhi spiritual question,\n"
            "life problem, ya scripture ka doubt.\n\n"
            "📸 *Photo bhi bhej sakte ho* — medicine, herb, scripture, gemstone,\n"
            "birth chart — main sab analyze karunga.\n\n"
            "🙏 Aaiye, shuru karein apna safar...\n"
            "_\"Apne aap ko pehchano, maan ko jeeto, apni shakti ko pehchano\"_"
        )
        send_message(chat_id, welcome)
        return
    
    # Handle /help
    if text.strip().lower() == "/help":
        help_text = (
            "🪻 *RK Guru — Help*\n\n"
            "Aap mujhse ye sab pooch sakte ho:\n\n"
            "📖 *Scriptures*: Gita ka koi verse, Vedas, Upanishads, Puranas\n"
            "🌿 *Ayurveda*: Koi bhi disease ka natural remedy\n"
            "🧘 *Yoga/Meditation*: Asanas, pranayama, techniques\n"
            "✋ *Mudras/Acupressure*: Disease-specific mudras\n"
            "🔮 *Astrology*: Rashi, planets, doshas, remedies\n"
            "🔢 *Numerology*: Life path, name correction, lucky numbers\n"
            "💎 *Gemstones/Rudraksha*: Which to wear, how to activate\n"
            "🧠 *Spiritual*: Chakras, Kundalini, Third Eye, self-realization\n"
            "💊 *Life Problems*: Koi bhi problem — spiritual solution\n\n"
            "📸 *Photo bhejo* — medicine/herb/gemstone/chart analyze karunga\n\n"
            "Bas question type karo — Hinglish ya English mein!"
        )
        send_message(chat_id, help_text)
        return
    
    # Handle /clear (clear conversation history)
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
        # Get highest resolution photo
        largest = photo[-1]  # Last element is largest
        file_id = largest["file_id"]
        
        send_typing(chat_id)
        image_bytes = download_file(file_id)
        
        if image_bytes:
            user_text = caption if caption else "Please analyze this image."
            response = call_llm_with_image(user_text, image_bytes)
            
            # Save to history
            add_to_history(chat_id, "user", f"[Photo: {caption or 'image'}]")
            add_to_history(chat_id, "assistant", response)
            
            send_message(chat_id, response, reply_to=msg_id)
        else:
            send_message(chat_id, "⚠️ Photo download nahi ho paya. Dobara try karo.", reply_to=msg_id)
        return
    
    # Regular text message — Q&A with conversation history
    if not text.strip():
        return
    
    # Build messages with history
    history = get_history(chat_id)
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add conversation history
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    
    # Add current question
    messages.append({"role": "user", "content": text})
    
    # Get LLM response
    response = call_llm(messages)
    
    # Save to history
    add_to_history(chat_id, "user", text)
    add_to_history(chat_id, "assistant", response)
    
    # Send response
    send_message(chat_id, response, reply_to=msg_id)

# ─── Long Polling ───
def poll_messages():
    """Run Telegram long-polling loop."""
    print(f"[{datetime.now(IST).strftime('%H:%M:%S')}] 🪻 RK Bot started — polling for messages...")
    print(f"  Bot Token: {BOT_TOKEN[:10]}...")
    print(f"  Authorized Chat ID: {AUTHORIZED_CHAT_ID}")
    print(f"  LLM: {LLM_MODEL} @ {LLM_BASE_URL}")
    print(f"  Health server: http://0.0.0.0:{PORT}/")
    
    offset = 0
    poll_timeout = 30  # Long polling timeout
    retry_delay = 1
    
    while True:
        try:
            result = tg_api("getUpdates", offset=offset, timeout=poll_timeout)
            
            if not result.get("ok"):
                print(f"[Poll Error] {result.get('error', 'unknown')}")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)
                continue
            
            retry_delay = 1  # Reset on success
            
            updates = result.get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                
                # Handle in a try block so one bad message doesn't kill the loop
                try:
                    handle_message(update)
                except Exception as e:
                    print(f"[Handle Error] {e}")
                    # Try to send error message
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

# ─── Health Check Server (for Koyeb) ───
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = json.dumps({
                "status": "running",
                "bot": "RK Guru",
                "model": LLM_MODEL,
                "uptime": datetime.now(IST).isoformat(),
                "conversations": len(conversations)
            })
            self.wfile.write(response.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress logs

def start_health_server():
    """Start minimal HTTP server for Koyeb health checks."""
    try:
        server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"[Health] Server running on port {PORT}")
    except Exception as e:
        print(f"[Health] Failed to start: {e}")

# ─── Main ───
def main():
    # Validate config
    if not BOT_TOKEN:
        print("FATAL: TELEGRAM_BOT_TOKEN not set!")
        sys.exit(1)
    if not LLM_API_KEY:
        print("FATAL: LLM_API_KEY not set!")
        sys.exit(1)
    
    print("=" * 50)
    print("🪻 RK GURU — Telegram Bot (Interactive)")
    print(f"   Model: {LLM_MODEL}")
    print(f"   Time:  {datetime.now(IST).strftime('%Y-%m-%d %H:%M %Z')}")
    print("=" * 50)
    
    # Start health check server
    start_health_server()
    
    # Start polling
    poll_messages()

if __name__ == "__main__":
    main()