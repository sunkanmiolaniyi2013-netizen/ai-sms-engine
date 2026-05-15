"""
database/db.py — Supabase client & CRUD helpers
"""
import os
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Optional[Client] = None


def get_db() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        _client = create_client(url, key)
    return _client


# ─────────────────────────────────────────
# Business helpers
# ─────────────────────────────────────────

def get_business_by_location(location_id: str) -> Optional[dict]:
    db = get_db()
    res = db.table("businesses").select("*").eq("ghl_location_id", location_id).eq("is_active", True).single().execute()
    return res.data if res.data else None

def get_campaign_by_id(campaign_id: str) -> Optional[dict]:
    db = get_db()
    res = db.table("campaigns").select("*").eq("id", campaign_id).eq("is_active", True).single().execute()
    return res.data if res.data else None


def get_business(business_id: str) -> Optional[dict]:
    db = get_db()
    res = db.table("businesses").select("*").eq("id", business_id).single().execute()
    return res.data if res.data else None


def list_businesses() -> list:
    db = get_db()
    res = db.table("businesses").select("*").order("created_at", desc=True).execute()
    return res.data or []


def create_business(data: dict) -> dict:
    db = get_db()
    res = db.table("businesses").insert(data).execute()
    return res.data[0]


def update_business(business_id: str, data: dict) -> dict:
    db = get_db()
    res = db.table("businesses").update(data).eq("id", business_id).execute()
    return res.data[0]


def delete_business(business_id: str):
    db = get_db()
    db.table("businesses").delete().eq("id", business_id).execute()


def delete_conversation(conversation_id: str):
    db = get_db()
    # Delete messages first to satisfy any potential foreign key constraints
    db.table("messages").delete().eq("conversation_id", conversation_id).execute()
    db.table("conversations").delete().eq("id", conversation_id).execute()


# ─────────────────────────────────────────
# Contact helpers
# ─────────────────────────────────────────

def get_or_create_contact(business_id: str, ghl_contact_id: str, phone: str = None, name: str = None) -> dict:
    db = get_db()
    res = db.table("contacts").select("*").eq("business_id", business_id).eq("ghl_contact_id", ghl_contact_id).execute()
    if res.data:
        return res.data[0]
    # Create new contact
    new_contact = {
        "business_id": business_id,
        "ghl_contact_id": ghl_contact_id,
        "phone": phone,
        "name": name,
    }
    res = db.table("contacts").insert(new_contact).execute()
    return res.data[0]


def update_contact_cache(contact_id: str, website_context: str):
    db = get_db()
    from datetime import datetime, timezone
    db.table("contacts").update({
        "website_context": website_context,
        "website_cached_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", contact_id).execute()


# ─────────────────────────────────────────
# Conversation helpers
# ─────────────────────────────────────────

def get_or_create_conversation(business_id: str, contact_id: str, ghl_contact_id: str) -> dict:
    db = get_db()
    res = db.table("conversations").select("*").eq("business_id", business_id).eq("ghl_contact_id", ghl_contact_id).execute()
    if res.data:
        return res.data[0]
    new_conv = {
        "business_id": business_id,
        "contact_id": contact_id,
        "ghl_contact_id": ghl_contact_id,
    }
    res = db.table("conversations").insert(new_conv).execute()
    return res.data[0]


def list_conversations(business_id: str, limit: int = 50) -> list:
    db = get_db()
    res = (db.table("conversations")
           .select("*, contacts(name, phone)")
           .eq("business_id", business_id)
           .order("last_message_at", desc=True)
           .limit(limit)
           .execute())
    return res.data or []


def update_conversation_meta(conversation_id: str):
    """Bump message count and last_message_at."""
    db = get_db()
    from datetime import datetime, timezone
    db.table("conversations").update({
        "last_message_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", conversation_id).execute()
    db.rpc("increment_message_count", {"conv_id": conversation_id}).execute()


# ─────────────────────────────────────────
# Message helpers
# ─────────────────────────────────────────

def save_message(conversation_id: str, business_id: str, role: str, content: str) -> dict:
    db = get_db()
    from datetime import datetime, timezone
    msg = {
        "conversation_id": conversation_id,
        "business_id": business_id,
        "role": role,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    res = db.table("messages").insert(msg).execute()
    # Update conversation metadata
    db.table("conversations").update({
        "last_message_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", conversation_id).execute()
    return res.data[0]


def get_conversation_history(conversation_id: str, limit: int = 20) -> list:
    """Returns last N messages ordered oldest→newest for AI context."""
    db = get_db()
    res = (db.table("messages")
           .select("role, content, created_at")
           .eq("conversation_id", conversation_id)
           .order("created_at", desc=True)
           .limit(limit)
           .execute())
    messages = res.data or []
    return list(reversed(messages))


def get_messages_for_viewer(conversation_id: str) -> list:
    db = get_db()
    res = (db.table("messages")
           .select("*")
           .eq("conversation_id", conversation_id)
           .order("created_at")
           .execute())
    return res.data or []


# ─────────────────────────────────────────
# Stats helpers
# ─────────────────────────────────────────

def get_stats(business_id: str) -> dict:
    db = get_db()
    conv_res = db.table("conversations").select("id", count="exact").eq("business_id", business_id).execute()
    msg_res = db.table("messages").select("id", count="exact").eq("business_id", business_id).execute()
    ai_msg_res = (db.table("messages").select("id", count="exact")
                  .eq("business_id", business_id).eq("role", "assistant").execute())
    return {
        "total_conversations": conv_res.count or 0,
        "total_messages": msg_res.count or 0,
        "ai_replies_sent": ai_msg_res.count or 0,
    }
