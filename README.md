# 🕸️ Scrape Hub

**A generalized web scraping framework with Streamlit UI.**

Scrape Hub provides a unified architecture for building web scrapers with [Playwright](https://playwright.dev/python/) and interactive dashboards with [Streamlit](https://streamlit.io/). Each platform (X/Twitter, WeChat, etc.) is a self-contained adapter that plugs into the core framework.

## ✨ Features

- **Plugin Architecture** — Add new platforms by subclassing `BaseScraper`
- **Anti-Detection** — Built-in browser fingerprint spoofing and stealth mode
- **Persistent Sessions** — Login once, reuse sessions across runs
- **Dual Output** — Every scrape produces both JSON (for processing) and Markdown (for reading)
- **Streamlit Apps** — One interactive app per platform with search, browse, and download
- **CLI & Python API** — Use from command line or import as a library

## 📦 Supported Platforms

| Platform | Scraper | Streamlit App | Description |
|----------|---------|---------------|-------------|
| X / Twitter | `XTwitterScraper` | `app_x.py` | Search tweets by account & keyword |
| WeChat (微信公众号) | `WeChatScraper` | `app_wechat.py` | Search articles via Sogou WeChat |

## 🚀 Quick Start

### Installation

```bash
# Clone the repo
git clone https://github.com/hechenyu/scrape-hub.git
cd scrape-hub

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

# Install dependencies
pip install -e .

# Install Playwright browsers (first time only)
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

### Streamlit App

```bash
# Launch X/Twitter app
python -m scrape_hub app x

# Launch WeChat app
python -m scrape_hub app wechat

# Or directly with streamlit
streamlit run scrape_hub/apps/app_x.py
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
├── scrape_hub/
│   ├── core/                   # Core abstractions
│   │   ├── base_scraper.py     # BaseScraper ABC — extend this for new platforms
│   │   ├── browser.py          # Playwright lifecycle + anti-detection
│   │   └── storage.py          # JSON/Markdown output
│   ├── platforms/              # Platform adapters
│   │   ├── x_twitter.py        # X/Twitter implementation
│   │   └── wechat.py           # WeChat implementation
│   ├── apps/                   # Streamlit apps
│   │   ├── app_x.py            # X/Twitter dashboard
│   │   └── app_wechat.py       # WeChat dashboard
│   └── __main__.py             # CLI entry point
├── configs/                    # Configuration examples
├── data/                       # Default output directory (gitignored)
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

2. (Optional) Create a Streamlit app in `scrape_hub/apps/app_my_platform.py`

3. Register in `scrape_hub/platforms/__init__.py` and `__main__.py`

## 📝 Notes

- **First-time login**: X/Twitter requires manual login in the browser on first run. The session is saved to `.browser_data/` for reuse.
- **Sogou captcha**: WeChat scraping via Sogou may trigger captchas. The scraper pauses and waits for manual input.
- **Browser data**: `.browser_data/` contains login sessions and is gitignored. Do not share it.

## 📄 License

MIT
