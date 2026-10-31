"""Optional per-user diagnosis history with Supabase Auth, RLS and private Storage.

Google OAuth and password recovery use PKCE. A short-lived, single-use, in-process
rendezvous keeps PKCE verifiers across redirects without placing them in URLs.
"""

import base64
import hashlib
import io
import httpx
import secrets
import threading
import time
import uuid

from PIL import Image
import streamlit as st
from supabase import ClientOptions, create_client

BUCKET = "diagnosis-photos"
TABLE = "diagnosis_records"
TEST_URL = "https://tomato-diagnosis-test-gttdtnicndwbzp3b4kuy9x.streamlit.app/"
OAUTH_TTL_SECONDS = 600
RECOVERY_TTL_SECONDS = 3600


def configured():
    try:
        return bool(st.secrets.get("SUPABASE_URL") and st.secrets.get("SUPABASE_ANON_KEY"))
    except (FileNotFoundError, KeyError):
        return False


def _new_client(pkce=False):
    if pkce:
        return create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_ANON_KEY"],
            options=ClientOptions(flow_type="pkce"),
        )
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])


def client():
    if not configured():
        return None
    if "history_supabase_client" not in st.session_state:
        st.session_state.history_supabase_client = _new_client()
    return st.session_state.history_supabase_client


@st.cache_resource
def _pending_oauth():
    # Shared in this Streamlit process, never rendered. Keys are random 256-bit ids.
    return {"lock": threading.Lock(), "items": {}}


def _make_google_link():
    pool = _pending_oauth()
    attempt = secrets.token_urlsafe(32)
    oauth_client = _new_client(pkce=True)
    redirect_to = f"{TEST_URL}?oauth_attempt={attempt}"
    result = oauth_client.auth.sign_in_with_oauth(
        {"provider": "google", "options": {"redirect_to": redirect_to}}
    )
    url = getattr(result, "url", None)
    if not url or not url.startswith("https://"):
        raise RuntimeError("Supabase did not provide an OAuth URL")
    with pool["lock"]:
        now = time.monotonic()
        pool["items"] = {
            k: value for k, value in pool["items"].items()
            if now - value[0] < OAUTH_TTL_SECONDS
        }
        pool["items"][attempt] = (now, oauth_client)
    return url


def _google_callback():
    """Exchange the single-use OAuth code in the original PKCE client."""
    attempt = st.query_params.get("oauth_attempt")
    if not attempt:
        return
    code = st.query_params.get("code")
    error = st.query_params.get("error")
    pool = _pending_oauth()
    with pool["lock"]:
        pending = pool["items"].pop(attempt, None)
    # The code is sensitive: remove it from the browser URL immediately.
    st.query_params.clear()
    if error:
        st.error("Googleログインがキャンセルされたか、認証に失敗しました。もう一度お試しください。")
        return
    if not code or not pending or time.monotonic() - pending[0] > OAUTH_TTL_SECONDS:
        st.warning("Googleログインの有効期限が切れました。もう一度「Googleでログイン」を押してください。")
        return
    try:
        oauth_client = pending[1]
        response = oauth_client.auth.exchange_code_for_session({"auth_code": code})
        if not response.session:
            st.error("Googleのログインセッションを取得できませんでした。")
            return
        st.session_state.history_supabase_client = oauth_client
        st.session_state.pop("history_google_url", None)
        st.success("Googleアカウントでログインしました。")
        st.rerun()
    except Exception as exc:
        _show_auth_error(exc)


def _send_recovery_email(email):
    """Send recovery email with explicit PKCE challenge (auth-py omits it)."""
    attempt = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    redirect_to = f"{TEST_URL}?recovery_attempt={attempt}"
    api_url = st.secrets["SUPABASE_URL"].rstrip("/") + "/auth/v1/recover"
    api_key = st.secrets["SUPABASE_ANON_KEY"]
    with httpx.Client(timeout=20) as http:
        response = http.post(
            api_url,
            headers={"apikey": api_key, "Content-Type": "application/json"},
            params={"redirect_to": redirect_to},
            json={
                "email": email,
                "code_challenge": challenge,
                "code_challenge_method": "s256",
            },
        )
    response.raise_for_status()
    # Keep verifier server-side. A random attempt identifies exactly one recovery.
    pool = _pending_oauth()
    with pool["lock"]:
        now = time.monotonic()
        pool["items"] = {
            k: v for k, v in pool["items"].items()
            if now - v[0] < (RECOVERY_TTL_SECONDS if k.startswith("recovery:") else OAUTH_TTL_SECONDS)
        }
        pool["items"][f"recovery:{attempt}"] = (now, verifier)


def _recovery_callback():
    """Exchange recovery PKCE code and create user-scoped recovery session."""
    attempt = st.query_params.get("recovery_attempt")
    if not attempt:
        return
    code = st.query_params.get("code")
    error = st.query_params.get("error")
    # Immediately remove the one-time code from the visible URL.
    st.query_params.clear()
    if error:
        st.error("再設定リンクが無効になっています。新しいメールを送信してください。")
        return
    # Important: do not consume stored verifier when there is no code.
    if not code:
        st.warning("認証コードが届いていません。新しい再設定メールからやり直してください。")
        return
    pool = _pending_oauth()
    with pool["lock"]:
        pending = pool["items"].pop(f"recovery:{attempt}", None)
    if not pending or time.monotonic() - pending[0] > RECOVERY_TTL_SECONDS:
        st.warning("再設定リンクの一時情報が失われたか、有効期限が切れました。新しいメールからやり直してください。")
        return
    try:
        api_key = st.secrets["SUPABASE_ANON_KEY"]
        api_url = st.secrets["SUPABASE_URL"].rstrip("/") + "/auth/v1/token"
        with httpx.Client(timeout=20) as http:
            response = http.post(
                api_url,
                headers={"apikey": api_key, "Content-Type": "application/json"},
                params={"grant_type": "pkce"},
                json={"auth_code": code, "code_verifier": pending[1]},
            )
        if response.is_error:
            st.error("認証コードを確認できませんでした。新しい再設定メールを送信してください。")
            st.caption(f"認証HTTPステータス: {response.status_code}")
            return
        session_data = response.json()
        access_token = session_data.get("access_token")
        refresh_token = session_data.get("refresh_token")
        if not access_token or not refresh_token:
            st.error("再設定用セッションを取得できませんでした。")
            return
        # Fresh client: keep existing users' Supabase sessions isolated.
        recovery_client = _new_client()
        recovery_client.auth.set_session(access_token, refresh_token)
        st.session_state.history_supabase_client = recovery_client
        st.session_state.history_password_recovery = True
        st.rerun()
    except Exception:
        st.error("パスワード再設定の認証に失敗しました。新しいメールでやり直してください。")


def _recovery_form():
    st.info("メールでの確認が完了しました。新しいパスワードを設定してください。")
    with st.form("history_new_password_form"):
        password1 = st.text_input("新しいパスワード（8文字以上）", type="password")
        password2 = st.text_input("新しいパスワード（確認）", type="password")
        submitted = st.form_submit_button("パスワードを変更する", use_container_width=True)
    if submitted:
        if len(password1) < 8:
            st.warning("パスワードは8文字以上で入力してください。")
        elif password1 != password2:
            st.warning("確認用パスワードが一致しません。")
        else:
            try:
                client().auth.update_user({"password": password1})
                st.session_state.history_password_recovery = False
                # Sign out the temporary recovery session to require normal login.
                client().auth.sign_out({"scope": "local"})
                st.session_state["history_password_reset_success"] = True
                st.rerun()
            except Exception as exc:
                _show_auth_error(exc)
    if st.button("再設定を中止", key="history_cancel_recovery"):
        try:
            client().auth.sign_out({"scope": "local"})
        except Exception:
            pass
        st.session_state.history_password_recovery = False
        st.rerun()


def user():
    db = client()
    if db is None:
        return None
    try:
        result = db.auth.get_user()
        return result.user if result else None
    except Exception:
        return None


def _show_auth_error(exc):
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    st.error("登録・ログインに失敗しました。")
    explanations = {
        "invalid_credentials": "メールアドレスまたはパスワードが一致しません。",
        "email_not_confirmed": "メールアドレスの認証が完了していません。",
        "user_already_exists": "このメールアドレスはすでに登録されている可能性があります。",
        "email_exists": "このメールアドレスはすでに登録されています。",
        "over_request_rate_limit": "試行回数が多いため一時的に制限されています。時間をおいて再試行してください。",
        "request_timeout": "通信がタイムアウトしました。時間をおいて再試行してください。",
    }
    if code in explanations:
        st.info(explanations[code])
    if code:
        st.caption(f"エラーコード: {code}")
    if status:
        st.caption(f"HTTPステータス: {status}")
    if not code and not status:
        st.caption(f"エラーの種類: {type(exc).__name__}")
    st.caption("※ パスワードやメール内の認証リンクは共有しないでください。")


def _show_signup_error(exc):
    """Explain duplicate signups when Supabase explicitly reports them.

    With email confirmations enabled, Supabase may mask whether an address exists.
    Never infer account existence from a user object or its identities.
    """
    code = getattr(exc, "code", None)
    if code in ("email_exists", "user_already_exists", "email_address_exists"):
        st.warning("このメールアドレスはすでに登録されています。")
        st.info("上の『登録済みの方（ログイン）』を押してください。パスワードを忘れた場合はログイン画面から再設定できます。")
    else:
        _show_auth_error(exc)


def auth_panel():
    """Optional login controls. Anonymous users can still diagnose plants."""
    st.subheader("💾 成長記録（任意）")
    if not configured():
        st.caption("保存機能は準備中です。登録なしの写真診断は引き続き利用できます。")
        return

    # Run during the existing auth_panel call; app.py need not change.
    _google_callback()
    _recovery_callback()
    if st.session_state.get("history_password_recovery"):
        _recovery_form()
        return
    if st.session_state.pop("history_password_reset_success", False):
        st.success("パスワードを変更しました。新しいパスワードでログインしてください。")
    current = user()
    if current:
        st.success("ログイン中")
        if st.button("🌱 保存した記録を見る", use_container_width=True):
            st.session_state.page = "history_calendar"
            st.rerun()
        if st.button("ログアウト", use_container_width=True):
            try:
                client().auth.sign_out()
            except Exception:
                st.error("ログアウトできませんでした。もう一度お試しください。")
                return
            st.session_state.pop("history_google_url", None)
            st.session_state.page = "select_user"
            st.rerun()
        return

    st.markdown("**アカウントがあると、写真と診断結果を保存して見返せます。**")
    st.caption("登録しなくても、写真のAI診断は無料で利用できます。")

    st.markdown("#### かんたんに始める")
    if st.button("🔐 Googleで登録・ログイン", key="history_google_start", use_container_width=True):
        try:
            st.session_state.history_google_url = _make_google_link()
        except Exception as exc:
            _show_auth_error(exc)
    if st.session_state.get("history_google_url"):
        st.link_button(
            "Googleの認証画面へ進む",
            st.session_state.history_google_url,
            use_container_width=True,
        )
        st.caption("Googleで認証すると、植物診断ラボに戻ります。")

    st.divider()
    st.markdown("#### メールアドレスで利用する")
    if "history_auth_view" not in st.session_state:
        st.session_state.history_auth_view = "register"

    left, right = st.columns(2)
    with left:
        if st.button("🌱 はじめての方（新規登録）", key="history_show_register", use_container_width=True):
            st.session_state.history_auth_view = "register"
    with right:
        if st.button("🔑 登録済みの方（ログイン）", key="history_show_login", use_container_width=True):
            st.session_state.history_auth_view = "login"

    view = st.session_state.history_auth_view
    if view == "register":
        st.markdown("**新規登録（無料）**")
        st.caption("① メールとパスワードを入力 → ② 確認メールのリンクを開く → ③ この画面でログイン")
        if st.session_state.get("history_signup_notice"):
            st.success("📩 登録手続きを受け付けました。")
            st.info("初めて登録する方は、確認メールが届いたらメール内のリンクを開いてください。")
            st.warning(
                "すでに登録したことがある方は、新規登録は不要です。"
                "上の『🔑 登録済みの方（ログイン）』からログインしてください。"
                "パスワードを忘れた場合は、ログイン画面から再設定できます。"
            )
            if st.button("🔑 ログイン画面へ進む", key="history_after_signup_login", use_container_width=True):
                st.session_state.history_auth_view = "login"
                st.session_state.pop("history_signup_notice", None)
                st.rerun()
        with st.form("history_register_form"):
            email = st.text_input("メールアドレス", key="history_register_email", placeholder="example@gmail.com")
            password = st.text_input("パスワード（8文字以上）", key="history_register_password", type="password")
            password_again = st.text_input("パスワード（確認用）", key="history_register_password_again", type="password")
            submitted = st.form_submit_button("無料で新規登録する", use_container_width=True)
        if submitted:
            email = email.strip()
            if not email or "@" not in email:
                st.warning("メールアドレスを確認してください。")
            elif len(password) < 8:
                st.warning("パスワードは8文字以上にしてください。")
            elif password != password_again:
                st.warning("確認用パスワードが一致しません。")
            else:
                try:
                    response = client().auth.sign_up({"email": email, "password": password})
                    if response.session:
                        st.session_state.pop("history_signup_notice", None)
                        st.rerun()
                    else:
                        st.session_state.history_signup_notice = True
                        st.rerun()
                except Exception as exc:
                    _show_signup_error(exc)
    else:
        st.markdown("**メールアドレスでログイン**")
        with st.form("history_login_form"):
            email = st.text_input("登録したメールアドレス", key="history_login_email")
            password = st.text_input("パスワード", type="password", key="history_login_password")
            submitted = st.form_submit_button("ログインする", use_container_width=True)
        if submitted:
            if not email.strip() or not password:
                st.warning("メールアドレスとパスワードを入力してください。")
            else:
                try:
                    response = client().auth.sign_in_with_password({"email": email.strip(), "password": password})
                    if not response.session:
                        st.warning("ログインセッションを取得できませんでした。")
                    else:
                        st.session_state.pop("history_signup_notice", None)
                        st.rerun()
                except Exception as exc:
                    _show_auth_error(exc)

        with st.expander("🔑 パスワードを忘れた方はこちら"):
            with st.form("history_recovery_email_form"):
                recovery_email = st.text_input("登録したメールアドレス", key="history_recovery_email")
                send = st.form_submit_button("再設定メールを送る", use_container_width=True)
            if send:
                if not recovery_email.strip() or "@" not in recovery_email:
                    st.warning("メールアドレスを確認してください。")
                else:
                    try:
                        _send_recovery_email(recovery_email.strip())
                        st.info("登録済みのアドレスなら再設定メールが届きます。新しいメールのリンクを開いてください。")
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 429:
                            st.warning("メール送信回数の上限に達しました。時間を空けてからお試しください。")
                        else:
                            st.error("再設定メールを送信できませんでした。")
                    except Exception as exc:
                        _show_auth_error(exc)

    st.caption("※ 保存機能は任意です。ログインせずに診断だけ利用することもできます。")


def save(record, source_image):
    db, current = client(), user()
    if db is None or current is None:
        raise PermissionError("ログインが必要です。")
    record_id = str(uuid.uuid4())
    photo_path = None
    if source_image:
        with Image.open(io.BytesIO(source_image)) as img:
            img = img.convert("RGB")
            img.thumbnail((1600, 1600))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=82, optimize=True)
        photo_path = f"{current.id}/{record_id}.jpg"
        db.storage.from_(BUCKET).upload(
            photo_path,
            buffer.getvalue(),
            {"content-type": "image/jpeg", "upsert": "false"},
        )
    try:
        db.table(TABLE).insert(
            {"id": record_id, "user_id": str(current.id), "record": record, "photo_path": photo_path}
        ).execute()
    except Exception:
        if photo_path:
            try:
                db.storage.from_(BUCKET).remove([photo_path])
            except Exception:
                pass
        raise
    return record_id


def list_history():
    db, current = client(), user()
    if db is None or current is None:
        return []
    rows = (
        db.table(TABLE)
        .select("id,created_at,record,photo_path")
        .eq("user_id", str(current.id))
        .order("created_at", desc=False)
        .limit(200)
        .execute()
        .data or []
    )
    merged = []
    for row in rows:
        entry = dict(row.get("record") or {})
        entry["id"] = row["id"]
        entry["created_at"] = row["created_at"]
        entry["whole_image_path"] = ""
        if row.get("photo_path"):
            try:
                signed = db.storage.from_(BUCKET).create_signed_url(row["photo_path"], 600)
                entry["whole_image_path"] = signed.get("signedURL") or signed.get("signedUrl") or ""
            except Exception:
                pass
        merged.append(entry)
    return merged


def delete_record(record_id):
    db, current = client(), user()
    if db is None or current is None:
        raise PermissionError("ログインが必要です。")
    rows = (
        db.table(TABLE)
        .select("photo_path")
        .eq("id", record_id)
        .eq("user_id", str(current.id))
        .execute()
        .data or []
    )
    if not rows:
        return
    db.table(TABLE).delete().eq("id", record_id).eq("user_id", str(current.id)).execute()
    if rows[0].get("photo_path"):
        db.storage.from_(BUCKET).remove([rows[0]["photo_path"]])
