"""既存のTeachable Machineモデルによる写真の一括*仮*分類。

予測ラベルを正解として自動公開しない。利用者が確認・訂正してから
training_photos へ pending で保存する。既存の3モデルだけを使用する。
"""
import io
import logging
from pathlib import Path

import numpy as np
import streamlit as st
from PIL import Image, ImageOps

import history_cloud
import training_gallery

LOGGER = logging.getLogger(__name__)
MODEL_ROOT = Path(__file__).resolve().parent / "models"
MAX_FILES = 8  # Community Cloud のCPU制限を考慮
MAX_BYTES = 10 * 1024 * 1024
MODEL_NAMES = {"whole": "株全体", "leaf": "葉", "fruit": "実"}


def _predict_one(raw: bytes, key: str, load_tm_model, load_tm_labels):
    if len(raw) > MAX_BYTES:
        raise ValueError("10MB以下の写真を選んでください。")
    image = training_gallery._image_bytes(io.BytesIO(raw))
    with Image.open(io.BytesIO(image)) as src:
        square = ImageOps.fit(src.convert("RGB"), (224, 224), method=Image.Resampling.LANCZOS)
        tensor = np.expand_dims(np.asarray(square, dtype=np.float32) / 127.5 - 1.0, 0)
    folder = MODEL_ROOT / key
    weights, label_file = folder / "keras_model.h5", folder / "labels.txt"
    if not weights.is_file() or not label_file.is_file():
        raise FileNotFoundError(f"{key} のモデルファイルがありません。")
    model = load_tm_model(key, weights.stat().st_mtime)
    labels = load_tm_labels(key, label_file.stat().st_mtime)
    scores = np.asarray(model.predict(tensor, verbose=0)[0], dtype=float)
    if len(labels) != len(scores) or not np.isfinite(scores).all():
        raise ValueError("モデル出力と分類名が一致しません。")
    best = int(np.argmax(scores))
    return image, labels[best], float(scores[best]), labels


def show(load_tm_model, load_tm_labels):
    st.title("📦 写真をまとめてAI仮分類")
    st.write("分類されていない過去の写真をまとめて選び、既存モデルで分類候補を出します。")
    st.info("AIの判定は正解ではありません。すべての写真を確認・修正してから、審査待ちとして保存してください。")
    current = history_cloud.user()
    if current is None:
        st.warning("利用には画面上部からのログインが必要です。")
        return
    category = st.selectbox("どのモデルで分類する？", list(MODEL_NAMES),
                            format_func=lambda k: MODEL_NAMES[k], key="bulk_model_choice")
    st.caption("まずは1モデルずつ分類します。実が写っていない写真は、実の成熟度を正しく分類できない場合があります。")
    uploads = st.file_uploader("写真をまとめて選択（JPEG・PNG）", type=["jpg", "jpeg", "png"],
                               accept_multiple_files=True, key="bulk_uploads")
    if uploads and len(uploads) > MAX_FILES:
        st.warning(f"一度に分類できるのは最大{MAX_FILES}枚です。写真を減らしてください。")
    if st.button("AIで仮分類する", disabled=not uploads or len(uploads) > MAX_FILES,
                 key="bulk_predict", use_container_width=True):
        results = []
        with st.spinner("写真を分類しています…"):
            for idx, photo in enumerate(uploads):
                try:
                    jpeg, label, score, labels = _predict_one(photo.getvalue(), category, load_tm_model, load_tm_labels)
                    results.append({"id": f"{idx}_{photo.name}", "filename": photo.name,
                                    "jpeg": jpeg, "suggested": label, "score": score})
                except Exception as exc:
                    LOGGER.warning("Bulk classification skipped a file: %s (%s)", photo.name, type(exc).__name__)
                    st.warning(f"{photo.name} は分類できませんでした。画像形式やサイズを確認してください。")
        st.session_state["bulk_result_set"] = {"category": category, "rows": results}
        st.success(f"{len(results)}枚の分類候補を作りました。下で確認してください。")

    batch = st.session_state.get("bulk_result_set")
    if not batch or not batch["rows"]:
        return
    if batch["category"] != category:
        st.warning("モデルを変更しました。新しいモデルで『AIで仮分類する』を押してください。")
        return
    labels = training_gallery._labels_from_local_model(category)
    st.subheader("📝 分類結果を確認・修正")
    st.caption("下の選択肢は実際の labels.txt の分類名。画像を見て必ず確認してください。")
    with st.form("bulk_review_form"):
        corrected = []
        for idx, row in enumerate(batch["rows"]):
            img_col, edit_col = st.columns([1, 2], gap="medium")
            with img_col:
                st.image(row["jpeg"], caption=row["filename"], use_container_width=True)
            with edit_col:
                st.markdown(f"**写真 {idx + 1}**")
                st.caption(f"AIの候補：{row['suggested']}（参考スコア {row['score']:.0%}）")
                options = labels if row["suggested"] in labels else [row["suggested"]] + labels
                corrected.append(st.selectbox("確認した分類", options,
                                               index=options.index(row["suggested"]), key=f"bulk_correct_{idx}_{category}"))
            st.divider()
        description = st.text_input("共通の撮影状況（任意）", max_chars=300,
                                    placeholder="例：2026年夏に撮影したミニトマト")
        st.warning("写真は審査後に他の利用者へ公開され、AI学習用としてダウンロードされる可能性があります。顔・氏名・学校名などが映る写真は登録しないでください。")
        consent = st.checkbox("写真の公開・再学習利用・ダウンロードに同意し、全写真の分類を確認しました")
        submitted = st.form_submit_button("確認した写真を審査待ちで一括登録", use_container_width=True)
    if submitted:
        if not consent:
            st.error("登録前に分類を確認し、公開・学習利用への同意が必要です。")
            return
        successful = 0
        for row, label in zip(batch["rows"], corrected):
            try:
                # 既存の写真登録処理と同じStorage・テーブルを使う
                training_gallery._register(current, category, None, label, description.strip(), io.BytesIO(row["jpeg"]))
                successful += 1
            except Exception:
                LOGGER.exception("Failed saving reviewed image")
                break  # 重複登録を避けるため保存を中断する
        if successful == len(batch["rows"]):
            st.session_state.pop("bulk_result_set", None)
            st.success(f"{successful}枚を審査待ちで登録しました。写真データベースで確認できます。")
        else:
            # 保存済みの行を除き、残りを再送できるようにする
            batch["rows"] = batch["rows"][successful:]
            st.error(f"{successful}枚は登録済みです。残り{len(batch['rows'])}枚の登録に失敗しました。接続・RLSを確認してください。")

    if st.button("📷 写真データベースに戻る", key="bulk_back_to_board"):
        st.session_state.page = "training_gallery"
        st.rerun()
