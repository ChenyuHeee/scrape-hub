"""Shared UI components for commercial features."""

from __future__ import annotations

import streamlit as st

from scrape_hub.commercial.auth import get_current_user, is_logged_in, logout
from scrape_hub.commercial.config import SUPPORT_EMAIL, TIERS
from scrape_hub.commercial.credits import can_download, can_search, get_tier_config


def show_user_sidebar():
    """Display user info and quick usage stats in the sidebar."""
    if not is_logged_in():
        return

    user = get_current_user()
    if not user:
        return
    tier_cfg = get_tier_config()

    with st.sidebar:
        st.divider()
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"{tier_cfg['badge']} **{user['username']}**")
            st.caption(tier_cfg["name"])
        with col2:
            if st.button("退出", key="_logout_sidebar"):
                logout()
                st.rerun()

        _, search_msg = can_search()
        if search_msg:
            st.caption(f"🔍 {search_msg}")

        if user["tier"] != "free":
            _, dl_msg = can_download()
            if dl_msg:
                st.caption(f"⬇️ {dl_msg}")


def show_upgrade_prompt(feature: str = "此功能"):
    """Show an upgrade call-to-action card."""
    basic = TIERS["basic"]
    pro = TIERS["pro"]
    st.info(
        f"🔒 **{feature}需要升级套餐**\n\n"
        f"| 套餐 | 价格 | 搜索 | 下载 |\n"
        f"|------|------|------|------|\n"
        f"| {basic['badge']} {basic['name']} "
        f"| ¥{basic['price_monthly']}/月 "
        f"| {basic['searches_per_day']}次/天 "
        f"| {basic['downloads_per_day']}次/天 |\n"
        f"| {pro['badge']} {pro['name']} "
        f"| ¥{pro['price_monthly']}/月 "
        f"| 不限 | 不限 |\n\n"
        f"前往 **👤 账户管理** 页面了解详情，或联系 📧 {SUPPORT_EMAIL}"
    )
