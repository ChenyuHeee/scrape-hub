"""
X/Twitter 推文搜索页面
"""

from pathlib import Path

import streamlit as st

from scrape_hub.core.storage import Storage

st.title("🐦 X / Twitter 推文搜索")
st.caption("基于 Playwright 的 X 推文自动抓取工具 · 服务器端无头浏览器运行")

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
    st.info(
        "💡 **X 需要登录态**\n\n"
        "首次使用请在服务器终端运行：\n"
        "```\npython -m scrape_hub run x --keywords test\n```\n"
        "完成一次登录后，会话保存在 `.browser_data/`，\n"
        "之后即可在 Web 端无头抓取。"
    )

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

        if st.button("🚀 开始搜索", type="primary", use_container_width=True):
            progress_bar = st.progress(0, text="正在启动浏览器...")
            status_area = st.empty()
            results_area = st.container()

            def on_progress(current, total, message):
                progress_bar.progress(
                    min(current / max(total, 1), 1.0), text=message
                )

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
                    headless=True,
                )
                results = scraper.run(progress_callback=on_progress)

                total = sum(len(r.items) for r in results)
                progress_bar.progress(1.0, text="完成！")
                status_area.success(f"✅ 搜索完成！共收集 **{total}** 条推文。")

                for r in results:
                    if r.items:
                        with results_area.expander(
                            f"{r.query_type}: {r.query_value} ({len(r.items)} 条)"
                        ):
                            for item in r.items[:10]:
                                st.markdown(f"**{item.get('username', '')}**")
                                st.write(item.get("text", "")[:300])
                                if item.get("link"):
                                    st.markdown(f"[原文链接]({item['link']})")
                                st.divider()
                            if len(r.items) > 10:
                                st.caption(f"... 还有 {len(r.items) - 10} 条")
                    elif r.error:
                        results_area.warning(f"{r.query_value}: {r.error}")

            except Exception as e:
                progress_bar.empty()
                status_area.error(f"❌ 搜索失败: {e}")

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
                mime = "application/json" if f.suffix == ".json" else "text/markdown"
                st.download_button(
                    "⬇️", data=f.read_bytes(), file_name=f.name,
                    mime=mime, key=f"dl_{f.name}",
                )
