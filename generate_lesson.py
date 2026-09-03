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

    system_prompt = """You are Agent RK, a wise spiritual guru from Sanatana Dharma tradition. Generate a daily Bhagavad Gita lesson in EXACTLY this Telegram HTML format.

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

📖 <b>VERSE ELABORATION — TODA-TODA SAMJHO (HINGLISH)</b>
• <b>Pehla hissa:</b> [verse ka pehla part — alag se explain karo Hinglish mein. Important words ko <b>bold</b> karo]
• <b>Doosra hissa:</b> [verse ka doosra part — alag se explain karo. Important words <b>bold</b> karo]
• <b>Teesra hissa:</b> [agar verse lamba hai toh teesra part — explain karo. Important words <b>bold</b> karo]
• <b>Sabse zaroori sentence:</b> "[verse ki sabse important line — <b>highlight</b> karo]"
• <b>Deep arth:</b> [is verse ka deeper spiritual meaning — Hinglish mein, 2-3 lines]
• <b>Krishna ka updesha:</b> [Krishna is verse se kya sikhana chahte hain — Hinglish]

📖 <b>VERSE ELABORATION — PART BY PART EXPLANATION (ENGLISH)</b>
• <b>First part:</b> [first part of verse — explain separately in English. <b>Highlight</b> important words]
• <b>Second part:</b> [second part — explain separately. <b>Highlight</b> important words]
• <b>Third part:</b> [if verse is long, third part — explain. <b>Highlight</b> important words]
• <b>Key sentence:</b> "[most important line from verse — <b>highlight</b> it]"
• <b>Deep meaning:</b> [deeper spiritual meaning in English — 2-3 lines]
• <b>Krishna's teaching:</b> [what Krishna wants to teach through this verse — English]

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

⚔️ <b>KALIYUG MEIN ADHARMI LOGO SE KAISE DEAL KAREIN (HINGLISH)</b>
<i>Krishna, Rama aur Hanuman ji ki seekh par based — Gita ke is verse se solution</i>

• <b>Gali dene wale (verbal abusers):</b> [Is verse ke context mein kaise deal karein — Hinglish. <b>Important words bold karo</b>. Krishna kehte hain — unka gali unka karma hai, tumhara nahi. <b>Ignor</b> karo, apne dharam pe tike raho]
• <b>Chedne wale (direct harassers):</b> [Hinglish — <b>dhairya</b> rakho, lekin zaroorat ho toh <b>boundaries</b> set karo. Hanuman ji bhi bina kaaran nahi ladte the]
• <b>Indirect chedne wale (chidhane wale, taunters):</b> [Hinglish — jo indirectly chidhate hain, unki baaton pe <b>reaction</b> mat do. Krishna ne Kans ke threats ko bhi <b>ignor</b> kiya tha. <b>Vairagya</b> se kaam lo]
• <b>Hasne wale (mockers who laugh at you):</b> [Hinglish — tum dharam par chal rahe ho aur log <b>hasate</b> hain. Krishna ko bhi hasaya gaya tha. <b>Hansaane walo ko igno</b> karo — unka hasna unki samajh ki kami hai. <b>Tumhara marg tumhara hai</b>]
• <b>Ulta-sulta bolne wale (contradictory speakers):</b> [Hinglish — jo ulta bolte hain, confuse karte hain. <b>Buddhi</b> se unki baat ko pehchano. Krishna kehte hain — <b>vivek</b> se sach ko alag karo. Unki baaton mein mat phanso]
• <b>Gali dekh ke harkat karne wale (gesture provokers):</b> [Hinglish — jo dekh ke <b>harkat</b> karte hain, ishara karte hain. <b>Aankh neeche mat jhukao</b>. Hanuman ji jaisa <b> fearless</b> raho. Unki harkat unki gireez hai]
• <b>Raste se jaate hue chedna (passing-by teasers):</b> [Hinglish — raste se jaate hue log chedte hain. <b>Aage badho</b> — peeche mat dekho. Rama ne <b>vanvas</b> mein bahut logo ka apmaan sehka, bina ruke aage badhe]
• <b>Chalak log jo doosre ka pair khich ke upar jaate hain:</b> [Hinglish — unse <b>door</b> raho. Apna kaam <b>karma</b> se karo. Unki chaal unki problem hai]
• <b>Manipulators (zyada buddhi galat use karne wale):</b> [Hinglish — <b>buddhi</b> ka upyog karo. Hanuman ji jaise — unki buddhi ko apni <b>buddhi</b> se pehchano]
• <b>Dharam rokné wale (pura duniya against ho):</b> [Hinglish — jab <b>puri duniya</b> against ho, tab bhi <b>dharam</b> ke liye khade raho. Arjuna ne puri sena dekhi, darr laga, phir bhi Krishna kehte hain — <b>khade raho</b>. Rama ne <b>Kaikeyi</b> ke aage bhi dharma nahi chhoda]
• <b>Apna dharam nibhate hue aage kaise badho:</b> [Hinglish — <b>purpose</b> pe focus, <b>fearless</b> raho, <b>karma</b> karte raho]
• <b>Krishna/Rama/Hanuman ji ka updesha:</b> [Is verse ke context mein teeno Lord kya kehenge — Hinglish. <b>Calm</b>, <b>fearless</b>, <b>dharma-focused</b> raho]

⚔️ <b>DEALING WITH ADHARMIC PEOPLE IN KALIYUG (ENGLISH)</b>
<i>Based on teachings of Krishna, Rama and Hanuman ji — solution from this Gita verse</i>

• <b>Verbal abusers (those who abuse):</b> [How to deal in this verse's context — English. <b>Highlight key words</b>. Krishna says — their abuse is their karma, not yours. <b>Ignore</b> them]
• <b>Direct harassers:</b> [English — maintain <b>patience</b>, but set <b>boundaries</b> when needed]
• <b>Indirect taunters (those who provoke indirectly):</b> [English — don't <b>react</b> to their indirect taunts. Krishna ignored Kans's threats too. Use <b>detachment</b>]
• <b>Mockers (those who laugh at you):</b> [English — you walk on dharma and people <b>laugh</b>. Krishna was laughed at too. <b>Ignore the mockers</b> — their laughter shows their ignorance. <b>Your path is yours</b>]
• <b>Contradictory speakers (those who say opposite things):</b> [English — use <b>wisdom</b> to identify truth. Krishna says — use <b>discrimination</b> to separate truth from lies. Don't get trapped]
• <b>Gesture provokers (those who make gestures looking at you):</b> [English — <b>don't lower your eyes</b>. Be <b>fearless</b> like Hanuman ji. Their gestures show their downfall]
• <b>Passing-by teasers:</b> [English — <b>move forward</b> — don't look back. Rama faced many insults in <b>exile</b>, yet moved forward without stopping]
• <b>Cunning people who step on others to rise:</b> [English — stay <b>away</b> from them. Do your work through <b>karma</b>]
• <b>Manipulators who use intelligence for wrong deeds:</b> [English — use your <b>wisdom</b>. Like Hanuman ji — recognize their intelligence with your intelligence]
• <b>Those who block dharma (even if the whole world is against you):</b> [English — when <b>the whole world</b> is against you, still <b>stand for dharma</b>. Arjuna saw the entire army, was afraid, yet Krishna says — <b>stand firm</b>. Rama didn't abandon dharma even before <b>Kaikeyi</b>]
• <b>How to move forward while staying on dharma:</b> [English — focus on <b>purpose</b>, stay <b>fearless</b>, keep doing <b>karma</b>]
• <b>Krishna/Rama/Hanuman ji's guidance:</b> [What the three Lords would say — English. Stay <b>calm</b>, <b>fearless</b>, <b>dharma-focused</b>]

🧘 <b>ANTAR SHANTI — STRESS, DEPRESSION, ANXIETY SE KAISE BACHEIN (HINGLISH)</b>
<i>Gita ke is verse se — Krishna tumhe sikhate hain</i>

• <b>Stress kyon aata hai:</b> [Hinglish — is verse ke context mein. Stress tab aata hai jab hum <b>phal</b> ke baare mein sochte hain, <b>karma</b> chhod kar]
• <b>Krishna ka updesha:</b> [Hinglish — Krishna kehte hain — <b>karma</b> pe focus rakh, <b>phal</b> pe nahi. Tab stress <b>khatam</b> hoga]
• <b>Depression se bachna:</b> [Hinglish — jab lage sab kuch khatam ho raha hai, tab <b>dharam</b> yaad rakho. Arjuna ne bhi <b>vishad</b> (depression) mein tha, Krishna ne <b>Gita</b> di]
• <b>Anxiety se bachna:</b> [Hinglish — <b>future</b> ki chinta anxiety deti hai. Krishna kehte hain — <b>vartaman</b> mein jiyo, <b>aaj</b> ka karma karo]
• <b>Andar se disturb na hona:</b> [Hinglish — bahar koi bhi situation ho, <b>andar shant</b> raho. Hanuman ji hamesha <b>shant</b> the, chahe koi bhi situation ho]
• <b>Gita ka solution:</b> [Hinglish — is verse ka <b>core message</b> — stress, depression, anxiety se bachne ke liye Gita kya kehti hai. <b>Bold</b> mein important words]
• <b>3 Lords ki seekh:</b> [Hinglish — Krishna, Rama, Hanuman ji apne jivan mein stress/depression kaise handle karte the. Unka <b>real example</b>]

🧘 <b>INNER PEACE — HOW TO AVOID STRESS, DEPRESSION &amp; ANXIETY (ENGLISH)</b>
<i>From this Gita verse — Krishna teaches you</i>

• <b>Why stress comes:</b> [English — in this verse's context. Stress comes when we focus on <b>results</b>, not on <b>action</b>]
• <b>Krishna's teaching:</b> [English — Krishna says — focus on <b>karma</b>, not on <b>phal</b>. Then stress <b>ends</b>]
• <b>Avoiding depression:</b> [English — when everything feels ending, remember <b>dharma</b>. Arjuna was also in <b>depression</b>, Krishna gave him <b>Gita</b>]
• <b>Avoiding anxiety:</b> [English — worrying about <b>future</b> causes anxiety. Krishna says — live in the <b>present</b>, do today's karma]
• <b>Staying undisturbed inside:</b> [English — whatever the external situation, stay <b>calm inside</b>. Hanuman ji was always <b>peaceful</b>, no matter the situation]
• <b>Gita's solution:</b> [English — <b>core message</b> of this verse for avoiding stress, depression, anxiety. <b>Bold</b> important words]
• <b>3 Lords' teachings:</b> [English — how Krishna, Rama, Hanuman ji handled stress/depression in their lives. Their <b>real example</b>]

🧠 <b>BUDDHI, BAAL AUR TEEZ DIMMAG — HANUMAN JI STYLE (HINGLISH)</b>
• <b>Jo chaal chale, wahi chaal se harao:</b> [Is verse ke context mein — Hinglish. Hanuman ji ka principle]
• <b>Jo buddhi se aaye, buddhi ka upyog karo:</b> [Hinglish — verse se connect]
• <b>Jo baal se aaye, baal ka upyog karo:</b> [Hinglish — verse se connect]
• <b>Hanuman ji doha:</b> "Jo chaal kara woh chaal se haaraya, jo buddhi hai usse buddhi ka upyog karo, jaa baal wah baal ka upyog karo"
• <b>Dharam ke liye lagao:</b> [Is verse mein kaise apply karein — Hinglish]
• <b>Aaj ke time mein practical application:</b> [Modern scenario — Hinglish]

🧠 <b>WISDOM, STRENGTH &amp; SHARP MIND — HANUMAN JI STYLE (ENGLISH)</b>
• <b>Counter their strategy with strategy:</b> [In this verse's context — English. Hanuman ji's principle]
• <b>Counter wisdom with wisdom:</b> [English — connect to verse]
• <b>Counter strength with strength:</b> [English — connect to verse]
• <b>Hanuman ji's principle:</b> "Defeat their strategy with strategy, use wisdom against wisdom, use strength against strength"
• <b>Apply for dharma:</b> [How to apply in this verse — English]
• <b>Practical application today:</b> [Modern scenario — English]

🎯 <b>DISTRACTION KO PAAR KARNA — HANUMAN JI JAISA (HINGLISH)</b>
• <b>Dharam ke raste mein kya distraction aate hain:</b> [Hinglish — is verse ke context mein]
• <b>Hanuman ji kaise paar karte the:</b> [Hanuman ji ki real story se example — Hinglish]
• <b>Tum kaise paar karo:</b> [Practical step — Hinglish]
• <b>Purpose pe focus rakhna:</b> [Manjil ko pura karne ke liye, distraction pe nahi — Hinglish]
• <b>Verse se connection:</b> [Is verse mein distraction paar karne ka kya sandesh hai — Hinglish]

🎯 <b>OVERCOMING DISTRACTION — HANUMAN JI STYLE (ENGLISH)</b>
• <b>What distractions come on the path of dharma:</b> [English — in this verse's context]
• <b>How Hanuman ji overcame them:</b> [Example from Hanuman ji's real story — English]
• <b>How you can overcome:</b> [Practical step — English]
• <b>Focus on purpose:</b> [Stay focused on the goal, not on distractions — English]
• <b>Connection to verse:</b> [What this verse says about overcoming distraction — English]

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
• <b>Krishna says:</b> "Hanuman, is verse ka arth ye hai..." [Krishna explains the verse — in HINGLISH]
• <b>Hanuman asks:</b> "Prabhu, main isse apne jivan mein kaise lagaoon? Kaliyug mein adharmi logo se kaise deal karoon? Jo hasate hain, chidhate hain, gali dete hain, ulta bolte hain — unse kaise bachoon? Stress, depression, anxiety andar na aaye tab kaise?" [In HINGLISH]
• <b>Krishna answers:</b> [Practical answer — buddhi, baal, teez dimmag ka upyog, distraction paar karna, hasne walo ko ignor, chidhane walo pe no reaction, <b>calm</b> raho, <b>fearless</b> raho, <b>ant shant</b> raho, stress/depression/anxiety se bachne ke liye Gita ka solution — in HINGLISH]
• <b>Rama adds:</b> "Hanuman, ye bhi yaad rakh..." [One more insight about staying on dharma jab puri duniya against ho — in HINGLISH]

🕉️ <b>KRISHNA TEACHES HANUMAN &amp; RAMA (ENGLISH)</b>
• <b>Krishna says:</b> "Hanuman, the meaning of this verse is..." [Same explanation — in ENGLISH]
• <b>Hanuman asks:</b> "Lord, how can I apply this in my life? How to deal with adharmic people in Kaliyug? Those who laugh, provoke, abuse, speak contradictions — how to handle them? How to keep stress, depression, anxiety away?" [In ENGLISH]
• <b>Krishna answers:</b> [Practical answer — wisdom, strength, sharp mind, overcoming distraction, ignoring mockers, no reaction to provokers, stay <b>calm</b>, <b>fearless</b>, <b>inner peace</b>, Gita's solution for stress/depression/anxiety — in ENGLISH]
• <b>Rama adds:</b> "Hanuman, also remember..." [Same insight about staying on dharma when the whole world is against you — in ENGLISH]

🎯 <b>TODAY'S SADHANA (HINGLISH)</b>
• Krishna ki tarah socho: [aaj ka practical step — HINGLISH]
• Rama ki tarah karo: [aaj ka practical step — HINGLISH]
• Hanuman ki tarah seva karo: [aaj ka practical step — HINGLISH]

🎯 <b>TODAY'S SADHANA (ENGLISH)</b>
• Think like Krishna: [same practical step — ENGLISH]
• Act like Rama: [same practical step — ENGLISH]
• Serve like Hanuman: [same practical step — ENGLISH]

🧠 <b>REMEMBER (HINGLISH)</b>
"[Short inspiring quote in HINGLISH — 1 line about verse + Kaliyug dealing]"

🧠 <b>REMEMBER (ENGLISH)</b>
"[Same inspiring quote in ENGLISH — 1 line about verse + Kaliyug dealing]"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 Agent RK — Your Spiritual Guide
<i>For questions, just reply here</i>

CRITICAL RULES:
- EVERY section must appear in BOTH Hinglish AND English — no exceptions
- VERSE ELABORATION: Break the verse into 2-3 parts and explain EACH part separately. <b>Highlight</b> important words and key sentences with bold tags. This is the most important section — explain properly, not superficially.
- KALIYUG SECTION: Must be based on the DAILY VERSE's teaching. Cover ALL these people types: (1) gali dene wale/verbal abusers, (2) direct chedne wale/harassers, (3) indirect chidhane wale/taunters, (4) hasne wale/mockers who laugh at your dharma path, (5) ulta-sulta bolne wale/contradictory speakers, (6) gali dekh ke harkat karne wale/gesture provokers, (7) raste se jaate hue chedna/passing-by teasers, (8) chalak log who pull others down, (9) manipulators who misuse intelligence, (10) dharam rokné wale — even if PURA DUNIYA is against you. For EACH type: give Gita-based solution from today's verse. Krishna/Rama/Hanuman ji as guru teaching how to deal. Calm, fearless, dharma-focused approach.
- ANTAR SHANTI / INNER PEACE SECTION: How to keep stress, depression, anxiety away. Based on verse — Krishna's teaching about karma vs phal, living in present, inner peace. How 3 Lords handled stress in their lives. Gita has ALL solutions.
- BUDDHI/BAAL SECTION: Hanuman ji's principle — jo chaal chale wahi chaal se harao, jo buddhi se aaye buddhi se, jo baal se aaye baal se. Apply this to the verse's context. How to use wisdom AND strength for dharma.
- DISTRACTION SECTION: What distractions come on the dharam path (based on verse), how Hanuman ji overcame them (real story), how reader can overcome. Focus on PURPOSE not distraction.
- KRISHNA TEACHES section: Hanuman specifically asks about dealing with adharmic people in Kaliyug (hasne wale, chidhane wale, gali dene wale, ulta bolne wale) AND keeping stress/depression/anxiety away. Krishna's answer must include buddhi/baal/teez dimmag + distraction + calm/fearless/inner peace + Gita solution. Rama adds about standing for dharma when puri duniya is against you.
- Keep each language version point-wise — bullet points
- Simple language — as if explaining to a 15 year old
- REAL situations from Krishna, Rama, and Hanuman's actual lives (from scriptures) — not generic advice
- Use HTML tags: <b>bold</b>, <i>italic</i>, <code>code</code> for formatting
- Do NOT use Markdown (*, _, `) — only HTML tags
- Escape &amp; as &amp;amp;, < as &amp;lt;, > as &amp;gt; in text content (but keep HTML tags intact)
- Keep the EXACT format above with all emojis and separators
- IMPORTANT words and sentences MUST be <b>highlighted</b> with bold tags throughout
- The entire message should be 4000-7000 characters (it's longer because of bilingual + expanded Kaliyug + antar shanti + verse elaboration)
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
    max_tokens = 6000  # expanded Kaliyug (10 types) + antar shanti + verse elaboration = needs more tokens
    
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
        
        provider_max = 6000  # bilingual lessons need more tokens (expanded Kaliyug + antar shanti)
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

📖 <b>VERSE ELABORATION — TODA-TODA SAMJHO (HINGLISH)</b>
• <b>Pehla hissa:</b> "Karma" — tumhara kaam sirf karna hai. <b>Phal</b> Bhagwan ke haath mein hai.
• <b>Doosra hissa:</b> "Phal ki chinta" — result ka tension mat lo. Tumhara kaam sirf effort dena hai.
• <b>Sabse zaroori sentence:</b> "<b>Karma kar, phal ki chinta mat kar</b>"
• <b>Deep arth:</b> Insan ka kaam sirf apna dharam nibhana hai. Result par tumhara control nahi hai, sirf effort par hai. <b>Mukti</b> isi mein hai.
• <b>Krishna ka updesha:</b> Krishna kehte hain — Arjuna, tu yuddh kar, result mere bharose chhod.

📖 <b>VERSE ELABORATION — PART BY PART EXPLANATION (ENGLISH)</b>
• <b>First part:</b> "Karma" — your job is only to act. <b>Results</b> are in God's hands.
• <b>Second part:</b> "Worry about results" — don't stress over outcomes. Your job is only to make effort.
• <b>Key sentence:</b> "<b>Do your duty, do not worry about results</b>"
• <b>Deep meaning:</b> A person's job is only to fulfill their dharma. You cannot control results, only effort. <b>Liberation</b> lies in this understanding.
• <b>Krishna's teaching:</b> Krishna says — Arjuna, fight the battle, leave the result to me.

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

⚔️ <b>KALIYUG MEIN ADHARMI LOGO SE KAISE DEAL KAREIN (HINGLISH)</b>
<i>Krishna, Rama aur Hanuman ji ki seekh — Gita se solution</i>

• <b>Gali dene wale:</b> <b>Ignor</b> karo. Unka gali tumhara karma nahi hai. Tum apna kaam karte raho, unka reaction unka karma hai.
• <b>Direct chedne wale:</b> <b>Dhairya</b> rakho, lekin zaroorat ho toh <b>boundaries</b> set karo. Hanuman ji bhi bina kaaran nahi ladte the.
• <b>Indirect chidhane wale (taunters):</b> Unki baaton pe <b>reaction</b> mat do. Krishna ne Kans ke threats ko bhi <b>ignor</b> kiya tha. <b>Vairagya</b> se kaam lo.
• <b>Hasne wale (mockers):</b> Tum dharam par chal rahe ho aur log <b>hasate</b> hain. Krishna ko bhi hasaya gaya tha. Unka hasna unki samajh ki kami hai. <b>Tumhara marg tumhara hai</b>.
• <b>Ulta-sulta bolne wale:</b> <b>Buddhi</b> se unki baat ko pehchano. Krishna kehte hain — <b>vivek</b> se sach ko alag karo. Unki baaton mein mat phanso.
• <b>Gali dekh ke harkat karne wale:</b> <b>Aankh neeche mat jhukao</b>. Hanuman ji jaisa <b>fearless</b> raho. Unki harkat unki gireez hai.
• <b>Raste se jaate hue chedna:</b> <b>Aage badho</b> — peeche mat dekho. Rama ne <b>vanvas</b> mein bahut logo ka apmaan sehka, bina ruke aage badhe.
• <b>Chalak log (pair khichne wale):</b> Unse <b>door</b> raho. Apna kaam <b>karma</b> se karo — unki chaal unki problem hai.
• <b>Manipulators:</b> <b>Buddhi</b> ka upyog karo. Hanuman ji jaise — unki buddhi ko apni <b>buddhi</b> se pehchano.
• <b>Dharam rokné wale (pura duniya against ho):</b> Jab <b>puri duniya</b> against ho, tab bhi <b>dharam</b> ke liye khade raho. Arjuna ne puri sena dekhi, darr laga, phir bhi Krishna kehte hain — <b>khade raho</b>. Rama ne <b>Kaikeyi</b> ke aage bhi dharma nahi chhoda.
• <b>Aage kaise badho:</b> Apne <b>purpose</b> par focus rakho. <b>Fearless</b> raho, <b>karma</b> karte raho, result Bhagwan par chhod do.

⚔️ <b>DEALING WITH ADHARMIC PEOPLE IN KALIYUG (ENGLISH)</b>
<i>Based on teachings of Krishna, Rama and Hanuman ji — Gita solution</i>

• <b>Verbal abusers:</b> <b>Ignore</b> them. Their abuse is their karma, not yours. Keep doing your work.
• <b>Direct harassers:</b> Maintain <b>patience</b>, but set <b>boundaries</b> when needed. Even Hanuman ji didn't fight without reason.
• <b>Indirect taunters:</b> Don't <b>react</b> to their indirect taunts. Krishna ignored Kans's threats too. Use <b>detachment</b>.
• <b>Mockers (those who laugh at you):</b> You walk on dharma and people <b>laugh</b>. Krishna was laughed at too. Their laughter shows their ignorance. <b>Your path is yours</b>.
• <b>Contradictory speakers:</b> Use <b>wisdom</b> to identify truth. Krishna says — use <b>discrimination</b> to separate truth from lies. Don't get trapped.
• <b>Gesture provokers:</b> <b>Don't lower your eyes</b>. Be <b>fearless</b> like Hanuman ji. Their gestures show their downfall.
• <b>Passing-by teasers:</b> <b>Move forward</b> — don't look back. Rama faced many insults in <b>exile</b>, yet moved forward without stopping.
• <b>Cunning people who step on others:</b> Stay <b>away</b> from them. Do your work through <b>karma</b> — their tricks are their problem.
• <b>Manipulators:</b> Use your <b>wisdom</b>. Like Hanuman ji — recognize their intelligence with your intelligence.
• <b>Those who block dharma (even if the whole world is against you):</b> When <b>the whole world</b> is against you, still <b>stand for dharma</b>. Arjuna saw the entire army, was afraid, yet Krishna says — <b>stand firm</b>. Rama didn't abandon dharma even before <b>Kaikeyi</b>.
• <b>How to move forward:</b> Focus on your <b>purpose</b>. Stay <b>fearless</b>, keep doing <b>karma</b>, surrender results to God.

🧘 <b>ANTAR SHANTI — STRESS, DEPRESSION, ANXIETY SE KAISE BACHEIN (HINGLISH)</b>
<i>Gita se — Krishna tumhe sikhate hain</i>

• <b>Stress kyon aata hai:</b> Stress tab aata hai jab hum <b>phal</b> ke baare mein sochte hain, <b>karma</b> chhod kar.
• <b>Krishna ka updesha:</b> <b>Karma</b> pe focus rakh, <b>phal</b> pe nahi. Tab stress <b>khatam</b> hoga.
• <b>Depression se bachna:</b> Jab lage sab kuch khatam ho raha hai, tab <b>dharam</b> yaad rakho. Arjuna ne bhi <b>vishad</b> (depression) mein tha, Krishna ne <b>Gita</b> di.
• <b>Anxiety se bachna:</b> <b>Future</b> ki chinta anxiety deti hai. Krishna kehte hain — <b>vartaman</b> mein jiyo, <b>aaj</b> ka karma karo.
• <b>Andar se disturb na hona:</b> Bahar koi bhi situation ho, <b>andar shant</b> raho. Hanuman ji hamesha <b>shant</b> the, chahe koi bhi situation ho.
• <b>Gita ka solution:</b> <b>Karma kar, phal ki chinta mat kar</b> — yahi stress, depression, anxiety ka solution hai. Gita ke paas <b>SAB solutions</b> hain.
• <b>3 Lords ki seekh:</b> Krishna ne Kurukshetra mein calm raho, Rama ne vanvaas mein acceptance, Hanuman ji ne Lanka mein fearlessness — sab ne stress bina handle kiya.

🧘 <b>INNER PEACE — HOW TO AVOID STRESS, DEPRESSION &amp; ANXIETY (ENGLISH)</b>
<i>From Gita — Krishna teaches you</i>

• <b>Why stress comes:</b> Stress comes when we focus on <b>results</b>, not on <b>action</b>.
• <b>Krishna's teaching:</b> Focus on <b>karma</b>, not on <b>phal</b>. Then stress <b>ends</b>.
• <b>Avoiding depression:</b> When everything feels ending, remember <b>dharma</b>. Arjuna was also in <b>depression</b>, Krishna gave him <b>Gita</b>.
• <b>Avoiding anxiety:</b> Worrying about <b>future</b> causes anxiety. Krishna says — live in the <b>present</b>, do today's karma.
• <b>Staying undisturbed inside:</b> Whatever the external situation, stay <b>calm inside</b>. Hanuman ji was always <b>peaceful</b>, no matter the situation.
• <b>Gita's solution:</b> <b>Do your duty, don't worry about results</b> — this is the solution for stress, depression, anxiety. Gita has <b>ALL solutions</b>.
• <b>3 Lords' teachings:</b> Krishna stayed calm at Kurukshetra, Rama accepted exile, Hanuman ji was fearless in Lanka — all handled stress with inner peace.

🧠 <b>BUDDHI, BAAL AUR TEEZ DIMMAG — HANUMAN JI STYLE (HINGLISH)</b>
• <b>Jo chaal chale, wahi chaal se harao:</b> Manipulator jo chaal chalega, usi chaal ko pehchankar usse harao.
• <b>Jo buddhi se aaye, buddhi ka upyog karo:</b> Chalak logo ko <b>buddhi</b> se jawab do, gusse se nahi.
• <b>Jo baal se aaye, baal ka upyog karo:</b> Jab koi <b>baal</b> use kare, tab <b>dhairya</b> aur <b>strength</b> dono rakho.
• <b>Hanuman ji doha:</b> "Jo chaal kara woh chaal se haaraya, jo buddhi hai usse buddhi ka upyog karo, jaa baal wah baal ka upyog karo"
• <b>Dharam ke liye lagao:</b> Is verse mein <b>karma</b> bina phal ki chinta — yeh tumhari sabse badi <b>buddhi</b> hai.
• <b>Practical application:</b> Office mein politics ho ya ghar mein tension — <b>karma</b> se jawab do, reaction se nahi.

🧠 <b>WISDOM, STRENGTH &amp; SHARP MIND — HANUMAN JI STYLE (ENGLISH)</b>
• <b>Counter strategy with strategy:</b> Whatever trick a manipulator uses, recognize it and counter with the same.
• <b>Counter wisdom with wisdom:</b> Answer cunning people with <b>wisdom</b>, not anger.
• <b>Counter strength with strength:</b> When someone uses <b>force</b>, hold both <b>patience</b> and <b>strength</b>.
• <b>Hanuman ji's principle:</b> "Defeat their strategy with strategy, use wisdom against wisdom, use strength against strength"
• <b>Apply for dharma:</b> In this verse, <b>karma</b> without worrying about results — this is your greatest <b>wisdom</b>.
• <b>Practical application:</b> Office politics or family tension — respond with <b>karma</b>, not reaction.

🎯 <b>DISTRACTION KO PAAR KARNA — HANUMAN JI JAISA (HINGLISH)</b>
• <b>Dharam ke raste mein kya distraction aate hain:</b> Logon ki baatein, result ki chinta, lalach, gussa — ye sab <b>distraction</b> hai.
• <b>Hanuman ji kaise paar karte the:</b> Lanka mein <b>Surasa</b> ne roka, <b>Mainaka</b> parvat ne aaram diya — Hanuman ji sab paar kiye, <b>Ram</b> ka naam yaad rakhte hue.
• <b>Tum kaise paar karo:</b> <b>Manjil</b> yaad rakho, <b>distraction</b> pe dhyan nahi. Apne <b>purpose</b> se judo.
• <b>Purpose pe focus:</b> Hanuman ji ka <b>purpose</b> Sita mata ko dhoondhna tha. Tumhara <b>purpose</b> tumhara dharam hai.
• <b>Verse se connection:</b> Krishna keh rahe hain — <b>karma</b> pe focus rakh, <b>phal</b> pe nahi. Yahi distraction paar karne ka tarika hai.

🎯 <b>OVERCOMING DISTRACTION — HANUMAN JI STYLE (ENGLISH)</b>
• <b>What distractions come:</b> People's words, worrying about results, greed, anger — all are <b>distractions</b>.
• <b>How Hanuman ji overcame:</b> In Lanka, <b>Surasa</b> tried to stop him, <b>Mainaka</b> mountain offered rest — Hanuman ji passed all, keeping <b>Ram's</b> name in heart.
• <b>How you can overcome:</b> Remember your <b>goal</b>, don't focus on <b>distractions</b>. Connect to your <b>purpose</b>.
• <b>Focus on purpose:</b> Hanuman ji's <b>purpose</b> was finding Sita mata. Your <b>purpose</b> is your dharma.
• <b>Connection to verse:</b> Krishna says — focus on <b>karma</b>, not on <b>results</b>. This is how you overcome distraction.

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
• <b>Hanuman asks:</b> "Prabhu, main result bilkul na sochun toh motivation kahan se aaye? Kaliyug mein adharmi logo se kaise deal karoon? Jo hasate hain, chidhate hain, gali dete hain, ulta bolte hain — unse kaise bachoon? Stress, depression, anxiety andar na aaye tab kaise?"
• <b>Krishna answers:</b> "Motivation result se nahi, <b>SEVA</b> se aati hai. Tum mera naam leke udi the — wahi karo. Adharmi logo se <b>buddhi</b> se deal karo, <b>baal</b> se nahi. Jo chaal chale, wahi chaal se harao. Hasne walo ko <b>ignor</b> karo, chidhane walo pe <b>no reaction</b>. <b>Calm</b> raho, <b>fearless</b> raho, <b>antar shant</b> raho. Gita ke paas <b>sab solutions</b> hain."
• <b>Rama adds:</b> "Hanuman, dharma ka kaam apna reward hota hai. Jab <b>puri duniya</b> against ho, tab bhi <b>dharam</b> ke liye khade raho. <b>Distraction</b> aaye toh <b>purpose</b> yaad rakhna."

🕉️ <b>KRISHNA TEACHES HANUMAN &amp; RAMA (ENGLISH)</b>
• <b>Krishna says:</b> "Hanuman, the meaning of this verse is — do your duty, don't think of results. You did the same in Lanka."
• <b>Hanuman asks:</b> "Lord, if I don't think of results at all, where will motivation come from? How to deal with adharmic people in Kaliyug? Those who laugh, provoke, abuse, speak contradictions — how to handle them? How to keep stress, depression, anxiety away?"
• <b>Krishna answers:</b> "Motivation comes from <b>SERVICE</b>, not results. You flew in my name — do the same. Deal with adharmic people using <b>wisdom</b>, not force. Counter their strategy with strategy. <b>Ignore</b> mockers, <b>no reaction</b> to provokers. Stay <b>calm</b>, <b>fearless</b>, <b>inner peace</b>. Gita has <b>ALL solutions</b>."
• <b>Rama adds:</b> "Hanuman, the act of dharma is its own reward. When <b>the whole world</b> is against you, still <b>stand for dharma</b>. When <b>distractions</b> come, remember your <b>purpose</b>."

🎯 <b>TODAY'S SADHANA (HINGLISH)</b>
• Krishna ki tarah socho: Aaj ek decision bina result ke chinta lo
• Rama ki tarah karo: Jo difficult hai us accept karke kar do
• Hanuman ki tarah seva karo: Kisi ki bina expectation madad karo

🎯 <b>TODAY'S SADHANA (ENGLISH)</b>
• Think like Krishna: Make one decision today without worrying about the result
• Act like Rama: Accept what is difficult and do it
• Serve like Hanuman: Help someone without any expectation

🧠 <b>REMEMBER (HINGLISH)</b>
"Karma kar, phal ki chinta mat kar. Kaliyug mein <b>buddhi</b> se deal karo, <b>dharam</b> se raho, <b>distraction</b> ko paar karo — Hanuman ji jaisa. Hasne walo ko ignor, chidhane walo pe no reaction. <b>Calm</b>, <b>fearless</b>, <b>antar shant</b> raho. Gita ke paas <b>sab solutions</b> hain."

🧠 <b>REMEMBER (ENGLISH)</b>
"Do your duty, don't worry about results. In Kaliyug, deal with <b>wisdom</b>, stay on <b>dharma</b>, overcome <b>distractions</b> — like Hanuman ji. Ignore mockers, no reaction to provokers. Stay <b>calm</b>, <b>fearless</b>, <b>inner peace</b>. Gita has <b>ALL solutions</b>."

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