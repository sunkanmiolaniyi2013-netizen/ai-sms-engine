"""
ghl/calendar.py — GHL v2 Calendar API client
Handles fetching free slots, booking appointments, and auto-refreshing OAuth tokens.
"""
import httpx
import logging
from typing import Optional
from database import db

logger = logging.getLogger(__name__)

GHL_V2_BASE_URL = "https://services.leadconnectorhq.com"
GHL_VERSION = "2021-04-15"


def _refresh_access_token(business: dict) -> str:
    """Uses the refresh_token to get a new access_token, saves to DB, returns new token."""
    logger.info(f"Refreshing GHL OAuth token for business {business['id']}")
    data = {
        "client_id": business["ghl_client_id"],
        "client_secret": business["ghl_client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": business["ghl_refresh_token"]
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    
    resp = httpx.post(f"{GHL_V2_BASE_URL}/oauth/token", data=data, headers=headers)
    if resp.status_code != 200:
        logger.error(f"Failed to refresh token: {resp.text}")
        raise Exception(f"OAuth token refresh failed: {resp.text}")
        
    tokens = resp.json()
    new_access = tokens.get("access_token")
    new_refresh = tokens.get("refresh_token")
    
    # Update DB
    db.update_business(business["id"], {
        "ghl_access_token": new_access,
        "ghl_refresh_token": new_refresh
    })
    
    return new_access


def _make_ghl_request(method: str, endpoint: str, business: dict, params: dict = None, json_data: dict = None):
    """Wrapper to make GHL v2 API calls and auto-refresh tokens on 401."""
    token = business.get("ghl_access_token")
    if not token:
        raise Exception("Business has no GHL access token configured.")
        
    url = f"{GHL_V2_BASE_URL}{endpoint}"
    
    def get_headers(t):
        return {
            "Authorization": f"Bearer {t}",
            "Version": GHL_VERSION,
            "Accept": "application/json"
        }
        
    # Attempt 1
    resp = httpx.request(method, url, headers=get_headers(token), params=params, json=json_data)
    
    # Handle Expiration
    if resp.status_code == 401:
        new_token = _refresh_access_token(business)
        # Attempt 2
        resp = httpx.request(method, url, headers=get_headers(new_token), params=params, json=json_data)
        
    resp.raise_for_status()
    return resp.json()


def get_free_slots(business: dict, start_date: str, end_date: str) -> dict:
    """
    Fetches available slots for the configured calendar.
    start_date and end_date should be timestamps in ms or YYYY-MM-DD.
    Wait, GHL free-slots API requires ms timestamp for startDate and endDate.
    """
    calendar_id = business.get("ghl_calendar_id")
    if not calendar_id:
        raise Exception("GHL Calendar ID is not configured for this business.")
        
    endpoint = f"/calendars/{calendar_id}/free-slots"
    params = {
        "startDate": start_date,
        "endDate": end_date
    }
    
    # Let the wrapper auto-refresh tokens if needed
    data = _make_ghl_request("GET", endpoint, business, params=params)
    return data


def book_appointment(business: dict, contact_id: str, start_time: str) -> dict:
    """
    Books an appointment in the configured calendar.
    start_time must be ISO-8601 (e.g., '2023-10-25T14:00:00Z').
    """
    calendar_id = business.get("ghl_calendar_id")
    location_id = business.get("ghl_location_id")
    
    if not calendar_id:
        raise Exception("GHL Calendar ID is not configured for this business.")

    endpoint = "/calendars/events/appointments"
    json_payload = {
        "calendarId": calendar_id,
        "locationId": location_id,
        "contactId": contact_id,
        "startTime": start_time
    }
    
    data = _make_ghl_request("POST", endpoint, business, json_data=json_payload)
    return data
