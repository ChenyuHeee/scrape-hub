# AGENTS.md — how AI agents should use this repository

This is a Python CLI tool for scraping web content. There is no web UI, no
server, and no API keys required for the default WeChat engines.

## Install (clone → install → run)

```bash
git clone https://github.com/ChenyuHeee/scrape-hub.git
cd scrape-hub
python -m venv .venv
.venv/bin/pip install -e .
.venv/bin/playwright install chromium
```

Or with `make install`. Verify with `.venv/bin/python -m scrape_hub doctor`.

On Linux CI (e.g. GitHub Actions / containers), also run
`playwright install-deps chromium` for system libraries.

## Key commands

```bash
# WeChat official-account articles — multi-engine search
python -m scrape_hub wechat search --keywords "大模型定价" --accounts 量子位
python -m scrape_hub wechat search --keywords 大模型 --engine metasearch --max-results 20 --json
python -m scrape_hub wechat search --keywords 大模型 --fetch-content   # + full article bodies

# Fetch full article content directly from URLs (bypasses search engines)
python -m scrape_hub wechat fetch --urls https://mp.weixin.qq.com/s/xxxx
python -m scrape_hub wechat fetch --file urls.txt
python -m scrape_hub wechat fetch --accounts 量子位 --keywords 大模型

# Monitor a public account for NEW articles (WeChat Reading backend)
python -m scrape_hub wechat watch login          # one-time QR scan (headed) or QR png
python -m scrape_hub wechat watch add <article-url|__biz|bookId>
python -m scrape_hub wechat watch check --all [--interval 600] [--fetch-content]
python -m scrape_hub wechat watch list

# X/Twitter (requires one-time interactive login in --headed mode)
python -m scrape_hub x search --keywords "LLM pricing" --accounts sama
```

## Output contract

- Results are saved to `data/<platform>/` as timestamped JSON **and**
  Markdown. JSON is the machine-readable format — parse it.
- Append `--json` to print a `__RESULT_JSON__` block on stdout containing the
  full payload (summary + outputs + results). Pipe-friendly for agents.
- Item fields (wechat): `title`, `link` (canonical `mp.weixin.qq.com/s?...`),
  `summary`, `account`, `author`, `publish_time`, `time_text`, `engine`,
  `content` / `content_length` (only with `--fetch-content`), `error`.
  Image-only articles: `content_type: "images"`, `image_count`, `image_urls`
  (no text content — do not treat as failure).

## Account monitoring (wechat watch)

- WeChat Reading treats each 公众号 as a book: `bookId = MP_WXS_ + base64decode(__biz)`.
  `__biz` is public data in any article URL/page, so `watch add` accepts an
  article link, a `__biz`, or a `bookId` — no search needed.
- Login is a one-time WeChat QR scan (session persists in `.browser_data/weread`).
  Headless login saves the QR to `data/wechat_watch/login_qr.png`.
- `watch check` diffs against state files in `data/wechat_watch/state_*.json`;
  first run establishes the baseline, later runs report new articles only.
- Known limits: per-account sync lag (hours, sometimes longer), occasional
  TCaptcha (solve manually with `--headed`), rate-limit risk — keep
  `--interval` ≥ 600s.
- Endpoint reference: weread-mp-fetcher (https://github.com/Pengyf04/weread-mp-fetcher).

## WeChat engines (order matters)

1. `metasearch` (default first): Bing RSS + Baidu + 360 via
   `site:mp.weixin.qq.com <kw>`. No login, no captcha, fresher coverage than
   Sogou — use this by default.
2. `sogou`: the classic dedicated WeChat search. Incomplete index, slow
   updates, frequent captchas. Use as fallback or for account lookup.

`--engine all` merges every engine and dedups by URL. If a Sogou captcha
appears, the browser window pauses for manual solving (run with `--headed`).

## Layout

- `scrape_hub/core/` — BaseScraper, BrowserManager (Playwright + stealth), Storage
- `scrape_hub/platforms/wechat/` — multi-engine WeChat scraper
  - `backends/` — one module per search engine (add new engines here)
  - `article.py` — redirect resolution + full article content extraction
  - `fetcher.py` — batch URL → full text (`wechat fetch`)
  - `weread.py` — WeChat Reading backend (`wechat watch`: login/shelf/articles/diff)
- `scrape_hub/platforms/x_twitter.py` — X/Twitter scraper
- `scrape_hub/__main__.py` — the entire CLI surface

## Rules

- Never commit `.browser_data/` (login sessions) or `data/` (results).
- Search engines rate-limit aggressively: keep `--page-pause` ≥ 1.5s and
  `--pause` ≥ 1.5s when fetching article bodies.
- The legacy Streamlit UI lives on the `legacy/streamlit` branch; do not
  reintroduce web UI dependencies (streamlit, fastapi, supabase) here.
