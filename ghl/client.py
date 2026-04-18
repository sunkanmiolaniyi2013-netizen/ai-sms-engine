"""
ghl/client.py — GoHighLevel API v2 client
"""
import httpx
import logging
from typing import Optional
from database import db

logger = logging.getLogger(__name__)

GHL_BASE_URL = "https://services.leadconnectorhq.com"
HEADERS_BASE = {
    "Content-Type": "application/json",
    "Version": "2021-04-15",
}

def _headers(token: str) -> dict:
    h = HEADERS_BASE.copy()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def _refresh_ghl_token(business: dict) -> Optional[str]:
    refresh_url = f"{GHL_BASE_URL}/oauth/token"
    client_id = business.get("ghl_client_id")
    client_secret = business.get("ghl_client_secret")
    refresh_token = business.get("ghl_refresh_token")
    
    if not all([client_id, client_secret, refresh_token]):
        logger.error("Missing credentials for token refresh.")
        return None
        
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(refresh_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
            if resp.status_code == 200:
                tokens = resp.json()
                new_access = tokens.get("access_token")
                db.update_business(business["id"], {
                    "ghl_access_token": new_access,
                    "ghl_refresh_token": tokens.get("refresh_token")
                })
                logger.info(f"Successfully refreshed token for {business['name']}")
                return new_access
            else:
                logger.error(f"Failed to refresh token: {resp.text}")
                return None
    except Exception as e:
        logger.error(f"Error during refresh token: {e}")
        return None


async def send_sms(location_id: str, contact_id: str, message: str, business_id: str, phone: Optional[str] = None) -> bool:
    """Send an SMS to a GHL contact via the Conversations/Messages API OR an Outbound Webhook."""
    business = db.get_business(business_id)
    if not business:
        logger.error(f"Business {business_id} not found.")
        return False
        
    api_key = business.get("ghl_access_token") or business.get("ghl_api_key") or ""
    
    # If the user pasted a Webhook URL instead of an API Key (Zero-API approach)
    if api_key.startswith("http"):
        payload = {
            "contact_id": contact_id,
            "message": message,
            "location_id": location_id,
            "phone": phone
        }
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.post(api_key, json=payload)
                resp.raise_for_status()
                logger.info(f"SMS sent to contact {contact_id} via Webhook: {resp.status_code}")
                return True
            except Exception as e:
                logger.error(f"GHL Webhook send error: {e}")
                return False

    # Otherwise, use the standard GHL API
    url = f"{GHL_BASE_URL}/conversations/messages"
    payload = {
        "type": "SMS",
        "contactId": contact_id,
        "message": message,
    }
    
    async def try_send(token: str):
        async with httpx.AsyncClient(timeout=15) as client:
            return await client.post(url, json=payload, headers=_headers(token))

    try:
        resp = await try_send(api_key)
        
        # Token refresh logic
        if resp.status_code == 401 and business.get("ghl_refresh_token"):
            logger.info("Access token expired/unauthorized. Triggering refresh...")
            new_token = await _refresh_ghl_token(business)
            if new_token:
                resp = await try_send(new_token)
                
        resp.raise_for_status()
        logger.info(f"SMS sent to contact {contact_id} via API: {resp.status_code}")
        return True
    except httpx.HTTPStatusError as e:
        logger.error(f"GHL SMS sent failed: {e.response.status_code} — {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"GHL SMS send error: {e}")
        return False


async def get_contact(contact_id: str, api_key: str) -> Optional[dict]:
    url = f"{GHL_BASE_URL}/contacts/{contact_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(url, headers=_headers(api_key))
            resp.raise_for_status()
            data = resp.json()
            return data.get("contact", data)
        except Exception as e:
            logger.error(f"GHL get_contact error: {e}")
            return None

async def get_conversations(location_id: str, contact_id: str, api_key: str) -> Optional[list]:
    url = f"{GHL_BASE_URL}/conversations/search"
    params = {"locationId": location_id, "contactId": contact_id}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(url, params=params, headers=_headers(api_key))
            resp.raise_for_status()
            return resp.json().get("conversations", [])
        except Exception as e:
            logger.error(f"GHL get_conversations error: {e}")
            return None

async def trigger_workflow(location_id: str, contact_id: str, workflow_id: str, api_key: str) -> bool:
    url = f"{GHL_BASE_URL}/contacts/{contact_id}/workflow/{workflow_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(url, json={}, headers=_headers(api_key))
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"GHL trigger_workflow error: {e}")
            return False
