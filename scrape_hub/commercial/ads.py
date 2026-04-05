"""Ad display components for Streamlit pages — powered by EthicalAds."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from scrape_hub.commercial.config import ADS_ENABLED, ETHICALADS_PUBLISHER


def _has_publisher() -> bool:
    return bool(ETHICALADS_PUBLISHER)


def _ethicalads_html(ad_type: str = "image", height: int = 100) -> str:
    """Generate EthicalAds embed snippet."""
    return f"""
    <html>
    <head>
        <script async src="https://media.ethicalads.io/media/client/ethicalads.min.js"></script>
    </head>
    <body style="margin:0;padding:0;">
        <div data-ea-publisher="{ETHICALADS_PUBLISHER}"
             data-ea-type="{ad_type}"
             data-ea-style="stickybox"
             id="ea-{ad_type}"></div>
    </body>
    </html>
    """


def _placeholder_html(height: int = 90) -> str:
    return """
    <div style="
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 8px;
        padding: 14px 20px;
        text-align: center;
        color: white;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        margin: 4px 0;
    ">
        <div style="font-size: 14px; opacity: 0.95;">📢 Sponsored by EthicalAds</div>
        <div style="font-size: 11px; opacity: 0.7; margin-top: 4px;">
            Privacy-friendly ads for developers
        </div>
    </div>
    """


def show_banner_ad(location: str = "header", height: int = 100):
    """Display a banner ad (EthicalAds image type)."""
    if not ADS_ENABLED:
        return

    if _has_publisher():
        components.html(_ethicalads_html("image", height), height=height)
    else:
        components.html(_placeholder_html(height), height=height)


def show_sidebar_ad():
    """Display an ad in the sidebar."""
    if not ADS_ENABLED:
        return
    with st.sidebar:
        if _has_publisher():
            components.html(_ethicalads_html("image", 250), height=260)
        else:
            components.html(_placeholder_html(250), height=260)


def show_in_content_ad():
    """Display a smaller text ad between content sections."""
    if not ADS_ENABLED:
        return
    if _has_publisher():
        components.html(_ethicalads_html("text", 80), height=90)
    else:
        components.html(_placeholder_html(80), height=90)
