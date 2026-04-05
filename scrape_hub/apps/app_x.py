"""
Streamlit app for X (Twitter) tweet scraping.

Run with:
    streamlit run scrape_hub/apps/app_x.py
"""

import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from scrape_hub.core.storage import Storage

# ── Page config ─────────────────────────────────────────────

st.set_page_config(page_title="X/Twitter Scraper", page_icon="🐦", layout="wide")
st.title("🐦 X / Twitter 推文搜索")
st.caption("基于 Playwright 的 X 推文自动抓取工具")

DATA_DIR = Path("data/x_twitter")

# ── Sidebar: Configuration ──────────────────────────────────

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
    headless = st.checkbox("无头模式（后台运行）", value=False)
    output_dir = st.text_input("输出目录", value=str(DATA_DIR))

# ── Main area: Actions ──────────────────────────────────────

tab_scrape, tab_browse, tab_download = st.tabs(["🔍 搜索", "📋 浏览历史", "⬇️ 下载"])

# ── Tab 1: Scrape ───────────────────────────────────────────

with tab_scrape:
    st.subheader("启动搜索任务")

    accounts = [a.strip() for a in accounts_text.strip().split("\n") if a.strip()]
    keywords = [k.strip() for k in keywords_text.strip().split("\n") if k.strip()]

    if not accounts and not keywords:
        st.info("请在左侧边栏输入至少一个账号或关键词。")
    else:
        st.write(f"**账号**: {len(accounts)} 个 | **关键词**: {len(keywords)} 个")

        if st.button("🚀 开始搜索", type="primary", use_container_width=True):
            st.warning(
                "⚠️ 搜索将在后台启动浏览器。如果是首次使用，请在弹出的浏览器中登录 X 账号。"
            )

            with st.spinner("正在启动浏览器并搜索..."):
                try:
                    from scrape_hub.platforms.x_twitter import XTwitterScraper

                    scraper = XTwitterScraper(
                        config={
                            "accounts": accounts,
                            "keywords": keywords,
                            "max_scroll": max_scroll,
                            "scroll_pause": scroll_pause,
                        },
                        output_dir=output_dir,
                        headless=headless,
                    )
                    results = scraper.run()

                    total = sum(len(r.items) for r in results)
                    st.success(f"✅ 搜索完成！共收集 {total} 条推文。")

                    # Show preview
                    for r in results:
                        if r.items:
                            with st.expander(
                                f"{r.query_type}: {r.query_value} ({len(r.items)} 条)"
                            ):
                                for item in r.items[:5]:
                                    st.markdown(f"**{item.get('username', '')}**")
                                    st.write(item.get("text", ""))
                                    if item.get("link"):
                                        st.markdown(
                                            f"[原文链接]({item['link']})"
                                        )
                                    st.divider()
                                if len(r.items) > 5:
                                    st.caption(f"... 还有 {len(r.items) - 5} 条")

                except Exception as e:
                    st.error(f"搜索失败: {e}")

# ── Tab 2: Browse History ───────────────────────────────────

with tab_browse:
    st.subheader("历史搜索结果")

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
            st.write(f"共 {len(data)} 个查询")

            for group in data:
                items = group.get("items", [])
                label = f"{group.get('query_type', '')}: {group.get('query_value', '')}"
                with st.expander(f"{label} ({len(items)} 条)"):
                    if not items:
                        st.write("无结果")
                        continue
                    for item in items:
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.markdown(f"**{item.get('username', '')}**")
                            st.write(item.get("text", "")[:300])
                        with col2:
                            ts = item.get("timestamp", "")
                            if ts:
                                st.caption(ts)
                            if item.get("link"):
                                st.markdown(f"[链接]({item['link']})")
                        st.divider()

# ── Tab 3: Download ─────────────────────────────────────────

with tab_download:
    st.subheader("下载数据")

    saved_files = Storage.list_saved(output_dir, "x_twitter")
    if not saved_files:
        st.info("暂无可下载的数据。")
    else:
        for f in saved_files:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f.name)
            with col2:
                st.caption(f"{f.stat().st_size / 1024:.1f} KB")
            with col3:
                st.download_button(
                    "⬇️ 下载",
                    data=f.read_bytes(),
                    file_name=f.name,
                    mime="application/json",
                    key=f"dl_{f.name}",
                )

        # Also offer Markdown downloads
        md_files = sorted(Path(output_dir).glob("x_twitter_*.md"), reverse=True)
        if md_files:
            st.divider()
            st.caption("Markdown 文件")
            for f in md_files:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f.name)
                with col2:
                    st.caption(f"{f.stat().st_size / 1024:.1f} KB")
                with col3:
                    st.download_button(
                        "⬇️ 下载",
                        data=f.read_bytes(),
                        file_name=f.name,
                        mime="text/markdown",
                        key=f"dl_{f.name}",
                    )
