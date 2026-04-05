"""
微信公众号文章搜索页面
"""

from pathlib import Path

import streamlit as st

from scrape_hub.core.storage import Storage

st.title("💬 微信公众号文章搜索")
st.caption("基于搜狗微信搜索的公众号文章自动抓取工具 · 服务器端无头浏览器运行")

DATA_DIR = Path("data/wechat")

# ── Sidebar ─────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ 搜索配置")

    keywords_text = st.text_area(
        "关键词列表（每行一个）",
        placeholder="LLM 定价\ntoken经济学\n大模型API价格",
        height=120,
    )
    accounts_text = st.text_area(
        "公众号列表（每行一个）",
        placeholder="量子位\n机器之心\n新智元",
        height=120,
    )

    st.divider()
    st.subheader("高级设置")
    max_pages = st.slider("每个关键词最大翻页数", 1, 10, 3)
    page_pause = st.slider("页面间隔（秒）", 1.0, 10.0, 3.0, step=0.5)
    skip_keywords = st.checkbox("跳过关键词搜索", value=False)
    skip_accounts = st.checkbox("跳过公众号搜索", value=False)
    debug = st.checkbox("调试模式（保存页面 HTML）", value=False)
    output_dir = st.text_input("输出目录", value=str(DATA_DIR))

# ── Tabs ────────────────────────────────────────────────────

tab_scrape, tab_browse, tab_download = st.tabs(["🔍 搜索", "📋 浏览历史", "⬇️ 下载"])

# ── Tab 1: Scrape ───────────────────────────────────────────

with tab_scrape:
    keywords = (
        [k.strip() for k in keywords_text.strip().split("\n") if k.strip()]
        if not skip_keywords else []
    )
    accounts = (
        [a.strip() for a in accounts_text.strip().split("\n") if a.strip()]
        if not skip_accounts else []
    )

    if not keywords and not accounts:
        st.info("👈 请在左侧边栏输入至少一个关键词或公众号名称。")
    else:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("关键词", len(keywords))
        with col_b:
            st.metric("公众号", len(accounts))
        with col_c:
            st.metric("每词翻页", max_pages)

        if st.button("🚀 开始搜索", type="primary", use_container_width=True):
            progress_bar = st.progress(0, text="正在启动浏览器...")
            status_area = st.empty()
            results_area = st.container()

            def on_progress(current, total, message):
                progress_bar.progress(
                    min(current / max(total, 1), 1.0), text=message
                )

            try:
                from scrape_hub.platforms.wechat import WeChatScraper

                scraper = WeChatScraper(
                    config={
                        "keywords": keywords,
                        "accounts": accounts,
                        "max_pages": max_pages,
                        "page_pause": page_pause,
                        "debug": debug,
                    },
                    output_dir=output_dir,
                    headless=True,
                )
                results = scraper.run(progress_callback=on_progress)

                total = sum(len(r.items) for r in results)
                progress_bar.progress(1.0, text="完成！")
                status_area.success(f"✅ 搜索完成！共收集 **{total}** 篇文章。")

                for r in results:
                    if r.items:
                        with results_area.expander(
                            f"{r.query_type}: {r.query_value} ({len(r.items)} 篇)"
                        ):
                            for item in r.items[:10]:
                                st.markdown(f"**{item.get('title', '')}**")
                                if item.get("account"):
                                    st.caption(
                                        f"来源: {item['account']}  "
                                        f"{item.get('time_text', '')}"
                                    )
                                if item.get("summary"):
                                    st.write(item["summary"][:200])
                                if item.get("link"):
                                    st.markdown(f"[阅读原文]({item['link']})")
                                st.divider()
                            if len(r.items) > 10:
                                st.caption(f"... 还有 {len(r.items) - 10} 篇")
                    elif r.error:
                        results_area.warning(f"{r.query_value}: {r.error}")

            except Exception as e:
                progress_bar.empty()
                status_area.error(f"❌ 搜索失败: {e}")

# ── Tab 2: Browse ───────────────────────────────────────────

with tab_browse:
    saved_files = Storage.list_saved(output_dir, "wechat")
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
            filter_text = st.text_input("🔎 筛选标题关键词", "")
            st.caption(f"共 {len(data)} 个查询")

            for group in data:
                items = group.get("items", [])
                label = f"{group.get('query_type', '')}: {group.get('query_value', '')}"

                if filter_text:
                    items = [
                        it for it in items
                        if filter_text.lower() in it.get("title", "").lower()
                    ]
                if not items:
                    continue

                with st.expander(f"{label} ({len(items)} 篇)"):
                    for item in items:
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.markdown(f"**{item.get('title', '')}**")
                            if item.get("summary"):
                                st.write(item["summary"][:200])
                        with col2:
                            if item.get("account"):
                                st.caption(item["account"])
                            if item.get("link"):
                                st.markdown(f"[链接]({item['link']})")
                        st.divider()

# ── Tab 3: Download ─────────────────────────────────────────

with tab_download:
    dl_dir = Path(output_dir)
    all_files = sorted(dl_dir.glob("wechat_*"), reverse=True) if dl_dir.exists() else []
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
