"""Base class for WeChat article search backends.

Each backend is an independent way to discover WeChat official-account
articles. Because no single search engine fully indexes mp.weixin.qq.com
(Sogou's index is incomplete and lags), the scraper runs several backends
and merges their results:

- ``sogou``       — Sogou WeChat search (weixin.sogou.com), the classic entry.
- ``metasearch``  — Bing / Baidu / 360 with ``site:mp.weixin.qq.com`` queries;
                    broader & fresher coverage, no login, captcha-free.
"""

from __future__ import annotations

import abc
from typing import Any


class WeChatBackend(abc.ABC):
    """Interface every WeChat search backend must implement."""

    #: short identifier, e.g. "sogou", "metasearch"
    name: str = "base"

    @abc.abstractmethod
    def search_keyword(
        self, page: Any, keyword: str, limit: int, **kwargs
    ) -> list[dict]:
        """Search articles by keyword. Returns a list of item dicts.

        Item dict fields: ``title``, ``link``, ``summary``, ``account``,
        ``time_text``; the orchestrator adds ``engine`` and query metadata.
        """

    @abc.abstractmethod
    def search_account(
        self, page: Any, account: str, limit: int, **kwargs
    ) -> list[dict]:
        """Search articles published by a specific public account."""

    # ── shared helpers ──────────────────────────────────────

    @staticmethod
    def _dedup(items: list[dict], key: str = "title") -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for it in items:
            k = (it.get(key) or "").strip()
            if k and k in seen:
                continue
            if k:
                seen.add(k)
            out.append(it)
        return out
