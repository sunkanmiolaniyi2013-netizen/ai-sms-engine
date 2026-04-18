"""
main.py — AI SMS Reactivation Engine — FastAPI entry point
"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start delay scheduler on startup
    from task_queue.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    logger.info("AI SMS Reactivation Engine started ✓")
    yield
    stop_scheduler()
    logger.info("Engine shut down")


app = FastAPI(
    title="AI SMS Reactivation Engine",
    description="GHL-integrated AI SMS bot with multi-tenant support",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────
from ghl.webhook import router as webhook_router
from api.businesses import router as businesses_router
from api.conversations import router as conversations_router
from api.campaigns import router as campaigns_router

app.include_router(webhook_router)
app.include_router(businesses_router)
app.include_router(conversations_router)
app.include_router(campaigns_router)

# ── Static files (dashboard) ─────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def dashboard():
    return FileResponse("static/index.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "AI SMS Reactivation Engine"}


@app.get("/oauth/callback")
def oauth_callback(code: str):
    from database import db
    from fastapi.responses import HTMLResponse
    
    businesses = db.list_businesses()
    options = "".join(
        f'<option value="{b["id"]}">{b["name"]} (Loc: {b["ghl_location_id"]})</option>'
        for b in businesses
    )
    
    html = f"""
    <html>
      <head>
        <title>GHL OAuth Successful</title>
        <style>
          body {{ font-family: sans-serif; background: #0b0f19; color: white; display:flex; justify-content:center; align-items:center; height: 100vh; margin:0; }}
          .box {{ background: #1a2235; padding: 40px; border-radius: 12px; text-align: center; max-width: 400px; }}
          select {{ width: 100%; padding: 10px; margin: 20px 0; background: #0b0f19; color: white; border: 1px solid #2d3748; border-radius: 6px; }}
          button {{ background: #2563eb; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-weight: bold; width: 100%; }}
          button:hover {{ background: #1d4ed8; }}
        </style>
      </head>
      <body>
        <div class="box">
          <h2>🎉 Authorization Received!</h2>
          <p>GoHighLevel has sent the secure access code.</p>
          <p>Which business should we attach these tokens to?</p>
          <form action="/api/businesses/oauth/exchange" method="POST">
            <input type="hidden" name="code" value="{code}">
            <select name="business_id" required>
              <option value="" disabled selected>Select a business...</option>
              {options}
            </select>
            <button type="submit">Complete Installation</button>
          </form>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(content=html)
