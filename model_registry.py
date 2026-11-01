"""Teachable Machine model proposals backed by the existing Supabase RLS.

No model supplied by a user is downloaded or executed here. Proposals do not
modify the production diagnosis models, and approval is managed separately.
"""
import re

import streamlit as st
import history_cloud

MODEL_URL_PATTERN = re.compile(
    r"^https://teachablemachine\.withgoogle\.com/models/[A-Za-z0-9_-]+/?$"
)
CATEGORIES = {
    "whole": "株全体",
    "leaf": "葉",
    "fruit": "実",
    "pest": "病害虫",
    "other": "その他（新しい診断項目）",
}
STATUSES = {"pending": "審査待ち", "approved": "承認済み", "rejected": "不採用"}


def _safe_error(message):
    # Do not show raw DB/API responses that might expose account information.
    st.error(message)


def _list_models():
    # Row-level security restricts this to the current user's proposals and
    # approved models. Never use a service-role key in a public Streamlit app.
    response = (
        history_cloud.client().table("ai_models")
        .select("id,model_name,model_url,model_type,category,description,labels,status,created_at,training_image_count,validation_accuracy,validation_image_count")
        .order("created_at", desc=True).limit(100).execute()
    )
    return response.data or []


def show():
    st.title("🧠 AIモデルを登録・確認する")
    st.write("Teachable Machineで作成したモデルを提案できます。既存モデルの改良も、新しい診断項目の追加も歓迎します。")
    st.info("登録したモデルは審査待ちになります。現在の全体・葉・実の診断モデルは自動では変更されません。")
    current = history_cloud.user()
    if current is None:
        st.warning("AIモデルの登録・一覧表示にはログインが必要です。画面上部の「会員登録・ログイン」からログインしてください。")
        return
    if not history_cloud.configured():
        st.error("Supabaseが設定されていません。")
        return

    with st.expander("➕ 新しいAIモデルを提案する", expanded=True):
        with st.form("ai_model_proposal_form", clear_on_submit=True):
            model_name = st.text_input("モデル名 *", max_chars=120, placeholder="例：葉の黄化判定モデル Ver.2")
            model_type_display = st.radio("登録するモデルの種類 *", ["既存モデルの改良", "新しい診断項目"], horizontal=True)
            category = st.selectbox("診断分野 *", options=list(CATEGORIES), format_func=lambda k: CATEGORIES[k])
            url = st.text_input("Teachable Machineの公開モデルURL *", max_chars=300, placeholder="https://teachablemachine.withgoogle.com/models/xxxxxx/")
            description = st.text_area("モデルの説明", max_chars=1200, placeholder="どんな写真で学習したか、どの状態を分類するかなど")
            labels_raw = st.text_input("分類名（任意・カンマ区切り）", max_chars=800, placeholder="良好, 黄化, 虫食い")
            count = st.number_input("学習画像の枚数（任意・不明なら0）", min_value=0, max_value=1000000, step=1, value=0)
            st.caption("分類名・学習枚数は登録者の申告内容です。精度が検証されたことを意味しません。")
            submitted = st.form_submit_button("審査待ちとして登録する", use_container_width=True)
        if submitted:
            name = model_name.strip()
            cleaned_url = url.strip()
            labels = [x.strip() for x in labels_raw.replace("、", ",").split(",") if x.strip()]
            if not (1 <= len(name) <= 120):
                st.warning("モデル名を入力してください。")
            elif not MODEL_URL_PATTERN.fullmatch(cleaned_url):
                st.warning("Teachable Machineの公開モデルURLを確認してください。")
            elif len(labels) > 30 or any(len(label) > 80 for label in labels):
                st.warning("分類名は最大30個・各80文字以内にしてください。")
            elif model_type_display == "既存モデルの改良" and category not in ("whole", "leaf", "fruit"):
                st.warning("既存モデルの改良では、株全体・葉・実から選んでください。")
            else:
                payload = {
                    "user_id": str(current.id),
                    "model_name": name,
                    "model_url": cleaned_url,
                    "model_type": "improvement" if model_type_display == "既存モデルの改良" else "new",
                    "category": category,
                    "description": description.strip(),
                    "labels": labels,
                    "training_image_count": int(count) if count else None,
                    "status": "pending",
                }
                try:
                    history_cloud.client().table("ai_models").insert(payload).execute()
                except Exception:
                    _safe_error("モデルを登録できませんでした。ai_models テーブルとRLS設定、通信状況をご確認ください。")
                else:
                    st.success("モデルの提案を登録しました。現在の診断には反映されていません。")

    st.subheader("📚 登録モデル一覧")
    st.caption("自分が登録したモデルと承認済みモデルだけが表示されます。")
    try:
        rows = _list_models()
    except Exception:
        _safe_error("モデル一覧を取得できませんでした。ai_models テーブルとRLS設定をご確認ください。")
        return
    if not rows:
        st.info("表示できるモデルはまだありません。最初のモデルを登録してみよう！")
        return
    for entry in rows:
        title = entry.get("model_name", "名称未設定")
        with st.expander(f"{STATUSES.get(entry.get('status'), '状態不明')}｜{title}"):
            st.write(f"**診断分野:** {CATEGORIES.get(entry.get('category'), entry.get('category', '不明'))}")
            st.write(f"**種類:** {'改良モデル' if entry.get('model_type') == 'improvement' else '新しい診断項目'}")
            st.write(f"**説明:** {entry.get('description') or '説明なし'}")
            st.write(f"**分類名（申告）:** {', '.join(entry.get('labels') or []) or '未登録'}")
            if entry.get('training_image_count') is not None:
                st.write(f"**学習画像枚数（申告）:** {entry['training_image_count']}")
            st.code(entry.get("model_url", ""), language=None)
            st.caption("モデルのURL・説明は投稿者が入力した情報です。外部モデルの安全性や精度は未検証です。")
