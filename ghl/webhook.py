"""
ghl/webhook.py — Inbound SMS webhook handler
GHL sends a POST here when a contact replies to an SMS
"""
import logging
from fastapi import APIRouter, Request, BackgroundTasks
from typing import Optional
from ai.pipeline import process_inbound_message, send_delayed_reply
from task_queue.scheduler import schedule_reply
from database.db import get_business_by_location

logger = logging.getLogger(__name__)
router = APIRouter()


def _extract_message(raw) -> str:
    """Handle both string and dict message formats from GHL."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return raw.get("body") or raw.get("message") or raw.get("text") or ""
    return ""


@router.post("/webhook/inbound")
async def inbound_sms(request: Request, background_tasks: BackgroundTasks, campaign_id: Optional[str] = None):
    """
    Receives inbound SMS reply from GHL.
    Reads from customData first (our explicit fields), then falls back to
    native GHL payload fields.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    logger.info(f"Raw GHL payload keys: {list(body.keys())}")

    # GHL puts our custom key-value pairs inside "customData"
    custom = body.get("customData") or {}

    # ── Extract location_id ──────────────────────────────────
    location_id = (
        custom.get("location_id") or                          # our custom field
        body.get("location_id") or                            # top-level
        (body.get("location") or {}).get("id") or             # nested location object
        ""
    )

    # ── Extract contact_id ──────────────────────────────────
    contact_id = (
        custom.get("contact_id") or
        body.get("contact_id") or
        body.get("contactId") or
        ""
    )

    # ── Extract message body ─────────────────────────────────
    # GHL native message is a dict: {"type": 2, "body": "..."}
    # Our customData message is a plain string
    raw_msg = custom.get("message") or body.get("message")
    message_body = _extract_message(raw_msg)

    # ── Extract contact name & phone ─────────────────────────
    contact_name = (
        custom.get("name") or
        body.get("full_name") or
        body.get("fullName") or
        f"{body.get('first_name', '')} {body.get('last_name', '')}".strip() or
        None
    )
    contact_phone = (
        custom.get("phone") or
        body.get("phone") or
        body.get("phoneNumber") or
        None
    )

    # ── Log what we extracted ────────────────────────────────
    logger.info(f"Extracted → location={location_id} contact={contact_id} msg={str(message_body)[:80]} phone={contact_phone}")

    # ── Validate ─────────────────────────────────────────────
    if not location_id:
        logger.error(f"Missing location_id. customData={custom}, body keys={list(body.keys())}")
        return {"status": "error", "detail": "Missing location_id"}

    if not contact_id:
        logger.error(f"Missing contact_id. customData={custom}")
        return {"status": "error", "detail": "Missing contact_id"}

    if not message_body:
        logger.error(f"Missing message. customData={custom}, native message={body.get('message')}")
        return {"status": "error", "detail": "Missing message"}

    # ── Resolve business ──────────────────────────────────────
    business = get_business_by_location(location_id)
    if not business:
        logger.warning(f"No business found for location_id={location_id}")
        return {"status": "error", "detail": f"No business configured for location {location_id}"}

    business_id = business["id"]
    delay_min = business.get("delay_min", 60)
    delay_max = business.get("delay_max", 180)

    # ── Run pipeline in background ────────────────────────────
    background_tasks.add_task(
        _run_pipeline_and_schedule,
        location_id=location_id,
        ghl_contact_id=contact_id,
        message_body=message_body,
        contact_name=contact_name,
        contact_phone=contact_phone,
        business_id=business_id,
        delay_min=delay_min,
        delay_max=delay_max,
        campaign_id=campaign_id,
    )

    return {"status": "received", "message": "Processing started"}


async def _run_pipeline_and_schedule(
    location_id: str,
    ghl_contact_id: str,
    message_body: str,
    contact_name: Optional[str],
    contact_phone: Optional[str],
    business_id: str,
    delay_min: int,
    delay_max: int,
    campaign_id: Optional[str] = None,
):
    """Runs AI pipeline then schedules the GHL send with human delay."""
    reply = await process_inbound_message(
        location_id=location_id,
        ghl_contact_id=ghl_contact_id,
        message_body=message_body,
        contact_name=contact_name,
        contact_phone=contact_phone,
        campaign_id=campaign_id,
    )

    if reply:
        schedule_reply(
            coroutine_fn=send_delayed_reply,
            delay_min=delay_min,
            delay_max=delay_max,
            location_id=location_id,
            ghl_contact_id=ghl_contact_id,
            reply=reply,
            business_id=business_id,
            phone=contact_phone,
        )
