"""
Scrape Hub — Home Page.

Run the multi-page app with:
    streamlit run app.py
"""

import streamlit as st

st.set_page_config(page_title="Scrape Hub", page_icon="🕸️", layout="wide")

st.title("🕸️ Scrape Hub")
st.subheader("通用 Web 内容抓取框架")

st.markdown("""
在线搜索、浏览、下载来自多个平台的内容。**点击左侧导航**选择平台。

---

### 📦 支持的平台

| 平台 | 说明 | 状态 |
|------|------|------|
| 🐦 **X / Twitter** | 按账号、关键词搜索推文 | ✅ 可用 |
| 💬 **微信公众号** | 基于搜狗微信搜索文章 | ✅ 可用 |

---

### 🚀 使用方式

1. **左侧导航** → 选择平台
2. **侧边栏** → 输入搜索关键词 / 账号
3. **点击搜索** → 服务器端浏览器自动抓取
4. **浏览历史** → 查看之前的数据
5. **下载** → 导出 JSON / Markdown

### ⚠️ 部署说明

本应用需要 **Playwright + Chromium**，必须部署在自有服务器上（Docker 或直接安装）。
不支持 Streamlit Community Cloud。

```bash
# Docker 一键部署
docker compose up -d

# 访问
http://localhost:8501
```
""")

st.divider()
st.caption("Scrape Hub v0.1.0 · Powered by Playwright + Streamlit")
