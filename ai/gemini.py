"""
ai/gemini.py — Gemini 2.0 Flash AI integration
"""
import os
import logging
import google.generativeai as genai
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# SMS tone instructions injected into every system prompt
SMS_TONE_INSTRUCTIONS = """
IMPORTANT REPLY RULES:
- You are answering via SMS text messages. Keep replies EXTREMELY SHORT (1-2 short sentences maximum). No fluff.
- Sound like a real human — warm, casual, natural. NOT like a bot or corporate email.
- DO NOT use the prospect's name unless strictly necessary. Keep it casual.
- NO emojis unless they feel very natural for the context.
- NO long paragraphs. NO lists. NO bullet points.
- Match the energy of the person you're talking to.
- If they ask a question you can answer, answer it directly.
- CRITICAL CALENDAR RULE: Before proposing any specific times, you MUST ask the prospect what Timezone they are in (e.g. EST, PST) if it is not already apparent from the conversation context.
- When you use `check_calendar`, it will return exact ISO-8601 strings with a timezone offset (e.g. `+01:00`). This is the Calendar's physical native timezone.
- You MUST correctly convert that returned Calendar time mathematically into the Prospect's local timezone when proposing the available times in the chat (e.g. "I have 8:00 AM EST available").
- Once they agree to a specific time, YOU MUST USE YOUR TOOL (`book_appointment`) to officially book it for them. You MUST pass the EXACT original ISO string returned by your `check_calendar` search into the `book_appointment` tool! DO NOT pass your mathematically converted timezone string into the tool, only use the conversion when speaking to the prospect.
- When proposing times, ALWAYS provide exactly 3 distinct options.
- Never say you're an AI.
- Never say "I hope this message finds you well" or any robotic phrases.
- Just talk like a person texting.
"""


def _build_system_prompt(business_prompt: str, website_context: Optional[str], calendar_link: Optional[str], pricing_info: Optional[str] = None, outreach_message: Optional[str] = None) -> str:
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%A, %Y-%m-%d %H:%M:%S UTC")
    
    parts = [
        f"CURRENT SERVER TIME: {today}\nUse this as a baseline to determine 'today', 'tomorrow', 'next week', etc.\n",
    ]

    if outreach_message:
        parts.append(f"CONTEXT: This conversation started because your automated system just sent them this exact first message: '{outreach_message}'. They are replying to it.\n")

    parts.extend([business_prompt.strip(), "\n\n", SMS_TONE_INSTRUCTIONS])

    if website_context:
        parts.append(f"\n\nBUSINESS WEBSITE INFO (use only if relevant to their question):\n{website_context[:2000]}")

    if pricing_info:
        parts.append(f"\n\nPRICING GUIDELINES:\n{pricing_info}\n(Only mention these prices if explicitly asked).")
    else:
        parts.append(f"\n\nPRICING RULE: You do NOT have any general pricing information. If they ask for a price estimate, NEVER guess or hallucinate. Politely explain that you need to inspect their specific issue or discuss on a call to provide an accurate quote.")

    if calendar_link:
        parts.append(f"\n\nBACKUP CALENDAR BOOKING LINK: {calendar_link}\n(ONLY send this link if the user specifically asks to book themselves, or if the calendar database is down.)")

    return "".join(parts)


async def generate_reply(
    business_prompt: str,
    conversation_history: list,
    user_message: str,
    website_context: Optional[str] = None,
    calendar_link: Optional[str] = None,
    pricing_info: Optional[str] = None,
    outreach_message: Optional[str] = None,
    model_name: str = "gemini-2.5-pro",
    business: dict = None,
    contact_id: str = None,
) -> str:
    """
    Generate a human-like SMS reply using Gemini.
    conversation_history: list of {"role": "user"/"assistant", "content": "..."}
    """
    try:
        system_prompt = _build_system_prompt(business_prompt, website_context, calendar_link, pricing_info, outreach_message)

        # ── Map model name to actual ──
        # Force 2.5-pro as requested by user
        actual_model = "gemini-2.5-pro"

        def check_calendar(date_str: str) -> str:
            """
            Checks calendar availability for exactly ONE day.
            If the user asks for "next week", call this tool multiple times for each day.
            Args:
                date_str: The specific date in YYYY-MM-DD format (e.g., '2023-10-25').
            """
            import datetime
            from ghl.calendar import get_free_slots
            try:
                # GHL requires ms timestamps
                dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                start_ms = str(int(dt.timestamp() * 1000))
                end_dt = dt + datetime.timedelta(days=1)
                end_ms = str(int(end_dt.timestamp() * 1000))
                
                slots = get_free_slots(business, start_ms, end_ms)
                return f"RAW CALENDAR SLOTS (NOTE: These times are in the Calendar's native physical timezone offset. You MUST mentally convert these slots to the user's timezone before you text them!): {str(slots)}"
            except Exception as e:
                return f"Error connecting to calendar: {str(e)}"
                
        def book_appointment(start_time_iso: str) -> str:
            """
            Books an appointment for the lead at a specific time. 
            ONLY calling this if the user has EXPLICITLY confirmed a time.
            Args:
                start_time_iso: The precise time in ISO 8601 format (e.g., '2023-10-25T14:00:00Z').
            """
            from ghl.calendar import book_appointment as api_book
            try:
                res = api_book(business, contact_id, start_time_iso)
                return f"Successfully booked: {str(res)}"
            except Exception as e:
                return f"Error booking appointment: {str(e)}"

        try:
            model = genai.GenerativeModel(
                model_name=actual_model,
                system_instruction=system_prompt,
                tools=[check_calendar, book_appointment]
            )
        except Exception:
            # Fallback if tools aren't supported on this specific SDK version without weird wrappers
            logger.warning("Tools initialization failed. Reverting to standard chat.")
            model = genai.GenerativeModel(
                model_name=actual_model, 
                system_instruction=system_prompt
            )

        # Build chat history in Gemini format
        history = []
        for msg in conversation_history[:-1]:  # exclude the latest message
            role = "user" if msg["role"] == "user" else "model"
            history.append({
                "role": role,
                "parts": [msg["content"]]
            })

        chat = model.start_chat(history=history, enable_automatic_function_calling=True)
        response = await chat.send_message_async(user_message)
        reply = response.text.strip()

        logger.info(f"Gemini reply generated ({len(reply)} chars)")
        return reply

    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return "Hey, got your message! Give me just a moment and I'll get back to you."
