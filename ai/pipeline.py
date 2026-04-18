"""
ai/pipeline.py — Core AI reply orchestrator
Ties together: context fetching, conversation history, Gemini, and GHL send
"""
import logging
import asyncio
from typing import Optional
from database import db
from ai.gemini import generate_reply
from ai.context import get_or_refresh_website_context
from ghl.client import send_sms

logger = logging.getLogger(__name__)


async def process_inbound_message(
    location_id: str,
    ghl_contact_id: str,
    message_body: str,
    contact_name: Optional[str] = None,
    contact_phone: Optional[str] = None,
    campaign_id: Optional[str] = None,
) -> Optional[str]:
    """
    Full pipeline:
    1. Resolve business from location_id
    2. Get/create contact + conversation
    3. Load conversation history
    4. Fetch website context (cached)
    5. Generate AI reply
    6. Save messages to DB
    7. Return reply text (caller handles delay + GHL send)
    """
    # 1. Resolve business
    business = db.get_business_by_location(location_id)
    if not business:
        logger.warning(f"No active business found for location_id={location_id}")
        return None

    business_id = business["id"]

    # 2. Get or create contact
    contact = db.get_or_create_contact(
        business_id=business_id,
        ghl_contact_id=ghl_contact_id,
        phone=contact_phone,
        name=contact_name,
    )

    # 3. Get or create conversation
    conversation = db.get_or_create_conversation(
        business_id=business_id,
        contact_id=contact["id"],
        ghl_contact_id=ghl_contact_id,
    )

    # 4. Save inbound message
    db.save_message(
        conversation_id=conversation["id"],
        business_id=business_id,
        role="user",
        content=message_body,
    )

    # 5. Load conversation history (last 20 messages for context)
    history = db.get_conversation_history(conversation["id"], limit=20)

    # 6. Fetch website context if given
    website_context = None
    if business.get("website_url"):
        website_context = await get_or_refresh_website_context(contact, business["website_url"])

    ai_prompt_override = business["ai_prompt"]
    calendar_link_override = business.get("calendar_link")
    pricing_info_override = business.get("pricing_info")
    outreach_message_override = business.get("outreach_message")
    
    if campaign_id:
        campaign = db.get_campaign_by_id(campaign_id)
        if campaign:
            ai_prompt_override = campaign.get("ai_prompt") or ai_prompt_override
            calendar_link_override = campaign.get("calendar_link") or calendar_link_override
            pricing_info_override = campaign.get("pricing_info") or pricing_info_override
            outreach_message_override = campaign.get("outreach_message") or outreach_message_override
            if campaign.get("ghl_calendar_id"):
                business["ghl_calendar_id"] = campaign.get("ghl_calendar_id")

    # 7. Generate AI reply
    reply = await generate_reply(
        business_prompt=ai_prompt_override,
        conversation_history=history,
        user_message=message_body,
        website_context=website_context,
        calendar_link=calendar_link_override,
        pricing_info=pricing_info_override,
        outreach_message=outreach_message_override,
        model_name=business.get("ai_model", "gemini-2.5-pro"),
        business=business, 
        contact_id=contact["ghl_contact_id"],
    )

    if not reply:
        logger.error("AI returned empty reply — skipping send")
        return None

    # 8. Save AI reply to DB
    db.save_message(
        conversation_id=conversation["id"],
        business_id=business_id,
        role="assistant",
        content=reply,
    )

    logger.info(f"Pipeline complete for contact {ghl_contact_id}. Reply: {reply[:80]}...")
    return reply


async def send_delayed_reply(
    location_id: str,
    ghl_contact_id: str,
    reply: str,
    business_id: str,
    phone: Optional[str] = None,
):
    """Just sends the GHL message — called after delay fires."""
    success = await send_sms(
        location_id=location_id,
        contact_id=ghl_contact_id,
        message=reply,
        business_id=business_id,
        phone=phone,
    )
    if not success:
        logger.error(f"Failed to send SMS to {ghl_contact_id}")
