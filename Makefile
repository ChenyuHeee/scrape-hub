# Scrape Hub — common tasks
.PHONY: install doctor wechat x

## 安装依赖 + Chromium（一次性）
install:
	python -m venv .venv
	.venv/bin/pip install -e .
	.venv/bin/playwright install chromium

## 环境自检
doctor:
	.venv/bin/python -m scrape_hub doctor

## 微信公众号多引擎搜索（示例：关键词）
wechat:
	.venv/bin/python -m scrape_hub wechat search --keywords "大模型" --fetch-content

## 抓取指定公众号文章正文
wechat-account:
	.venv/bin/python -m scrape_hub wechat fetch --accounts 量子位 --max-results 5

## X/Twitter 搜索（示例）
x:
	.venv/bin/python -m scrape_hub x search --keywords "LLM pricing"
