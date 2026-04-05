"""Ad display components for Streamlit pages."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from scrape_hub.commercial.config import ADS_ENABLED, ADSENSE_CLIENT_ID, AD_SLOTS


def _is_placeholder(slot_id: str) -> bool:
    """Check if the slot ID is still a placeholder."""
    return not slot_id or slot_id.startswith("XXXX")


def show_banner_ad(location: str = "header", height: int = 90):
    """Display a banner ad. Shows placeholder if AdSense is not configured."""
    if not ADS_ENABLED:
        return

    slot_id = AD_SLOTS.get(location, AD_SLOTS.get("header", ""))

    if _is_placeholder(slot_id):
        # Attractive placeholder when no real ad ID is configured
        components.html(
            """
            <div style="
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 8px;
                padding: 14px 20px;
                text-align: center;
                color: white;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                margin: 4px 0;
            ">
                <div style="font-size: 14px; opacity: 0.95;">📢 广告位招租 · Ad Space Available</div>
                <div style="font-size: 11px; opacity: 0.7; margin-top: 4px;">
                    联系我们投放您的广告 — support@scrapehub.com
                </div>
            </div>
            """,
            height=height,
        )
        return

    # Real Google AdSense ad
    components.html(
        f"""
        <html>
        <head>
            <script async
                src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CLIENT_ID}"
                crossorigin="anonymous"></script>
        </head>
        <body style="margin:0;padding:0;">
            <ins class="adsbygoogle"
                 style="display:block"
                 data-ad-client="{ADSENSE_CLIENT_ID}"
                 data-ad-slot="{slot_id}"
                 data-ad-format="auto"
                 data-full-width-responsive="true"></ins>
            <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
        </body>
        </html>
        """,
        height=height,
    )


def show_sidebar_ad():
    """Display a vertical ad in the sidebar."""
    with st.sidebar:
        show_banner_ad("sidebar", height=250)


def show_in_content_ad():
    """Display a smaller ad between content sections."""
    show_banner_ad("in_content", height=80)
