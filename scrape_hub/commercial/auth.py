"""User authentication: register, login, session management."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3

import streamlit as st

from scrape_hub.commercial.database import get_db


def _hash_password(password: str, salt: str) -> str:
    """Hash password with PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), iterations=100_000
    ).hex()


def register_user(username: str, password: str) -> tuple[bool, str]:
    """Register a new user. Returns (success, message)."""
    username = username.strip()
    if len(username) < 2:
        return False, "用户名至少 2 个字符"
    if len(password) < 6:
        return False, "密码至少 6 个字符"

    salt = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)

    with get_db() as db:
        try:
            db.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                (username, pw_hash, salt),
            )
            return True, "注册成功！"
        except sqlite3.IntegrityError:
            return False, "用户名已存在"


def login_user(username: str, password: str) -> tuple[bool, str]:
    """Verify credentials and set session. Returns (success, message)."""
    with get_db() as db:
        row = db.execute(
            "SELECT id, password_hash, salt, tier FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()

    if not row:
        return False, "用户名或密码错误"

    pw_hash = _hash_password(password, row["salt"])
    if pw_hash != row["password_hash"]:
        return False, "用户名或密码错误"

    # Set session state
    st.session_state["user_id"] = row["id"]
    st.session_state["username"] = username.strip()
    st.session_state["tier"] = row["tier"]
    return True, "登录成功"


def logout():
    """Clear session state."""
    for key in ("user_id", "username", "tier"):
        st.session_state.pop(key, None)


def is_logged_in() -> bool:
    return "user_id" in st.session_state


def get_current_user() -> dict | None:
    """Return current user info or None."""
    if not is_logged_in():
        return None
    return {
        "id": st.session_state["user_id"],
        "username": st.session_state["username"],
        "tier": st.session_state["tier"],
    }


def require_login():
    """Show login/register form and stop execution if not logged in."""
    if is_logged_in():
        return

    st.warning("🔒 请先登录后使用此功能。")

    tab_login, tab_register = st.tabs(["🔑 登录", "📝 注册"])

    with tab_login:
        with st.form("login_form"):
            u = st.text_input("用户名", key="login_u")
            p = st.text_input("密码", type="password", key="login_p")
            if st.form_submit_button("登录", type="primary", use_container_width=True):
                if u and p:
                    ok, msg = login_user(u, p)
                    if ok:
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("请填写用户名和密码")

    with tab_register:
        with st.form("register_form"):
            u = st.text_input("用户名", key="reg_u")
            p = st.text_input("密码", type="password", key="reg_p")
            p2 = st.text_input("确认密码", type="password", key="reg_p2")
            if st.form_submit_button("注册", use_container_width=True):
                if not u or not p:
                    st.warning("请填写所有字段")
                elif p != p2:
                    st.error("两次密码不一致")
                else:
                    ok, msg = register_user(u, p)
                    if ok:
                        st.success(msg + " 请切换到「登录」标签页。")
                    else:
                        st.error(msg)

    st.stop()
