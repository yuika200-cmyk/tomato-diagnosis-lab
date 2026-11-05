"""Teachable Machine-style photo board for the existing tomato diagnosis app.

Photos are catalogued independently of the trained model weights.  Built-in model
photos have model_id=None; submitted model proposals have a specific model_id.
No user-submitted model is executed by this module.
"""
from __future__ import annotations

import io
import uuid
import zipfile
from collections import Counter
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError
import history_cloud

TABLE = "training_photos"
BUCKET = "training-photos"
MODEL_TABLE = "ai_models"
APP_DIR = Path(__file__).resolve().parent
MODEL_DIR = APP_DIR / "models"
CATEGORIES = {"whole": "株全体", "leaf": "葉", "fruit": "実", "pest": "病害虫", "other": "その他"}
FALLBACK = {
    "whole": ["良好", "葉が重なっている", "誘引必要"],
    "leaf": ["良好", "葉が黄色い", "白い斑点が見られる", "虫食い", "しおれている"],
    "fruit": ["成長途中", "成熟中", "収穫間近"],
}
EXPLAIN = {
    "良好": "状態が分かる、ぶれやぼけの少ない写真",
    "葉が黄色い": "黄色くなっている部分が確認できる写真",
    "虫食い": "虫に食べられた跡が確認できる写真",
    "収穫間近": "実の色がはっきり確認できる写真",
    "誘引必要": "茎の傾きや支柱との位置関係が分かる写真",
}
STATUS = {"pending": "審査待ち", "approved": "公開済み", "rejected": "不採用"}
MAX_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000


def _labels_from_local_model(category: str) -> list[str]:
    path = MODEL_DIR / category / "labels.txt"
    if not path.is_file():
        return FALLBACK.get(category, [])
    try:
        result = []
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            name = parts[1] if len(parts) == 2 and parts[0].isdigit() else line
            if name not in result:
                result.append(name)
        return result[:60] or FALLBACK.get(category, [])
    except (OSError, UnicodeError):
        return FALLBACK.get(category, [])


def _image_bytes(file) -> bytes:
    source = file.getvalue()
    if not source or len(source) > MAX_BYTES:
        raise ValueError("10MB以下の写真を選んでください。")
    try:
        with Image.open(io.BytesIO(source)) as im:
            if im.width * im.height > 25_000_000:
                raise ValueError("画素数が大きすぎます。")
            im.load()
            image = ImageOps.exif_transpose(im).convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, "JPEG", quality=85, optimize=True)
            return output.getvalue()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError("画像を読み込めません。JPEG・PNG形式を選んでください。") from exc


def _register(current, category: str, model_id: str | None, label: str, description: str, uploaded) -> None:
    db = history_cloud.client()
    photo_id = str(uuid.uuid4())
    photo_path = f"{current.id}/{photo_id}.jpg"
    image_data = _image_bytes(uploaded)
    db.storage.from_(BUCKET).upload(photo_path, image_data,
        {"content-type": "image/jpeg", "upsert": "false"})
    # Insert only after successful Storage upload.  Failed DB insertion leaves an
    # orphan, which an admin can clean up (owner DELETE RLS is not configured).
    payload = {"id": photo_id, "user_id": str(current.id), "category": category,
               "label": label, "description": description, "image_path": photo_path,
               "consent_to_share": True, "status": "pending", "model_id": model_id}
    db.table(TABLE).insert(payload).execute()


def _models():
    """Built-in models + RLS-visible proposed or approved models."""
    out = [
        {"id": None, "category": key, "name": f"{value}（基本モデル）",
         "labels": _labels_from_local_model(key), "status": "built-in"}
        for key, value in list(CATEGORIES.items())[:3]
    ]
    rows = (history_cloud.client().table(MODEL_TABLE)
            .select("id,model_name,category,labels,status")
            .order("created_at", desc=True).limit(150).execute().data or [])
    for row in rows:
        out.append({"id": row["id"], "category": row["category"],
                    "name": row["model_name"], "labels": row.get("labels") or [],
                    "status": row.get("status", "pending")})
    return out


def _photos(model):
    db = history_cloud.client()
    q = db.table(TABLE).select("id,user_id,category,label,description,image_path,status,created_at")
    q = q.eq("category", model["category"])
    q = q.is_("model_id", "null") if model["id"] is None else q.eq("model_id", model["id"])
    return q.order("created_at", desc=True).limit(500).execute().data or []


def _photo_preview(row):
    return history_cloud.client().storage.from_(BUCKET).download(row["image_path"])


def _download_zip(rows, category, label) -> bytes:
    """Only approved photos may be shared as learning data."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in rows:
            if item.get("status") != "approved":
                continue
            try:
                content = _photo_preview(item)
                archive.writestr(f"{category}/{label}/{item['id']}.jpg", content)
            except Exception:
                continue
    return output.getvalue()


def show():
    st.title("📷 AIモデル・学習写真データベース")
    st.write("Teachable Machineのクラス別に、必要な写真・登録枚数・実際の写真を確認できます。")
    st.info("ここに登録した写真は自動でTeachable Machineに追加されません。承認後、学習用に取得して再学習します。")

    current = history_cloud.user()
    if current is None:
        st.warning("写真の登録・一覧を見るには、ページ上部からログインしてください。")
        return
    if not history_cloud.configured():
        st.error("Supabaseの接続設定がありません。")
        return
    try:
        models = _models()
    except Exception:
        st.error("モデル一覧を読み込めませんでした。Supabaseの接続と ai_models テーブルを確認してください。")
        return

    model_options = {f"{i}: {m['name']}": m for i, m in enumerate(models)}
    selected = st.selectbox("📚 管理するAIモデルを選ぶ", list(model_options),
                            format_func=lambda v: model_options[v]["name"],
                            key="photo_board_model")
    model = model_options[selected]
    st.caption(f"分野：{CATEGORIES.get(model['category'], model['category'])}　｜　"
               f"モデルの状態：{'基本モデル' if model['status']=='built-in' else STATUS.get(model['status'], '審査待ち')}")
    try:
        photos = _photos(model)
    except Exception:
        st.error("写真を読み込めませんでした。model_id列の追加SQLが実行済みか確認してください。")
        return

    # The category labels come from actual built-in labels.txt or a proposed
    # model's declared labels.  Photos already uploaded with other names also appear.
    labels = []
    for value in model["labels"] + [r["label"] for r in photos]:
        if value and value not in labels:
            labels.append(value)

    counts = Counter(r["label"] for r in photos)
    approved_count = sum(r["status"] == "approved" for r in photos)
    col1, col2, col3 = st.columns(3)
    col1.metric("分類数", len(labels))
    col2.metric("見られる写真", len(photos))
    col3.metric("公開済み写真", approved_count)
    if len(photos) == 500:
        st.warning("表示は最新500枚まで。将来はページ分割で全件を閲覧できるようにします。")

    with st.expander("➕ 新しい分類名で写真を登録する", expanded=not labels):
        with st.form("board_custom_class_form", clear_on_submit=True):
            new_label = st.text_input("追加したい分類名", max_chars=100, placeholder="例：葉先が枯れている")
            upload = st.file_uploader("分類に登録する写真", type=["jpg", "jpeg", "png"], key="board_new_class_file")
            desc = st.text_area("撮影状況・補足（任意）", max_chars=1000, key="board_new_class_desc")
            consent = st.checkbox("承認後の写真公開・AI学習への利用とダウンロードに同意します。")
            submitted = st.form_submit_button("この分類に写真を登録", use_container_width=True)
        if submitted:
            name = new_label.strip()
            if not name:
                st.warning("分類名を入力してください。")
            elif upload is None:
                st.warning("写真を選んでください。")
            elif not consent:
                st.warning("公開・学習利用への同意を確認してください。")
            else:
                try:
                    _register(current, model["category"], model["id"], name, desc.strip(), upload)
                except ValueError as exc:
                    st.warning(str(exc))
                except Exception:
                    st.error("登録できませんでした。Storageとテーブルのアクセス権を確認してください。")
                else:
                    st.success("審査待ちとして登録しました。")
                    st.rerun()

    if not labels:
        st.info("まだ分類名がありません。上から最初の写真を登録してみよう。")
        return

    st.subheader("🗂️ 分類別の写真一覧")
    st.caption("登録枚数は、ログイン中の本人の写真＋承認済み写真の合計です。未承認の他人の写真は表示されません。")
    for idx, label in enumerate(labels):
        group = [r for r in photos if r["label"] == label]
        approved = [r for r in group if r["status"] == "approved"]
        # Image thumbnails only for the selected category, to avoid fetching
        # hundreds of images when loading the page.
        with st.container(border=True):
            st.markdown(f"### {label}")
            st.caption(f"{counts.get(label, 0)}枚の画像サンプル（公開済み {len(approved)}枚）")
            st.caption(EXPLAIN.get(label, "分類が分かるように、明るくピントの合った写真を撮影してください。"))
            with st.expander("📸 写真を見る", expanded=False):
                if not group:
                    st.caption("まだ登録写真がありません。")
                else:
                    display_count = st.selectbox("表示する枚数", [6, 12, 24], key=f"board_count_{idx}")
                    visible = group[:display_count]
                    for offset in range(0, len(visible), 4):
                        columns = st.columns(4)
                        for column, item in zip(columns, visible[offset:offset + 4]):
                            with column:
                                try:
                                    data = _photo_preview(item)
                                    st.image(data, use_container_width=True)
                                    if item["status"] == "approved":
                                        st.download_button("写真を保存", data=data,
                                            file_name=f"{item['id']}.jpg", mime="image/jpeg",
                                            key=f"board_download_{item['id']}", use_container_width=True)
                                except Exception:
                                    st.caption("写真を取得できませんでした")
                                st.caption(STATUS.get(item["status"], "状態不明"))
                                if item.get("description"):
                                    st.caption(item["description"][:120])
                    if len(group) > display_count:
                        st.caption(f"残り {len(group)-display_count} 枚。表示枚数を変更できます。")
                if approved:
                    zip_key = f"board_zip_content_{selected}_{idx}"
                    if st.button("📦 公開済み写真のZIPを準備", key=f"board_prepare_{idx}"):
                        with st.spinner("写真をまとめています..."):
                            st.session_state[zip_key] = _download_zip(approved, model["category"], label)
                    if st.session_state.get(zip_key):
                        st.download_button("ZIPをダウンロード", data=st.session_state[zip_key],
                            file_name=f"tomato_{model['category']}_class_{idx}.zip",
                            mime="application/zip", key=f"board_zip_{idx}")
            with st.expander("➕ この分類に写真を追加", expanded=False):
                with st.form(f"board_upload_{idx}", clear_on_submit=True):
                    image_file = st.file_uploader("写真（JPEG・PNG、10MBまで）", type=["jpg", "jpeg", "png"],
                                                  key=f"board_image_{idx}")
                    note = st.text_area("撮影状況（任意）", key=f"board_note_{idx}", max_chars=1000)
                    agree = st.checkbox("承認後の公開・学習利用・ダウンロードに同意します。", key=f"board_agree_{idx}")
                    submit = st.form_submit_button("審査待ちとして写真を登録", use_container_width=True)
                if submit:
                    if image_file is None:
                        st.warning("写真を選んでください。")
                    elif not agree:
                        st.warning("公開・学習利用への同意を確認してください。")
                    else:
                        try:
                            _register(current, model["category"], model["id"], label, note.strip(), image_file)
                        except ValueError as exc:
                            st.warning(str(exc))
                        except Exception:
                            st.error("登録できませんでした。接続設定・RLSを確認してください。")
                        else:
                            st.success("審査待ちとして登録しました。")
                            st.rerun()
    st.caption("写真はモデル本体から抽出したものではありません。学習写真を別途登録・分類して管理します。"
               " 顔・氏名・学校名などが写り込んだ写真は登録しないでください。")
