"""
微信公众号文章搜索页面
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

st.title("💬 微信公众号文章搜索")
st.caption("基于搜狗微信搜索的公众号文章自动抓取工具 · 服务器端无头浏览器运行")

require_login()
show_banner_ad("header")

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

show_user_sidebar()
show_sidebar_ad()

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

        # ── Search rate limit check ──
        allowed, search_msg = can_search()
        if search_msg:
            st.caption(f"🔍 {search_msg}")

        if st.button("🚀 开始搜索", type="primary", use_container_width=True, disabled=not allowed):
            if not allowed:
                show_upgrade_prompt("更多搜索次数")
                st.stop()
            log_usage("search", "wechat", f"{len(keywords)} keywords, {len(accounts)} accounts")

            progress_bar = st.progress(0, text="正在启动...")
            status_area = st.empty()
            results_area = st.container()

            def on_progress(current, total, message):
                progress_bar.progress(
                    min(current / max(total, 1), 1.0), text=message
                )

            scrape_config = {
                "keywords": keywords,
                "accounts": accounts,
                "max_pages": max_pages,
                "page_pause": page_pause,
                "debug": debug,
            }

            try:
                mode = get_backend_mode()
                if mode == "api":
                    results = remote_scrape(
                        "wechat", scrape_config,
                        progress_callback=on_progress,
                    )
                elif mode == "github":
                    results = github_scrape(
                        "wechat", scrape_config,
                        progress_callback=on_progress,
                    )
                else:
                    from scrape_hub.platforms.wechat import WeChatScraper

                    scraper = WeChatScraper(
                        config=scrape_config,
                        output_dir=output_dir,
                        headless=True,
                    )
                    results = scraper.run(progress_callback=on_progress)

                total = sum(len(r.items) for r in results)
                progress_bar.progress(1.0, text="完成！")
                status_area.success(f"✅ 搜索完成！共收集 **{total}** 篇文章。")

                # Store results in session for download tab
                import json as _json
                from datetime import datetime as _dt
                _result_data = [
                    {"query_type": r.query_type, "query_value": r.query_value,
                     "items": r.items, "collected_at": getattr(r, "collected_at", ""),
                     "error": getattr(r, "error", None)}
                    for r in results
                ]
                _ts = _dt.now().strftime("%Y%m%d_%H%M%S")
                _fname = f"wechat_{_ts}.json"
                _json_bytes = _json.dumps(_result_data, ensure_ascii=False, indent=2).encode("utf-8")
                st.session_state["wechat_last_result"] = {"name": _fname, "data": _json_bytes, "total": total}

                preview_limit = get_preview_limit()
                for r in results:
                    if r.items:
                        show_count = len(r.items) if preview_limit == -1 else min(len(r.items), preview_limit)
                        with results_area.expander(
                            f"{r.query_type}: {r.query_value} ({len(r.items)} 篇)"
                        ):
                            for item in r.items[:show_count]:
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
                            remaining = len(r.items) - show_count
                            if remaining > 0:
                                st.caption(f"🔒 还有 {remaining} 篇，升级套餐查看全部")
                    elif r.error:
                        results_area.warning(f"{r.query_value}: {r.error}")

            except Exception as e:
                progress_bar.empty()
                status_area.error(f"❌ 搜索失败: {e}")

show_in_content_ad()

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
    dl_allowed, dl_msg = can_download()

    if not dl_allowed:
        show_upgrade_prompt("下载数据")
    else:
        if dl_msg:
            st.caption(f"⬇️ {dl_msg}")

    # Collect downloadable items from session (remote) + local files
    _dl_items = []

    # From session state (GitHub Actions / API mode results)
    if "wechat_last_result" in st.session_state:
        r = st.session_state["wechat_last_result"]
        _dl_items.append({"name": r["name"], "data": r["data"],
                          "size": len(r["data"]), "source": "session"})

    # From local files (local mode)
    dl_dir = Path(output_dir)
    if dl_dir.exists():
        for f in sorted(dl_dir.glob("wechat_*"), reverse=True):
            _dl_items.append({"name": f.name, "data": f.read_bytes(),
                              "size": f.stat().st_size, "source": "file"})

    if not _dl_items:
        st.info("暂无可下载的数据。请先执行搜索。")
    else:
        for item in _dl_items:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(item["name"])
            with col2:
                st.caption(f"{item['size'] / 1024:.1f} KB")
            with col3:
                if dl_allowed:
                    mime = "application/json" if item["name"].endswith(".json") else "text/markdown"
                    if st.download_button(
                        "⬇️", data=item["data"], file_name=item["name"],
                        mime=mime, key=f"dl_{item['name']}",
                    ):
                        log_usage("download", "wechat", item["name"])
                else:
                    st.button("🔒", key=f"dl_locked_{item['name']}", disabled=True)
