# 🕸️ Scrape Hub

**A generalized web scraping framework with Streamlit UI.**

Scrape Hub provides a unified architecture for building web scrapers with [Playwright](https://playwright.dev/python/) and interactive dashboards with [Streamlit](https://streamlit.io/). Each platform (X/Twitter, WeChat, etc.) is a self-contained adapter that plugs into the core framework.

> ⚠️ **需要自部署**：本项目依赖 Playwright + Chromium，不支持 Streamlit Community Cloud。请使用 Docker 或直接安装。

## ✨ Features

- **Plugin Architecture** — Add new platforms by subclassing `BaseScraper`
- **Anti-Detection** — Built-in browser fingerprint spoofing and stealth mode
- **Persistent Sessions** — Login once, reuse sessions across runs
- **Dual Output** — Every scrape produces both JSON (for processing) and Markdown (for reading)
- **Streamlit Multi-Page App** — One page per platform with search, browse, and download
- **Real-time Progress** — Progress bar and live status updates in the web UI
- **Docker Ready** — One-command deployment with `docker compose up`
- **CLI & Python API** — Use from command line or import as a library

## 📦 Supported Platforms

| Platform | Scraper | Description |
|----------|---------|-------------|
| 🐦 X / Twitter | `XTwitterScraper` | Search tweets by account & keyword |
| 💬 WeChat (微信公众号) | `WeChatScraper` | Search articles via Sogou WeChat |

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
git clone https://github.com/ChenyuHeee/scrape-hub.git
cd scrape-hub

# Build and start
docker compose up -d

# Open in browser
open http://localhost:8501
```

### Option 2: Local Install

```bash
git clone https://github.com/ChenyuHeee/scrape-hub.git
cd scrape-hub

python -m venv .venv
source .venv/bin/activate

pip install -e .
playwright install chromium
```

### CLI Usage

```bash
# Search X/Twitter
python -m scrape_hub run x_twitter \
    --keywords "LLM pricing" "token economics" \
    --accounts sama JensenHuang

# Search WeChat
python -m scrape_hub run wechat \
    --keywords "大模型定价" "token经济学" \
    --accounts "量子位" "机器之心"
```

### Streamlit App (Multi-Page)

```bash
# Launch the multi-page app (includes all platforms)
python -m scrape_hub app

# Or directly
streamlit run app.py
```

### Python API

```python
from scrape_hub.platforms import XTwitterScraper

scraper = XTwitterScraper(
    config={
        "keywords": ["LLM pricing", "API cost"],
        "accounts": ["sama"],
        "max_scroll": 10,
    },
    output_dir="my_data/x",
)
results = scraper.run()

for r in results:
    print(f"{r.query_type}: {r.query_value} → {len(r.items)} items")
```

## 🏗️ Architecture

```
scrape-hub/
├── app.py                      # Streamlit entry point (Home page)
├── pages/                      # Streamlit multi-page pages
│   ├── 1_X_Twitter.py
│   └── 2_WeChat.py
├── scrape_hub/
│   ├── core/                   # Core abstractions
│   │   ├── base_scraper.py     # BaseScraper ABC — extend this
│   │   ├── browser.py          # Playwright lifecycle + anti-detection
│   │   └── storage.py          # JSON/Markdown output
│   ├── platforms/              # Platform adapters
│   │   ├── x_twitter.py        # X/Twitter scraper
│   │   └── wechat.py           # WeChat scraper
│   └── __main__.py             # CLI entry point
├── Dockerfile                  # Docker deployment
├── docker-compose.yml
├── configs/                    # Configuration examples
└── pyproject.toml
```

## 🔌 Adding a New Platform

1. Create `scrape_hub/platforms/my_platform.py`:

```python
from scrape_hub.core.base_scraper import BaseScraper, ScrapeResult

class MyPlatformScraper(BaseScraper):
    @property
    def platform_name(self) -> str:
        return "my_platform"

    @property
    def default_config(self) -> dict:
        return {"keywords": [], "accounts": [], "locale": "en-US"}

    def search(self, query_type, query_value, **kwargs) -> ScrapeResult:
        page = self._page
        # ... your scraping logic here ...
        return ScrapeResult(query_type=query_type, query_value=query_value, items=items)
```

2. (Optional) Create a Streamlit page in `pages/3_MyPlatform.py`

3. Register in `scrape_hub/platforms/__init__.py` and `__main__.py`

## 📝 Notes

- **First-time X login**: X/Twitter requires a manual login on first run. Run the CLI once without `--headless`, complete the login, and the session is saved to `.browser_data/` for reuse.
- **Sogou captcha**: WeChat scraping via Sogou may trigger captchas. In headless mode, the scraper auto-retries; in non-headless mode, it pauses for manual input.
- **Browser data**: `.browser_data/` contains login sessions and is gitignored. Do not share it.
- **Docker volumes**: Scraped data and browser sessions persist across container restarts via Docker volumes.

## 📄 License

MIT
