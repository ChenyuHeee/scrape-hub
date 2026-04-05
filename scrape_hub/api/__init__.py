"""
FastAPI backend API for Scrape Hub.

Runs on your own server alongside Playwright + Chromium.
The Streamlit frontend (which can be on Streamlit Cloud) calls this API.

Usage:
    uvicorn scrape_hub.api.server:app --host 0.0.0.0 --port 8000

    # Or via CLI:
    python -m scrape_hub api --port 8000

NOTE: FastAPI / Pydantic are imported lazily so that ``import scrape_hub.api``
does **not** fail on environments where only the *client* is needed (e.g.
Streamlit Cloud, which never runs the server).
"""

from __future__ import annotations


def create_app():
    """Build and return the FastAPI application.

    All heavy imports (FastAPI, Pydantic) happen inside this function so that
    simply importing the ``scrape_hub.api`` package does not require them.
    """
    import hmac
    import os
    import time
    from typing import Any

    from fastapi import FastAPI, HTTPException, Header
    from pydantic import BaseModel, Field

    app = FastAPI(
        title="Scrape Hub API",
        version="0.2.0",
        description="Remote scraping API — Playwright runs here, Streamlit Cloud calls this.",
    )

    # ── Auth ────────────────────────────────────────────────────
    API_SECRET = os.environ.get("SCRAPE_HUB_API_SECRET", "")

    def _verify_token(authorization: str | None):
        if not API_SECRET:
            return
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
        token = authorization.removeprefix("Bearer ")
        if not hmac.compare_digest(token, API_SECRET):
            raise HTTPException(status_code=403, detail="Invalid API token")

    # ── Models ──────────────────────────────────────────────────

    class ScrapeRequest(BaseModel):
        platform: str = Field(..., pattern="^(x_twitter|wechat)$")
        config: dict[str, Any] = Field(default_factory=dict)
        headless: bool = True

    class ScrapeResultItem(BaseModel):
        query_type: str
        query_value: str
        items: list[dict[str, Any]]
        collected_at: str
        error: str | None = None

    class ScrapeResponse(BaseModel):
        ok: bool
        platform: str
        results: list[ScrapeResultItem]
        elapsed_seconds: float

    class HealthResponse(BaseModel):
        status: str
        version: str

    # ── Endpoints ───────────────────────────────────────────────

    @app.get("/health", response_model=HealthResponse)
    def health_check():
        return HealthResponse(status="ok", version="0.2.0")

    @app.post("/scrape", response_model=ScrapeResponse)
    def run_scrape(
        req: ScrapeRequest,
        authorization: str | None = Header(default=None),
    ):
        _verify_token(authorization)
        t0 = time.time()
        try:
            scraper = _create_scraper(req.platform, req.config, req.headless)
            results = scraper.run()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        elapsed = time.time() - t0
        return ScrapeResponse(
            ok=True,
            platform=req.platform,
            results=[
                ScrapeResultItem(
                    query_type=r.query_type,
                    query_value=r.query_value,
                    items=r.items,
                    collected_at=r.collected_at,
                    error=r.error,
                )
                for r in results
            ],
            elapsed_seconds=round(elapsed, 2),
        )

    @app.get("/platforms")
    def list_platforms(authorization: str | None = Header(default=None)):
        _verify_token(authorization)
        from scrape_hub.platforms.x_twitter import XTwitterScraper
        from scrape_hub.platforms.wechat import WeChatScraper
        return {
            "platforms": {
                "x_twitter": {
                    "name": "X / Twitter",
                    "default_config": XTwitterScraper(config={}).default_config,
                },
                "wechat": {
                    "name": "微信公众号",
                    "default_config": WeChatScraper(config={}).default_config,
                },
            }
        }

    def _create_scraper(platform: str, config: dict, headless: bool):
        if platform == "x_twitter":
            from scrape_hub.platforms.x_twitter import XTwitterScraper
            return XTwitterScraper(config=config, headless=headless)
        elif platform == "wechat":
            from scrape_hub.platforms.wechat import WeChatScraper
            return WeChatScraper(config=config, headless=headless)
        else:
            raise ValueError(f"Unknown platform: {platform}")

    return app
