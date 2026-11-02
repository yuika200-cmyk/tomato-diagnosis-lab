"""Opt-in tomato training-image submissions and approved gallery.

Requires public.training_photos and private Storage bucket training-photos, with RLS.
No service-role key; use the existing per-user Supabase client.
"""
import io
import uuid
from PIL import Image, ImageOps, UnidentifiedImageError
import streamlit as st
import history_cloud

TABLE = "training_photos"
BUCKET = "training-photos"
CATEGORIES = {"whole": "株全体", "leaf": "葉", "fruit": "実", "pest": "病害虫", "other": "その他"}
DEFAULT_LABELS = {
    "whole": ["良好", "葉が重なっている", "誘引必要"],
    "leaf": ["良好", "葉が黄色い", "白い斑点", "虫食い", "しおれている"],
    "fruit": ["成長途中", "成熟中", "収穫間近"],
    "pest": ["虫食い", "害虫が見られる", "その他"],
    "other": ["その他"],
}
STATUSES = {"pending": "審査待ち", "approved": "公開済み", "rejected": "不採用"}
MAX_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000


def _photo_bytes(file):
    """Re-encode image and strip EXIF/GPS metadata."""
    data = file.getvalue()
    if not data or len(data) > MAX_BYTES:
        raise ValueError("写真のサイズは10MB以下にしてください。")
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.width * img.height > 25_000_000:
                raise ValueError("画像が大きすぎます。")
            rgb = ImageOps.exif_transpose(img).convert("RGB")
            rgb.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            rgb.save(output, "JPEG", quality=85, optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("写真を読み込めません。JPEGまたはPNGを選んでください。") from exc


def _register(current, category, label, description, photo):
    db = history_cloud.client()
    photo_id = str(uuid.uuid4())
    photo_path = f"{current.id}/{photo_id}.jpg"
    db.storage.from_(BUCKET).upload(photo_path, photo,
        {"content-type": "image/jpeg", "upsert": "false"})
    try:
        db.table(TABLE).insert({
            "id": photo_id, "user_id": str(current.id),
            "category": category, "label": label,
            "description": description, "image_path": photo_path,
            "consent_to_share": True, "status": "pending",
        }).execute()
    except Exception:
        # A Storage DELETE policy is not yet available. The owner should inspect
        # orphaned objects if a metadata write fails; do not silently claim cleanup.
        raise


def show():
    st.title("📷 学習用写真データベース")
    st.write("撮影したミニトマトの写真を分類して提供し、AIモデルを改善するための写真を集める場所です。")
    st.info("登録写真は審査待ちになります。承認されるまではほかの利用者には表示されません。")

    current = history_cloud.user()
    if current is None:
        st.warning("写真の登録・閲覧にはログインが必要です。上部のログイン欄からログインしてください。")
        return

    with st.expander("➕ 学習用写真を登録する", expanded=True):
        category = st.selectbox("写真の分野", list(CATEGORIES), format_func=lambda key: CATEGORIES[key])
        with st.form("training_photo_submission", clear_on_submit=True):
            label_choice = st.selectbox("写真の状態（分類名）", DEFAULT_LABELS[category] + ["自分で分類名を入力"])
            custom_label = st.text_input("新しい分類名（選択した場合のみ）", max_chars=100)
            description = st.text_area("補足・撮影状況（任意）", max_chars=1000,
                placeholder="例：下の葉が黄色い。日なたで撮影。")
            uploaded = st.file_uploader("学習用の写真", type=["jpg", "jpeg", "png"], key="training_photo_file")
            consent = st.checkbox("この写真を承認後にほかの利用者へ公開し、AI学習用に利用・ダウンロードされることに同意します。自分が提供してよい写真だけ登録します。")
            st.caption("人物・氏名・位置情報などが写る写真は登録しないでください。画像のEXIF位置情報は保存時に除去します。")
            submitted = st.form_submit_button("審査待ちとして写真を登録", use_container_width=True)
        if submitted:
            label = (custom_label if label_choice == "自分で分類名を入力" else label_choice).strip()
            if uploaded is None:
                st.warning("写真を選んでください。")
            elif not label or len(label) > 100:
                st.warning("分類名を入力してください。")
            elif not consent:
                st.warning("学習・共有への同意を確認してください。")
            else:
                try:
                    photo_data = _photo_bytes(uploaded)
                    _register(current, category, label, description.strip(), photo_data)
                except ValueError as exc:
                    st.warning(str(exc))
                except Exception:
                    st.error("保存できませんでした。Storageのアクセス制限・training_photosテーブル・通信状況を確認してください。")
                else:
                    st.success("写真を登録しました！ 管理者の確認後に公開されます。")

    st.subheader("🖼️ 登録された写真を探す")
    st.caption("自分の写真と、承認済みの写真を閲覧できます。審査中の他人の写真は表示されません。")
    category_filter = st.selectbox("分野で絞り込み", ["all"] + list(CATEGORIES),
        format_func=lambda v: "すべて" if v == "all" else CATEGORIES[v], key="training_filter_category")
    try:
        query = (history_cloud.client().table(TABLE)
            .select("id,user_id,category,label,description,image_path,status,created_at")
            .order("created_at", desc=True).limit(120))
        if category_filter != "all":
            query = query.eq("category", category_filter)
        rows = query.execute().data or []
    except Exception:
        st.error("一覧を読み込めませんでした。テーブル設定を確認してください。")
        return
    if not rows:
        st.info("該当する写真はまだありません。")
        return
    counts = {}
    for row in rows:
        key = (row["category"], row["label"])
        counts[key] = counts.get(key, 0) + 1
    st.markdown("**写真の分類と件数（表示対象の最大120件）**")
    for (cat, label), count in sorted(counts.items()):
        st.write(f"{CATEGORIES.get(cat, cat)} ／ {label}：{count}枚")

    for start in range(0, len(rows), 3):
        columns = st.columns(3)
        for col, item in zip(columns, rows[start:start+3]):
            with col:
                try:
                    data = history_cloud.client().storage.from_(BUCKET).download(item["image_path"])
                    st.image(data, use_container_width=True)
                except Exception:
                    st.caption("画像を表示できませんでした。")
                    continue
                st.write(f"**{CATEGORIES.get(item['category'], item['category'])}／{item['label']}**")
                st.caption(STATUSES.get(item["status"], "状態不明"))
                if item.get("description"):
                    st.caption(item["description"])
                if item["status"] == "approved":
                    st.download_button("学習用に写真を保存", data=data,
                        file_name=f"tomato_{item['id']}.jpg", mime="image/jpeg",
                        key=f"download_training_{item['id']}", use_container_width=True)
