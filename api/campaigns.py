from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from database.db import get_db

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

class CampaignCreate(BaseModel):
    business_id: str
    name: str
    ai_prompt: str
    calendar_link: Optional[str] = None
    ghl_calendar_id: Optional[str] = None
    pricing_info: Optional[str] = None
    outreach_message: Optional[str] = None
    is_active: bool = True

class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    ai_prompt: Optional[str] = None
    calendar_link: Optional[str] = None
    ghl_calendar_id: Optional[str] = None
    pricing_info: Optional[str] = None
    outreach_message: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("")
def list_campaigns(business_id: str):
    db = get_db()
    res = db.table("campaigns").select("*").eq("business_id", business_id).order("created_at", desc=True).execute()
    return res.data or []

@router.post("")
def create_campaign(campaign: CampaignCreate):
    db = get_db()
    payload = campaign.model_dump(exclude_unset=True)
    res = db.table("campaigns").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to create campaign")
    return res.data[0]

@router.put("/{campaign_id}")
def update_campaign(campaign_id: str, campaign: CampaignUpdate):
    db = get_db()
    payload = campaign.model_dump(exclude_unset=True)
    res = db.table("campaigns").update(payload).eq("id", campaign_id).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to update campaign")
    return res.data[0]

@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: str):
    db = get_db()
    db.table("campaigns").delete().eq("id", campaign_id).execute()
    return {"message": "Deleted successfully"}
