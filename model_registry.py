"""Personal Teachable Machine model URL registry.

Requires the existing public.model_registrations table and RLS policies.
Does not replace or execute registered models in the standard diagnosis.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from html import escape
from urllib.parse import urlsplit, urlunsplit

import streamlit as st
import history_cloud

TABLE = "model_registrations"
MODEL_TYPES = ("株全体", "葉", "実")
_MODEL_ID_RE = re.compile(r"^/models/([A-Za-z0-9_-]+)/?$")


def validate_model_url(value: str) -> str:
    """Validate a public Teachable Machine model URL; never accept arbitrary hosts."""
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme != "https" or parsed.hostname != "teachablemachine.withgoogle.com":
        raise ValueError("Teachable MachineのモデルURLを入力してください。")
    if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
        raise ValueError("モデルURLに余分な情報が含まれています。")
    match = _MODEL_ID_RE.fullmatch(parsed.path)
    if not match:
        raise ValueError("モデルURLの形式を確認してください。例：https://teachablemachine.withgoogle.com/models/xxxx/")
    return urlunsplit(("https", "teachablemachine.withgoogle.com", f"/models/{match.group(1)}/", "", ""))


def format_registered_at(value: str) -> str:
    """Supabase UTC timestamp -> Japan local date and time."""
    if not value:
        return "登録日時：不明"
    try:
        raw = str(value).strip()
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(ZoneInfo("Asia/Tokyo"))
        return f"登録：{dt.year}年{dt.month}月{dt.day}日 {dt:%H:%M}"
    except (ValueError, TypeError, OverflowError):
        return "登録日時：不明"


def _set_page(page: str):
    st.session_state.page = page
    st.session_state.force_scroll_top = True
    st.rerun()


def _styles():
    st.markdown("""
    <style>
      /* Model registration page only: blend with existing pale mint theme. */
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title) {
        max-width: 950px !important;
        padding-top: .1rem !important;
        padding-bottom: 1.1rem !important;
      }
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        > div > div[data-testid="stVerticalBlock"] {gap: .6rem !important;}
      .model-reg-title {font-size: clamp(26px,3vw,32px);font-weight:900;
        line-height:1.35;color:#173b2b;margin:0 0 5px;}
      .model-reg-subtitle {font-size:14px;color:#66796e;line-height:1.65;margin:0 0 14px;}
      .model-reg-section {font-size:19px;font-weight:850;color:#173b2b;margin:9px 0 6px;}
      .model-reg-name {font-size:16px;font-weight:800;color:#173b2b;overflow-wrap:anywhere;}
      .model-reg-type {font-size:12px;color:#52705c;background:#edf5ee;
        border:1px solid #d6e9da;border-radius:6px;padding:3px 9px;}
      .model-reg-row {display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:4px;}
      .model-reg-footnote {color:#738279;font-size:12px;line-height:1.6;margin-top:4px;}
      .model-reg-card-marker {display:none;}
      .model-reg-date {font-size:12px;color:#64786c;line-height:1.65;margin:10px 0 1px;}
      .model-reg-card-heading {display:flex;justify-content:space-between;align-items:flex-start;
        gap:8px;flex-wrap:wrap;min-height:44px;}
      .model-reg-card-heading .model-reg-name {flex:1;min-width:110px;font-size:17px;line-height:1.45;}
      div[data-testid="stVerticalBlockBorderWrapper"]:has(.model-reg-card-marker) {
        background:rgba(255,255,255,.94)!important;
        border:1px solid #dfe8e2!important;
        border-radius:13px!important;
        box-shadow:none!important;
        padding:14px 15px!important;
        height:100%;
      }
      div[data-testid="stVerticalBlockBorderWrapper"]:has(.model-reg-card-marker)
        [data-testid="stVerticalBlock"] {gap:.55rem!important;}
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        [class*="st-key-reg_delete_"] button {background:#fff!important;}
      @media(max-width:650px){.model-reg-card-heading .model-reg-name{font-size:16px;}}
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        div[data-testid="stVerticalBlockBorderWrapper"] {border-radius:12px!important;
        border-color:#dfe7e1!important;box-shadow:none!important;}
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        [data-testid="stTextInput"] input,
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        [data-testid="stSelectbox"] > div {border-radius:9px!important;}
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        .stButton button,
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        .stLinkButton a,
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        [data-testid="stFormSubmitButton"] button {
          border-radius:9px!important;min-height:42px!important;font-size:14px!important;
          font-weight:750!important;box-shadow:none!important;
      }
      /* Green primary submit regardless of inherited global red button rules. */
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        [data-testid="stFormSubmitButton"] button {
          background:#23864c!important;background-image:none!important;color:#fff!important;
          border:1px solid #23864c!important;
      }
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        [data-testid="stFormSubmitButton"] button:hover {
          background:#1c7440!important;border-color:#1c7440!important;
      }
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        .stLinkButton a {background:#fff!important;color:#216b42!important;
          border:1px solid #b6d3bf!important;}
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        [class*="st-key-reg_delete_"] button,
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        .st-key-registry_back button {
          background:transparent!important;background-image:none!important;
          border:1px solid #d8e2db!important;color:#69796e!important;
          box-shadow:none!important;
      }
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        [class*="st-key-reg_delete_"] button:hover,
      div[data-testid="stMainBlockContainer"]:has(.model-reg-title)
        .st-key-registry_back button:hover {
          background:#f1f6f2!important;color:#335b40!important;
      }
      @media(max-width:650px){.model-reg-subtitle{font-size:13px}.model-reg-title{font-size:25px}}
    </style>
    """, unsafe_allow_html=True)


def show():
    _styles()
    st.markdown('''<div class="model-reg-title">AIモデルを登録する</div>
    <div class="model-reg-subtitle">Teachable Machineで作成したモデルのURLを登録できます。</div>''',
                unsafe_allow_html=True)

    try:
        db, user = history_cloud.client(), history_cloud.user()
    except Exception:
        db, user = None, None

    if db is None or user is None:
        st.info("モデルの登録・確認にはログインが必要です。")
        if st.button("ログイン・登録へ", key="registry_login", use_container_width=True):
            _set_page("account")
        if st.button("← 1ページ前に戻る", key="registry_back"):
            _set_page("model_improve")
        return

    st.markdown('<div class="model-reg-section">新しいモデルを登録</div>', unsafe_allow_html=True)
    with st.form("registry_add_model", clear_on_submit=True, border=False):
        model_name = st.text_input("モデル名", max_chars=80, placeholder="例：葉の黄化を判定するモデル")
        model_type = st.selectbox("モデルの種類", MODEL_TYPES)
        model_url = st.text_input("Teachable MachineのモデルURL", placeholder="https://teachablemachine.withgoogle.com/models/.../")
        submitted = st.form_submit_button("モデルを登録する", type="primary", use_container_width=True)

    if submitted:
        name = model_name.strip()
        if not name:
            st.warning("モデル名を入力してください。")
        else:
            try:
                url = validate_model_url(model_url)
                db.table(TABLE).insert({
                    "user_id": str(user.id), "name": name,
                    "model_type": model_type, "model_url": url
                }).execute()
            except ValueError as exc:
                st.warning(str(exc))
            except Exception:
                st.error("登録できませんでした。通信状況を確認してください。")
            else:
                st.success("モデルを登録しました。")

    st.divider()
    st.markdown('<div class="model-reg-section">登録したモデル</div>', unsafe_allow_html=True)
    try:
        rows = (db.table(TABLE)
                .select("id,name,model_type,model_url,created_at")
                .eq("user_id", str(user.id))
                .order("created_at", desc=True).execute().data or [])
    except Exception:
        st.error("登録済みモデルを読み込めませんでした。接続状態を確認してください。")
        rows = None

    if rows == []:
        st.caption("登録したモデルはまだありません。")
    elif rows is not None:
        # Three cards per row on desktop; Streamlit stacks columns on narrow phones.
        for group_start in range(0, len(rows), 3):
            card_columns = st.columns(3, gap="small")
            for position, column in enumerate(card_columns):
                idx = group_start + position
                if idx >= len(rows):
                    continue
                row = rows[idx]
                row_id = str(row["id"])
                with column:
                    with st.container(border=True):
                        st.markdown(
                            '<span class="model-reg-card-marker"></span>'
                            '<div class="model-reg-card-heading">'
                            f'<span class="model-reg-name">{escape(str(row.get("name", "")))}</span>'
                            f'<span class="model-reg-type">{escape(str(row.get("model_type", "")))}</span>'
                            '</div>'
                            '<div class="model-reg-date">'
                            f'{escape(format_registered_at(row.get("created_at", "")))}'
                            '</div>', unsafe_allow_html=True,
                        )
                        try:
                            safe_url = validate_model_url(row.get("model_url", ""))
                        except (ValueError, TypeError):
                            st.caption("モデルURLを確認できませんでした。")
                        else:
                            st.link_button("モデルを開く", safe_url, use_container_width=True)
                        if st.button("削除", key=f"reg_delete_{row_id}", use_container_width=True):
                            st.session_state.registry_delete_id = row_id
                            st.rerun()
                        if st.session_state.get("registry_delete_id") == row_id:
                            st.caption("このモデルの登録を削除しますか？")
                            if st.button("削除する", key=f"registry_confirm_{row_id}",
                                         type="secondary", use_container_width=True):
                                try:
                                    (db.table(TABLE).delete().eq("id", row_id)
                                     .eq("user_id", str(user.id)).execute())
                                except Exception:
                                    st.error("削除できませんでした。")
                                else:
                                    st.session_state.pop("registry_delete_id", None)
                                    st.rerun()
                            if st.button("キャンセル", key=f"registry_cancel_{row_id}",
                                         use_container_width=True):
                                st.session_state.pop("registry_delete_id", None)
                                st.rerun()

    st.divider()
    if st.button("← 1ページ前に戻る", key="registry_back"):
        _set_page("model_improve")
