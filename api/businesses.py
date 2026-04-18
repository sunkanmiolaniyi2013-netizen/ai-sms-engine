"""
api/businesses.py — Business (tenant) management endpoints
"""
from fastapi import APIRouter, HTTPException, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional
import httpx
from database import db

router = APIRouter(prefix="/api/businesses", tags=["businesses"])


class BusinessCreate(BaseModel):
    name: str
    ghl_location_id: str
    ghl_api_key: Optional[str] = None
    ghl_client_id: Optional[str] = None
    ghl_client_secret: Optional[str] = None
    ghl_access_token: Optional[str] = None
    ghl_calendar_id: Optional[str] = None
    ai_prompt: str = "You are a helpful assistant for this business. Reply in a friendly, natural, concise SMS style."
    website_url: Optional[str] = None
    calendar_link: Optional[str] = None
    pricing_info: Optional[str] = None
    outreach_message: Optional[str] = None
    delay_min: int = 60
    delay_max: int = 180
    ai_model: str = "gemini-2.5-pro"


class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    ghl_api_key: Optional[str] = None
    ghl_client_id: Optional[str] = None
    ghl_client_secret: Optional[str] = None
    ghl_access_token: Optional[str] = None
    ghl_refresh_token: Optional[str] = None
    ghl_calendar_id: Optional[str] = None
    ai_prompt: Optional[str] = None
    website_url: Optional[str] = None
    calendar_link: Optional[str] = None
    pricing_info: Optional[str] = None
    outreach_message: Optional[str] = None
    delay_min: Optional[int] = None
    delay_max: Optional[int] = None
    ai_model: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
def list_businesses():
    businesses = db.list_businesses()
    # Mask API keys for security
    for b in businesses:
        if b.get("ghl_api_key"):
            b["ghl_api_key"] = b["ghl_api_key"][:8] + "..." + b["ghl_api_key"][-4:]
        if b.get("ghl_access_token"):
            b["ghl_access_token"] = b["ghl_access_token"][:8] + "..." + b["ghl_access_token"][-4:]
        if b.get("ghl_client_secret"):
            b["ghl_client_secret"] = b["ghl_client_secret"][:4] + "..." + b["ghl_client_secret"][-4:]
        if b.get("ghl_refresh_token"):
            b["ghl_refresh_token"] = b["ghl_refresh_token"][:8] + "..." + b["ghl_refresh_token"][-4:]
    return {"businesses": businesses}


@router.post("")
def create_business(data: BusinessCreate):
    try:
        business = db.create_business(data.model_dump())
        return {"business": business}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{business_id}")
def get_business(business_id: str):
    business = db.get_business(business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    if business.get("ghl_api_key"):
        business["ghl_api_key"] = business["ghl_api_key"][:8] + "..." + business["ghl_api_key"][-4:]
    if business.get("ghl_access_token"):
        business["ghl_access_token"] = business["ghl_access_token"][:8] + "..." + business["ghl_access_token"][-4:]
    if business.get("ghl_client_secret"):
        business["ghl_client_secret"] = business["ghl_client_secret"][:4] + "..." + business["ghl_client_secret"][-4:]
    if business.get("ghl_refresh_token"):
        business["ghl_refresh_token"] = business["ghl_refresh_token"][:8] + "..." + business["ghl_refresh_token"][-4:]
    return {"business": business}


@router.put("/{business_id}")
def update_business(business_id: str, data: BusinessUpdate):
    existing = db.get_business(business_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Business not found")
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    updated = db.update_business(business_id, updates)
    return {"business": updated}


@router.delete("/{business_id}")
def delete_business(business_id: str):
    db.delete_business(business_id)
    return {"status": "deleted"}


@router.get("/{business_id}/stats")
def get_stats(business_id: str):
    return db.get_stats(business_id)


@router.post("/oauth/exchange")
def oauth_exchange(request: Request, code: str = Form(...), business_id: str = Form(...)):
    """Exchanges the GHL authorization code for keys and saves them."""
    business = db.get_business(business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
        
    client_id = business.get("ghl_client_id")
    client_secret = business.get("ghl_client_secret")
    
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="Client ID or Secret missing in business settings")
        
    redirect_uri = str(request.base_url).rstrip("/") + "/oauth/callback"
    # Ensure it uses https if it's running behind a proxy like Railway
    if "localhost" not in redirect_uri and redirect_uri.startswith("http://"):
        redirect_uri = redirect_uri.replace("http://", "https://")

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    
    resp = httpx.post("https://services.leadconnectorhq.com/oauth/token", data=data, headers=headers)
    
    if resp.status_code != 200:
        return {"error": "Failed to exchange token", "details": resp.text}
        
    tokens = resp.json()
    
    db.update_business(business_id, {
        "ghl_access_token": tokens.get("access_token"),
        "ghl_refresh_token": tokens.get("refresh_token")
    })
    
    return RedirectResponse(url="/?oauth_success=true", status_code=303)
