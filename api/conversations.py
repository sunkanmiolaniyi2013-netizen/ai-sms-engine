"""
api/conversations.py — Conversation viewer endpoints
"""
from fastapi import APIRouter, HTTPException
from database import db

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
def list_conversations(business_id: str, limit: int = 50):
    conversations = db.list_conversations(business_id, limit=limit)
    return {"conversations": conversations}


@router.get("/{conversation_id}/messages")
def get_messages(conversation_id: str):
    messages = db.get_messages_for_viewer(conversation_id)
    return {"messages": messages}


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str):
    db.delete_conversation(conversation_id)
    return {"status": "deleted"}
