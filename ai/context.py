"""
ai/context.py — Business website scraper & context cache
"""
import httpx
import logging
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 24


def _is_cache_stale(cached_at_iso: Optional[str]) -> bool:
    if not cached_at_iso:
        return True
    try:
        cached_at = datetime.fromisoformat(cached_at_iso.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - cached_at > timedelta(hours=CACHE_TTL_HOURS)
    except Exception:
        return True


async def fetch_website_context(url: str) -> Optional[str]:
    """
    Scrape the business website and return a clean text summary.
    Focuses on homepage and /about content.
    Returns max 2000 chars.
    """
    if not url:
        return None

    # Ensure URL has scheme
    if not url.startswith("http"):
        url = f"https://{url}"

    pages_to_try = [url, url.rstrip("/") + "/about", url.rstrip("/") + "/about-us"]
    combined_text = []

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for page_url in pages_to_try[:2]:  # check home + about
            try:
                resp = await client.get(page_url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; SMSBot/1.0)"
                })
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                # Remove junk tags
                for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
                    tag.decompose()

                # Extract meaningful text
                text = soup.get_text(separator=" ", strip=True)
                # Collapse whitespace
                import re
                text = re.sub(r'\s+', ' ', text).strip()
                combined_text.append(text[:1200])

            except Exception as e:
                logger.warning(f"Could not scrape {page_url}: {e}")
                continue

    if not combined_text:
        return None

    full_context = " | ".join(combined_text)
    return full_context[:2000]


async def get_or_refresh_website_context(contact: dict, business_website_url: Optional[str]) -> Optional[str]:
    """
    Returns cached website context or refetches if stale.
    Updates the DB cache automatically.
    """
    from database.db import update_contact_cache

    if not business_website_url:
        return None

    # Check if cache is still fresh
    if contact.get("website_context") and not _is_cache_stale(contact.get("website_cached_at")):
        logger.info(f"Using cached website context for contact {contact['id']}")
        return contact["website_context"]

    # Refetch
    logger.info(f"Fetching fresh website context for {business_website_url}")
    context = await fetch_website_context(business_website_url)
    if context:
        update_contact_cache(contact["id"], context)
    return context
