"""Private Teachable Machine URL registry for the tomato diagnosis app.

Requires Supabase SQL setup in model_registry_setup.sql.  Only authenticated
users can access their own rows (DB RLS).  Registration does not deploy a model
or alter the standard inference pipeline.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

import streamlit as st
import history_cloud

TABLE = 'model_registrations'
MODEL_TYPES = ('株全体', '葉', '実')
_MODEL_ID_RE = re.compile(r'^/models/([A-Za-z0-9_-]+)/?$')


def validate_model_url(value: str) -> str:
    """Accept only exported Teachable Machine model links, no query/fragment."""
    s = value.strip()
    p = urlsplit(s)
    if p.scheme != 'https' or p.hostname != 'teachablemachine.withgoogle.com':
        raise ValueError('Teachable Machineで発行されたモデルURLを入力してください。')
    if p.username or p.password or p.port or p.query or p.fragment:
        raise ValueError('モデルURLに余分な情報が含まれています。')
    match = _MODEL_ID_RE.fullmatch(p.path)
    if not match:
        raise ValueError('「https://teachablemachine.withgoogle.com/models/…/」の形式で入力してください。')
    return urlunsplit(('https', 'teachablemachine.withgoogle.com', f'/models/{match.group(1)}/', '', ''))


def _client_and_user():
    try:
        return history_cloud.client(), history_cloud.user()
    except Exception:
        return None, None


def _set_page(page: str):
    st.session_state.page = page
    st.session_state.force_scroll_top = True
    st.rerun()


def _styles():
    st.markdown('''
    <style>
      div[data-testid="stMainBlockContainer"]:has(.registry-title) {
        padding-top: .35rem !important; padding-bottom: 1rem !important;
        max-width: 950px !important;
      }
      div[data-testid="stMainBlockContainer"]:has(.registry-title) > div > div[data-testid="stVerticalBlock"] {
        gap: .65rem !important;
      }
      .registry-eyebrow {font-size:12px;color:#6b7d71;font-weight:700;margin:2px 0 7px;}
      .registry-title {font-size:clamp(25px,3vw,32px);font-weight:850;line-height:1.3;color:#173b2b;margin:0 0 6px;}
      .registry-lead {font-size:14px;color:#60736a;line-height:1.7;margin:0 0 16px;}
      .registry-section {font-size:19px;font-weight:850;color:#173b2b;margin:5px 0 4px;}
      .registry-help {font-size:13px;color:#687a6e;line-height:1.7;margin:2px 0 12px;}
      .registry-row {display:flex;flex-wrap:wrap;gap:10px;align-items:baseline;}
      .registry-model-name {font-size:16px;font-weight:800;color:#174530;overflow-wrap:anywhere;}
      .registry-meta {color:#718177;font-size:12px;}
      .registry-info {background:#f5f9f6;border:1px solid #e0e9e2;border-radius:10px;
        padding:11px 14px;color:#617469;font-size:13px;line-height:1.65;margin:5px 0 12px;}
      div[data-testid="stMainBlockContainer"]:has(.registry-title) [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius:13px!important;box-shadow:none!important;
      }
      div[data-testid="stMainBlockContainer"]:has(.registry-title) .stButton button,
      div[data-testid="stMainBlockContainer"]:has(.registry-title) .stLinkButton a {
        border-radius:9px!important;min-height:42px!important;font-size:14px!important;box-shadow:none!important;
      }
      .st-key-registry_submit button {background:#23854b!important;color:white!important;border:0!important;}
      .st-key-registry_back button {background:transparent!important;color:#62756a!important;border:1px solid #d6e2da!important;}
      @media(max-width:650px){.registry-lead{font-size:13px}.registry-title{font-size:25px}}
    </style>
    ''', unsafe_allow_html=True)


def show():
    _styles()
    st.markdown('''<div class="registry-eyebrow">AIの開発・改善 / モデル登録</div>
    <div class="registry-title">AIモデルを登録する</div>
    <div class="registry-lead">Teachable Machineで作成したモデルのURLを登録できます。登録したモデルは、自分の一覧からいつでも開けます。</div>''', unsafe_allow_html=True)

    db, user = _client_and_user()
    if db is None or user is None:
        st.info('モデルの登録にはログインが必要です。登録したモデルは自分だけに表示されます。')
        if st.button('ログイン・登録へ', key='registry_login', use_container_width=True):
            _set_page('account')
        if st.button('← 1ページ前に戻る', key='registry_back'):
            _set_page('model_improve')
        return

    st.markdown('<div class="registry-section">新しいモデルを登録</div>', unsafe_allow_html=True)
    st.markdown('<div class="registry-help">入力するのは3項目だけです。Teachable Machineの「モデルをエクスポート」から共有用リンクをコピーしてください。</div>', unsafe_allow_html=True)
    with st.form('registry_add_model', clear_on_submit=True, border=True):
        model_name = st.text_input('モデル名', max_chars=80, placeholder='例：葉の黄化を判定するモデル')
        model_type = st.selectbox('モデルの種類', MODEL_TYPES)
        model_url = st.text_input('Teachable MachineのモデルURL', placeholder='https://teachablemachine.withgoogle.com/models/.../')
        st.caption('モデルのURLは公開され得ます。個人情報を含むデータや、共有できないモデルは登録しないでください。')
        submitted = st.form_submit_button('モデルを登録する', use_container_width=True, type='primary')

    if submitted:
        name = model_name.strip()
        if not name:
            st.warning('モデル名を入力してください。')
        else:
            try:
                url = validate_model_url(model_url)
                db.table(TABLE).insert({'user_id': str(user.id), 'name': name, 'model_type': model_type, 'model_url': url}).execute()
            except ValueError as exc:
                st.warning(str(exc))
            except Exception:
                st.error('保存できませんでした。データベース設定や通信状況を確認してください。')
            else:
                st.success('モデルを登録しました。下の一覧から確認できます。')

    st.markdown('<div class="registry-section">登録したモデル</div>', unsafe_allow_html=True)
    try:
        result = db.table(TABLE).select('id,name,model_type,model_url,created_at').eq('user_id', str(user.id)).order('created_at', desc=True).execute()
        rows = result.data or []
    except Exception:
        st.warning('登録モデルの一覧を読み込めませんでした。Supabaseに「model_registrations」テーブルがあるか確認してください。')
        rows = None

    if rows == []:
        st.caption('登録したモデルはまだありません。上のフォームから追加できます。')
    elif rows is not None:
        for row in rows:
            with st.container(border=True):
                st.markdown(
                    '<div class="registry-row"><span class="registry-model-name">' + _escape(row.get('name', '')) +
                    '</span><span class="registry-meta">' + _escape(row.get('model_type', '')) + '</span></div>',
                    unsafe_allow_html=True,
                )
                url = row.get('model_url', '')
                try:
                    url = validate_model_url(url)
                except (ValueError, TypeError):
                    st.caption('モデルURLが無効です。')
                    continue
                first, second = st.columns([3, 1], gap='small')
                with first:
                    st.link_button('モデルを開く ↗', url, use_container_width=True)
                with second:
                    if st.button('削除', key=f'registry_delete_request_{row["id"]}', use_container_width=True, type='secondary'):
                        st.session_state.registry_delete_id = row['id']
                if st.session_state.get('registry_delete_id') == row['id']:
                    st.warning('このモデルの登録を削除しますか？（Teachable Machine上のモデルは削除されません）')
                    yes, no = st.columns(2)
                    with yes:
                        if st.button('削除する', key=f'registry_confirm_{row["id"]}', use_container_width=True):
                            try:
                                db.table(TABLE).delete().eq('id', row['id']).eq('user_id', str(user.id)).execute()
                            except Exception:
                                st.error('削除に失敗しました。')
                            else:
                                st.session_state.pop('registry_delete_id', None)
                                st.rerun()
                    with no:
                        if st.button('やめる', key=f'registry_cancel_{row["id"]}', use_container_width=True):
                            st.session_state.pop('registry_delete_id', None)
                            st.rerun()

    st.markdown('<div class="registry-info">登録したモデルは、現在の標準AI診断を自動では置き換えません。登録モデルによる診断と比較機能は今後実装します。</div>', unsafe_allow_html=True)
    if st.button('← 1ページ前に戻る', key='registry_back'):
        _set_page('model_improve')


def _escape(text):
    from html import escape
    return escape(str(text), quote=True)
