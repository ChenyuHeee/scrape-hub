"""
X/Twitter 推文搜索页面
"""

from pathlib import Path

import streamlit as st

from scrape_hub.api.client import get_backend_mode, is_remote_mode, remote_scrape
from scrape_hub.api.github_backend import github_scrape
from scrape_hub.commercial.ads import show_banner_ad, show_in_content_ad, show_sidebar_ad
from scrape_hub.commercial.auth import require_login
from scrape_hub.commercial.credits import (
    can_download,
    can_search,
    get_preview_limit,
    log_usage,
)
from scrape_hub.commercial.ui import show_upgrade_prompt, show_user_sidebar
from scrape_hub.core.storage import Storage

st.title("🐦 X / Twitter 推文搜索")
st.caption("基于 Playwright 的 X 推文自动抓取工具 · 服务器端无头浏览器运行")

require_login()
show_banner_ad("header")

DATA_DIR = Path("data/x_twitter")

# ── Sidebar ─────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ 搜索配置")

    accounts_text = st.text_area(
        "账号列表（每行一个）",
        placeholder="sama\nJensenHuang\nArtificialAnlys",
        height=120,
    )
    keywords_text = st.text_area(
        "关键词列表（每行一个）",
        placeholder="LLM pricing\ntoken economics\nAPI cost",
        height=120,
    )

    st.divider()
    st.subheader("高级设置")
    max_scroll = st.slider("每次搜索最大滚动次数", 1, 50, 15)
    scroll_pause = st.slider("滚动间隔（秒）", 0.5, 10.0, 2.5, step=0.5)
    output_dir = st.text_input("输出目录", value=str(DATA_DIR))

    st.divider()
    _mode = get_backend_mode()
    if _mode == "api":
        st.success("☁️ **远程 API 模式**\n\n通过自建 API 后端执行搜索。")
    elif _mode == "github":
        st.success("🐙 **GitHub Actions 模式**\n\n零成本通过 GitHub Actions 执行搜索（约需 2-5 分钟）。")
    else:
        st.info(
            "💡 **本地模式 (Playwright)**\n\n"
            "X 需要登录态。首次使用请在服务器终端运行：\n"
            "```\npython -m scrape_hub run x --keywords test\n```\n"
            "完成一次登录后，会话保存在 `.browser_data/`。"
        )

show_user_sidebar()
show_sidebar_ad()

# ── Tabs ────────────────────────────────────────────────────

tab_scrape, tab_browse, tab_download = st.tabs(["🔍 搜索", "📋 浏览历史", "⬇️ 下载"])

# ── Tab 1: Scrape ───────────────────────────────────────────

with tab_scrape:
    accounts = [a.strip() for a in accounts_text.strip().split("\n") if a.strip()]
    keywords = [k.strip() for k in keywords_text.strip().split("\n") if k.strip()]

    if not accounts and not keywords:
        st.info("👈 请在左侧边栏输入至少一个账号或关键词。")
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("账号", len(accounts))
        with col_b:
            st.metric("关键词", len(keywords))

        # ── Search rate limit check ──
        allowed, search_msg = can_search()
        if search_msg:
            st.caption(f"🔍 {search_msg}")

        if st.button("🚀 开始搜索", type="primary", use_container_width=True, disabled=not allowed):
            if not allowed:
                show_upgrade_prompt("更多搜索次数")
                st.stop()
            log_usage("search", "x_twitter", f"{len(accounts)} accounts, {len(keywords)} keywords")

            progress_bar = st.progress(0, text="正在启动...")
            status_area = st.empty()
            results_area = st.container()

            def on_progress(current, total, message):
                progress_bar.progress(
                    min(current / max(total, 1), 1.0), text=message
                )

            scrape_config = {
                "accounts": accounts,
                "keywords": keywords,
                "max_scroll": max_scroll,
                "scroll_pause": scroll_pause,
            }

            try:
                mode = get_backend_mode()
                if mode == "api":
                    results = remote_scrape(
                        "x_twitter", scrape_config,
                        progress_callback=on_progress,
                    )
                elif mode == "github":
                    results = github_scrape(
                        "x_twitter", scrape_config,
                        progress_callback=on_progress,
                    )
                else:
                    from scrape_hub.platforms.x_twitter import XTwitterScraper

                    scraper = XTwitterScraper(
                        config=scrape_config,
                        output_dir=output_dir,
                        headless=True,
                    )
                    results = scraper.run(progress_callback=on_progress)

                total = sum(len(r.items) for r in results)
                progress_bar.progress(1.0, text="完成！")
                status_area.success(f"✅ 搜索完成！共收集 **{total}** 条推文。")

                preview_limit = get_preview_limit()
                for r in results:
                    if r.items:
                        show_count = len(r.items) if preview_limit == -1 else min(len(r.items), preview_limit)
                        with results_area.expander(
                            f"{r.query_type}: {r.query_value} ({len(r.items)} 条)"
                        ):
                            for item in r.items[:show_count]:
                                st.markdown(f"**{item.get('username', '')}**")
                                st.write(item.get("text", "")[:300])
                                if item.get("link"):
                                    st.markdown(f"[原文链接]({item['link']})")
                                st.divider()
                            remaining = len(r.items) - show_count
                            if remaining > 0:
                                st.caption(f"🔒 还有 {remaining} 条，升级套餐查看全部")
                    elif r.error:
                        results_area.warning(f"{r.query_value}: {r.error}")

            except Exception as e:
                progress_bar.empty()
                status_area.error(f"❌ 搜索失败: {e}")

show_in_content_ad()

# ── Tab 2: Browse ───────────────────────────────────────────

with tab_browse:
    saved_files = Storage.list_saved(output_dir, "x_twitter")
    if not saved_files:
        st.info("暂无历史数据。请先执行搜索。")
    else:
        selected_file = st.selectbox(
            "选择数据文件",
            saved_files,
            format_func=lambda p: f"{p.name} ({p.stat().st_size / 1024:.1f} KB)",
        )
        if selected_file:
            data = Storage.load_json(selected_file)
            filter_text = st.text_input("🔎 搜索推文内容", "", key="x_filter")
            st.caption(f"共 {len(data)} 个查询")

            for group in data:
                items = group.get("items", [])
                label = f"{group.get('query_type', '')}: {group.get('query_value', '')}"

                if filter_text:
                    items = [
                        it for it in items
                        if filter_text.lower() in it.get("text", "").lower()
                        or filter_text.lower() in it.get("username", "").lower()
                    ]
                if not items:
                    continue

                with st.expander(f"{label} ({len(items)} 条)"):
                    for item in items:
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.markdown(f"**{item.get('username', '')}**")
                            st.write(item.get("text", "")[:300])
                        with col2:
                            if item.get("timestamp"):
                                st.caption(item["timestamp"])
                            if item.get("link"):
                                st.markdown(f"[链接]({item['link']})")
                        st.divider()

# ── Tab 3: Download ─────────────────────────────────────────

with tab_download:
    dl_allowed, dl_msg = can_download()

    if not dl_allowed:
        show_upgrade_prompt("下载数据")
    else:
        if dl_msg:
            st.caption(f"⬇️ {dl_msg}")

    dl_dir = Path(output_dir)
    all_files = sorted(dl_dir.glob("x_twitter_*"), reverse=True) if dl_dir.exists() else []
    if not all_files:
        st.info("暂无可下载的数据。")
    else:
        for f in all_files:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f.name)
            with col2:
                st.caption(f"{f.stat().st_size / 1024:.1f} KB")
            with col3:
                if dl_allowed:
                    mime = "application/json" if f.suffix == ".json" else "text/markdown"
                    if st.download_button(
                        "⬇️", data=f.read_bytes(), file_name=f.name,
                        mime=mime, key=f"dl_{f.name}",
                    ):
                        log_usage("download", "x_twitter", f.name)
                else:
                    st.button("🔒", key=f"dl_locked_{f.name}", disabled=True)
