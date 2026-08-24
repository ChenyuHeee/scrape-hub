# 🕸️ Scrape Hub

**AI-Agent 友好的网页抓取 CLI** —— 克隆即用，无 Web UI、无后端服务、无需 API Key。

> 💬 本仓库是纯命令行版本（v1.0）。原 Streamlit 版本保留在备份分支
> [`legacy/streamlit`](https://github.com/ChenyuHeee/scrape-hub/tree/legacy/streamlit)。

## ✨ 为什么重写

| 旧版（Streamlit） | 新版（CLI） |
| --- | --- |
| 需要起 Web 服务、点界面 | 一条命令跑完，`--json` 直接喂给 AI Agent |
| 依赖 streamlit / fastapi / supabase | 唯一重依赖：playwright |
| 微信检索只有搜狗一个引擎 | 多引擎合并 + 直达正文 |

**微信公众号检索的痛点**：微信生态是封闭的，没有任何公共搜索引擎完整收录
`mp.weixin.qq.com` 的文章——搜狗微信的专用索引**收录不全且更新滞后**（还频繁弹验证码）。
Scrape Hub 用两层手段绕过这个问题：

1. **多引擎检索** —— 搜狗之外，聚合 Bing / Baidu / 360 的 `site:mp.weixin.qq.com`
   检索（通用引擎持续爬取微信文章页，收录更快更全）；
2. **直达正文** —— 从任意渠道拿到文章链接后（搜索引擎、RSS、别人转发……），
   `fetch` 命令直接抓取 `mp.weixin.qq.com` 的全文（标题/公众号/作者/时间/正文），
   完全不受"搜索引擎收录"的约束。

## 🚀 快速开始（克隆 → 安装 → 使用）

```bash
git clone https://github.com/ChenyuHeee/scrape-hub.git
cd scrape-hub

# 方式一：make（推荐）
make install

# 方式二：手动
python -m venv .venv
.venv/bin/pip install -e .
.venv/bin/playwright install chromium

# 环境自检
.venv/bin/python -m scrape_hub doctor
```

Linux 容器 / CI 环境额外执行 `playwright install-deps chromium`。

## 💬 微信公众号（多引擎）

### 关键词搜索

```bash
# 默认按 metasearch → sogou 顺序合并结果（自动去重）
python -m scrape_hub wechat search --keywords "大模型定价" "AI Agent"

# 只要元搜索（快、无验证码、收录新）
python -m scrape_hub wechat search --keywords 大模型 --engine metasearch --max-results 20

# 只要搜狗（公众号查找 / 兜底）
python -m scrape_hub wechat search --accounts 量子位 --engine sogou

# 抓取每篇文章完整正文（慢；公众号查询时按真实来源过滤）
python -m scrape_hub wechat search --keywords 大模型 --fetch-content

# 机器可读输出（供 AI Agent 管道消费）
python -m scrape_hub wechat search --keywords 大模型 --json
```

### 直接抓取文章正文（绕过搜索引擎）

```bash
# 指定链接
python -m scrape_hub wechat fetch \
    --urls https://mp.weixin.qq.com/s/xxxx https://mp.weixin.qq.com/s/yyyy

# 从文件批量抓取（每行一个链接，或 JSON 数组）
python -m scrape_hub wechat fetch --file urls.txt

# 按公众号抓取：先用元搜索发现链接，再逐篇抓正文
python -m scrape_hub wechat fetch --accounts 量子位 机器之心 --keywords 大模型 --max-results 5

# 只要元数据（标题/公众号/时间），不要正文
python -m scrape_hub wechat fetch --urls https://mp.weixin.qq.com/s/xxxx --metadata-only
```

> 纯图片文章（正文只有图片没有文字）会被标记为 `content_type: images`，
> 输出 `image_count` 与 `image_urls`（图片直链），不会误报为空正文。

### 监控公众号新文章（`wechat watch`，基于微信读书）

"不知道文章 URL，只想知道某个号有没有发新文章"——这是搜索引擎路线做不到的
（搜狗收录不全且滞后，实测部分文章发布数月后仍搜不到）。`watch` 走微信读书路线：
微信读书把公众号当"书"实时同步，`bookId = MP_WXS_ + base64解码(文章里的 __biz)`，
而 `__biz` 就写在任意一篇该号文章的 URL/页面里——**无需搜索、无需猜 URL**。

```bash
# 1) 扫码登录微信读书（一次性，会话保存在 .browser_data/weread）
python -m scrape_hub wechat watch login --headed
#   无图形界面时: watch login（无 --headed）会把二维码截图存到 data/wechat_watch/login_qr.png

# 2) 订阅：给任意一篇该号的文章链接（或 __biz、bookId）即可
python -m scrape_hub wechat watch add "https://mp.weixin.qq.com/s/MIhB6vF8BQrL9b3cOoITsA"

# 3) 检查新文章（对比上次基线，只报告新增）
python -m scrape_hub wechat watch check --all                 # 检查书架全部
python -m scrape_hub wechat watch check MzYzOTQ1NTEyNQ==      # 按 __biz
python -m scrape_hub wechat watch check --all --fetch-content # 新文章同时抓正文
python -m scrape_hub wechat watch check --all --interval 600  # 每 10 分钟轮询

# 4) 查看已订阅列表
python -m scrape_hub wechat watch list
```

> ⚠️ 微信读书路线的已知限制：① 部分公众号的同步滞后（通常晚几小时，个别号更久）；
> ② 需要微信扫码登录一次，登录失效后需重扫；③ 偶尔弹腾讯验证码（`--headed`
> 运行时手动点掉）；④ 有风控限频，请勿高频轮询（建议间隔 ≥ 10 分钟）。
> 与 `fetch` 组合：`fetch` 一篇文章拿到 `biz` → `watch add <biz>` 开始监控。

### 检索引擎对比

| 引擎 | 原理 | 收录 | 时效 | 验证码 | 登录 |
| --- | --- | --- | --- | --- | --- |
| `metasearch` | Bing RSS + Baidu + 360 的 `site:mp.weixin.qq.com` 检索 | 广（交叉覆盖） | 较快 | 基本无 | 不需要 |
| `sogou` | 搜狗微信专用索引 | 不全 | 滞后 | 频繁 | 不需要 |

- 默认配置见 `configs/wechat.example.yaml`（`--config` 加载，需 `pip install pyyaml`）。
- 搜狗弹验证码时会暂停等待人工输入：请用 `--headed` 运行以便手动完成。
- 输出为 `data/wechat/`、`data/wechat_fetch/` 下的 JSON + Markdown 双格式文件。

## 🐦 X / Twitter

```bash
# 首次运行需要交互式登录（会话保存在 .browser_data/）
python -m scrape_hub x search --headed --accounts sama

# 之后可无头运行
python -m scrape_hub x search --accounts sama --keywords "LLM pricing" --json
```

## ☁️ 云端抓取（可选，无需本机浏览器）

仓库自带的 GitHub Actions 工作流可以在云端跑 Playwright：

```bash
gh workflow run scrape.yml \
  -f platform=wechat \
  -f config_json='{"keywords":["大模型"],"engines":["metasearch"]}'
gh run list --workflow=scrape.yml   # 查看运行状态
```

## 🏗️ 架构

```
scrape-hub/
├── scrape_hub/
│   ├── __main__.py               # 全部 CLI 入口（wechat/x/doctor）
│   ├── core/                     # BaseScraper · BrowserManager(反检测) · Storage
│   └── platforms/
│       ├── wechat/               # 微信公众号（多引擎）
│       │   ├── scraper.py        #   编排：多引擎合并去重 → 链接解析 → 正文增强
│       │   ├── article.py        #   跳转链接解析 + mp.weixin.qq.com 全文提取（含纯图片文章）
│       │   ├── fetcher.py        #   wechat fetch：链接列表 → 正文批处理
│       │   ├── weread.py         #   wechat watch：微信读书接口，公众号新文章监控
│       │   └── backends/         #   检索后端（新增引擎只需实现 WeChatBackend）
│       │       ├── sogou.py      #   搜狗微信
│       │       └── metasearch.py #   Bing/Baidu/360 site: 检索
│       └── x_twitter.py          # X/Twitter
├── configs/                      # YAML 配置示例
├── AGENTS.md                     # 给 AI Agent 的仓库使用说明
├── Makefile                      # make install / doctor / wechat ...
└── .github/workflows/scrape.yml  # 云端抓取工作流
```

## 🔌 新增一个微信检索引擎

在 `scrape_hub/platforms/wechat/backends/` 新建模块，实现 `WeChatBackend`：

```python
from scrape_hub.platforms.wechat.backends.base import WeChatBackend

class MyEngine(WeChatBackend):
    name = "my_engine"

    def search_keyword(self, page, keyword, limit=10, **kwargs) -> list[dict]:
        # 返回 [{"title", "link", "summary", "account", "time_text"}, ...]
        ...

    def search_account(self, page, account, limit=10, **kwargs) -> list[dict]:
        ...
```

然后在 `backends/__init__.py` 的 `BACKENDS` 注册即可：
`--engine my_engine` 或 `configs/wechat.yaml` 中 `engines: [my_engine, metasearch]`。

## 🗺️ 其他可选路线（Roadmap）

- **微信客户端「搜一搜」**（微信内全量索引、实时，无需微信读书）：Windows 桌面自动化方案，
  参考 [wechat-soss-scraper](https://github.com/tony-eya/wechat-soss-scraper)；
  最全但脆弱，依赖微信版本与 UI 模板。可作为 `watch` 的第二个数据源。
- **微信公众平台官方后台接口**（需要公众号管理员账号，仅能查自己的素材）：
  参考 [wechat_mp](https://github.com/RogerLiNing/wechat_mp)。
- **商业数据服务**：新榜、西瓜数据等（付费 API）。
- **商业数据服务**：新榜、西瓜数据等（付费 API）。

## 📝 注意事项

- 请遵守目标网站的服务条款与 robots 约定，控制抓取频率（默认间隔 ≥1.5s），
  仅用于学习研究用途。
- `.browser_data/`（登录会话）与 `data/`（抓取结果）已被 gitignore，请勿提交。
- 微信风控提示"环境异常"时，请更换网络或稍后重试。

## 📄 License

MIT
