"""
Scrape Hub — Home Page.

Run the multi-page app with:
    streamlit run app.py
"""

import streamlit as st

from scrape_hub.api.client import api_health_check, get_backend_mode, is_remote_mode
from scrape_hub.api.github_backend import github_health_check, is_github_mode
from scrape_hub.commercial.ads import show_banner_ad, show_in_content_ad
from scrape_hub.commercial.auth import is_logged_in
from scrape_hub.commercial.ui import show_user_sidebar

st.set_page_config(page_title="Scrape Hub", page_icon="🕸️", layout="wide")

show_user_sidebar()

st.title("🕸️ Scrape Hub")
st.subheader("通用 Web 内容抓取框架")

show_banner_ad("header")

if not is_logged_in():
    st.info("👤 请先前往 **👤 Account** 页面登录或注册，即可使用搜索和下载功能。")

# ── Mode indicator ──
_mode = get_backend_mode()
if _mode == "api":
    healthy = api_health_check()
    if healthy:
        st.success("☁️ **远程 API 模式** — 后端已连接，可在 Streamlit Cloud 上运行。")
    else:
        st.error("☁️ **远程 API 模式** — ⚠️ 后端不可达，请检查 API 地址和网络。")
elif _mode == "github":
    healthy = github_health_check()
    if healthy:
        st.success("🐙 **GitHub Actions 模式** — 零成本通过 GitHub Actions 执行搜索（约需 2-5 分钟/次）。")
    else:
        st.error("🐙 **GitHub Actions 模式** — ⚠️ GitHub 连接失败，请检查 Token 和仓库配置。")
else:
    st.caption("🖥️ 本地模式 — 使用本机 Playwright + Chromium 执行搜索。")

st.markdown("""
在线搜索、浏览、下载来自多个平台的内容。**点击左侧导航**选择平台。

---

### 📦 支持的平台

| 平台 | 说明 | 状态 |
|------|------|------|
| 🐦 **X / Twitter** | 按账号、关键词搜索推文 | ✅ 可用 |
| 💬 **微信公众号** | 基于搜狗微信搜索文章 | ✅ 可用 |

---

### 💎 套餐方案

| 套餐 | 价格 | 搜索 | 下载 | 预览 |
|------|------|------|------|------|
| 🆓 免费版 | 免费 | 3 次/天 | ❌ | 前 5 条 |
| ⭐ 基础版 | ¥29.9/月 | 30 次/天 | 10 次/天 | 全部 |
| 💎 专业版 | ¥99.9/月 | 不限 | 不限 | 全部 |

---

### 🚀 使用方式

1. **👤 账户管理** → 注册 / 登录
2. **左侧导航** → 选择平台
3. **侧边栏** → 输入搜索关键词 / 账号
4. **点击搜索** → 自动抓取
5. **浏览历史** → 查看之前的数据
6. **下载** → 导出 JSON / Markdown（需基础版及以上）

### 🌐 三种部署模式

| 模式 | 成本 | 速度 | 说明 |
|------|------|------|------|
| 🐙 **GitHub Actions** | **免费** | ~3分钟 | 在 Streamlit Cloud Secrets 中配置 `GITHUB_TOKEN` 和 `GITHUB_REPO` |
| ☁️ **远程 API** | 需 VPS | 实时 | 自建 FastAPI 后端，配置 `SCRAPE_HUB_API_URL` |
| 🖥️ **本地** | 需服务器 | 实时 | 直接运行，Playwright 本地执行 |

### 🐙 GitHub Actions 零成本部署

适合没有服务器的用户，只需一个 GitHub 账号：

1. Fork 本仓库（或推送到你自己的 GitHub 仓库）
2. 创建 [Personal Access Token](https://github.com/settings/tokens) → 勾选 `actions` 权限
3. 在 Streamlit Cloud 部署，Settings → Secrets 中添加：

```toml
GITHUB_TOKEN = "ghp_your_personal_access_token"
GITHUB_REPO = "your-username/scrape-hub"
```

完成！搜索请求会自动触发 GitHub Actions → 等待运行 → 返回结果。

> 💡 公开仓库 Actions 分钟数**无限免费**，私有仓库每月 2000 分钟免费额度。
""")

show_in_content_ad()

st.divider()
st.caption("Scrape Hub v0.3.0 · Powered by Playwright + Streamlit + GitHub Actions")
