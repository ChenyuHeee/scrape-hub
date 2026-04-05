"""
👤 账户管理 — 登录 / 注册 / 套餐 / 使用统计
"""

import streamlit as st

from scrape_hub.commercial.ads import show_banner_ad, show_in_content_ad
from scrape_hub.commercial.auth import (
    get_current_user,
    is_logged_in,
    login_user,
    logout,
    register_user,
)
from scrape_hub.commercial.config import PAYMENT_LINKS, SUPPORT_EMAIL, TIERS
from scrape_hub.commercial.credits import get_tier_config, get_usage_stats

st.set_page_config(page_title="账户管理 · Scrape Hub", page_icon="👤")
st.title("👤 账户管理")

show_banner_ad("header")

# ── Not logged in ───────────────────────────────────────────

if not is_logged_in():
    st.markdown("登录或注册以使用 Scrape Hub 的全部功能。")

    tab_login, tab_register = st.tabs(["🔑 登录", "📝 注册"])

    with tab_login:
        with st.form("acct_login"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            if st.form_submit_button("登录", type="primary", use_container_width=True):
                if username and password:
                    ok, msg = login_user(username, password)
                    if ok:
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("请填写用户名和密码")

    with tab_register:
        with st.form("acct_register"):
            new_u = st.text_input("用户名", key="acct_reg_u")
            new_p = st.text_input("密码", type="password", key="acct_reg_p")
            new_p2 = st.text_input("确认密码", type="password", key="acct_reg_p2")
            if st.form_submit_button("注册", use_container_width=True):
                if not new_u or not new_p:
                    st.warning("请填写所有字段")
                elif new_p != new_p2:
                    st.error("两次密码不一致")
                else:
                    ok, msg = register_user(new_u, new_p)
                    if ok:
                        st.success(msg + " 请切换到「登录」标签页。")
                    else:
                        st.error(msg)

    st.stop()

# ── Logged in ───────────────────────────────────────────────

user = get_current_user()
if not user:
    st.error("会话已过期，请重新登录。")
    st.stop()
tier_cfg = get_tier_config()
stats = get_usage_stats()

st.markdown(f"### {tier_cfg['badge']} {user['username']}")
st.caption(f"当前套餐：**{tier_cfg['name']}**")

if st.button("退出登录"):
    logout()
    st.rerun()

st.divider()

# ── Usage Stats ─────────────────────────────────────────────

st.subheader("📊 使用统计")
col_a, col_b, col_c = st.columns(3)

with col_a:
    limit_s = tier_cfg["searches_per_day"]
    label_s = str(stats.get("searches_today", 0))
    label_s += " (不限)" if limit_s == -1 else f" / {limit_s}"
    st.metric("今日搜索", label_s)

with col_b:
    limit_d = tier_cfg["downloads_per_day"]
    label_d = str(stats.get("downloads_today", 0))
    label_d += " (不限)" if limit_d == -1 else f" / {limit_d}"
    st.metric("今日下载", label_d)

with col_c:
    st.metric("累计搜索", stats.get("total_searches", 0))

show_in_content_ad()

st.divider()

# ── Pricing Table ───────────────────────────────────────────

st.subheader("💎 套餐方案")

cols = st.columns(3)
for (tier_key, tier_info), col in zip(TIERS.items(), cols):
    with col:
        is_current = user["tier"] == tier_key
        price = tier_info["price_monthly"]

        st.markdown(f"#### {tier_info['badge']} {tier_info['name']}")
        st.markdown(f"**¥{price}/月**" if price > 0 else "**免费**")

        searches = tier_info["searches_per_day"]
        downloads = tier_info["downloads_per_day"]
        preview = tier_info["preview_limit"]

        st.markdown(
            f"- 🔍 搜索：{'不限' if searches == -1 else f'{searches} 次/天'}\n"
            f"- ⬇️ 下载：{'不限' if downloads == -1 else f'{downloads} 次/天'}\n"
            f"- 👀 预览：{'全部结果' if preview == -1 else f'前 {preview} 条'}"
        )

        if is_current:
            st.success("✅ 当前套餐")
        elif price > 0:
            link = PAYMENT_LINKS.get(f"{tier_key}_monthly", "")
            if link and "your_" not in link:
                st.link_button(
                    f"升级到{tier_info['name']}",
                    link,
                    use_container_width=True,
                )
            else:
                st.info(f"📧 联系升级: {SUPPORT_EMAIL}")

st.divider()
st.caption(f"如需帮助或企业合作，请联系 📧 {SUPPORT_EMAIL}")

show_banner_ad("in_content")
