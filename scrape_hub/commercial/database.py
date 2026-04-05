"""Supabase database for user management and usage tracking."""

from __future__ import annotations

import os
from functools import lru_cache

import streamlit as st

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None  # type: ignore
    Client = None  # type: ignore


def _secret(key: str) -> str:
    """Read from Streamlit secrets, then environment."""
    try:
        val = st.secrets.get(key, "")
    except Exception:
        val = ""
    return val or os.environ.get(key, "")


@lru_cache(maxsize=1)
def get_supabase() -> "Client":
    """Return a cached Supabase client."""
    if create_client is None:
        raise RuntimeError("请安装 supabase: pip install supabase")
    url = _secret("SUPABASE_URL")
    key = _secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("请在 secrets 中配置 SUPABASE_URL 和 SUPABASE_KEY")
    return create_client(url, key)
