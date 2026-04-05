"""Usage tracking and tier-based access control."""

from __future__ import annotations

from datetime import date

import streamlit as st

from scrape_hub.commercial.config import TIERS
from scrape_hub.commercial.database import get_supabase


def get_tier_config(tier: str | None = None) -> dict:
    """Get config for the given tier (defaults to current user's tier)."""
    tier = tier or st.session_state.get("tier", "free")
    return TIERS.get(tier, TIERS["free"])


def _count_today(user_id: int, action: str) -> int:
    today = date.today().isoformat()
    sb = get_supabase()
    result = (
        sb.table("usage_log")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("action", action)
        .gte("created_at", f"{today}T00:00:00")
        .lt("created_at", f"{today}T23:59:59.999999")
        .execute()
    )
    return result.count or 0


def log_usage(action: str, platform: str = "", detail: str = ""):
    """Log a usage event ('search' or 'download')."""
    user_id = st.session_state.get("user_id")
    if not user_id:
        return
    sb = get_supabase()
    sb.table("usage_log").insert({
        "user_id": user_id,
        "action": action,
        "platform": platform,
        "detail": detail,
    }).execute()


def can_search() -> tuple[bool, str]:
    """Check if the current user can perform a search. Returns (allowed, message)."""
    user_id = st.session_state.get("user_id")
    if not user_id:
        return False, "请先登录"

    tier_cfg = get_tier_config()
    limit = tier_cfg["searches_per_day"]
    if limit == -1:
        return True, "搜索次数不限"

    used = _count_today(user_id, "search")
    remaining = limit - used
    if remaining <= 0:
        return False, (
            f"今日搜索次数已用完（{tier_cfg['name']}：{limit} 次/天）。"
            "升级套餐可获取更多次数。"
        )
    return True, f"今日剩余 {remaining}/{limit} 次搜索"


def can_download() -> tuple[bool, str]:
    """Check if the current user can download. Returns (allowed, message)."""
    user_id = st.session_state.get("user_id")
    if not user_id:
        return False, "请先登录"

    tier_cfg = get_tier_config()
    limit = tier_cfg["downloads_per_day"]
    if limit == -1:
        return True, "下载次数不限"
    if limit == 0:
        return False, (
            f"免费版不支持下载数据。"
            f"升级到基础版（¥{TIERS['basic']['price_monthly']}/月）即可下载。"
        )

    used = _count_today(user_id, "download")
    remaining = limit - used
    if remaining <= 0:
        return False, f"今日下载次数已用完（{limit} 次/天）。"
    return True, f"今日剩余 {remaining}/{limit} 次下载"


def get_preview_limit() -> int:
    """Return the preview item limit for the current tier. -1 = unlimited."""
    return get_tier_config().get("preview_limit", 5)


def get_usage_stats() -> dict:
    """Get usage statistics for the current user."""
    user_id = st.session_state.get("user_id")
    if not user_id:
        return {}

    today = date.today().isoformat()
    sb = get_supabase()

    searches_today = (
        sb.table("usage_log")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("action", "search")
        .gte("created_at", f"{today}T00:00:00")
        .lt("created_at", f"{today}T23:59:59.999999")
        .execute()
    ).count or 0

    downloads_today = (
        sb.table("usage_log")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("action", "download")
        .gte("created_at", f"{today}T00:00:00")
        .lt("created_at", f"{today}T23:59:59.999999")
        .execute()
    ).count or 0

    total_searches = (
        sb.table("usage_log")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("action", "search")
        .execute()
    ).count or 0

    return {
        "searches_today": searches_today,
        "downloads_today": downloads_today,
        "total_searches": total_searches,
    }
