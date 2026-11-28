import os
import io
import zipfile
import base64
import logging
import warnings

import csv
import time
from datetime import date, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from html import escape
import history_cloud
import history_note_sync
import auth_screen
import model_registry
import registered_model_diagnosis
import training_gallery
import bulk_classifier

LOGGER = logging.getLogger(__name__)
APP_DIR = Path(__file__).resolve().parent
# Public edition intentionally has no server-side user history, including
# when a deployment accidentally sets ENABLE_SERVER_HISTORY=1.
ENABLE_SERVER_HISTORY = False
MAX_IMAGE_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000
register_heif_opener()
SUPPORTED_UPLOAD_TYPES = ["jpg", "jpeg", "png", "heic", "heif"]



# =========================================================
# ページ設定
# =========================================================
st.set_page_config(
    page_title="植物診断ラボ",
    page_icon="🌱",
    layout="wide",
)

# ホーム画面から診断・記録・AI改善機能へ移動できるため、
# 重複するサイドバーのナビゲーションは表示しません。


# =========================================================
# 公開版は個人情報を収集しません。
# =========================================================
STUDENTS = {}


# =========================================================
# 保存設定
# =========================================================
USER_DATA_DIR = APP_DIR / "user_data"
if ENABLE_SERVER_HISTORY:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_COLUMNS = [
    "created_at",
    "grade",
    "class_name",
    "student_number",
    "student_name",
    "plant_type",
    "planting_date",
    "watered_today",
    "work_items",
    "observation_note",
    "days_grown",
    "leaf_color_mark",
    "leaf_count_mark",
    "fruit_color_mark",
    "calyx_shape_mark",
    "leaf_color_score",
    "leaf_count_score",
    "fruit_color_score",
    "calyx_shape_score",
    "harvest_progress",
    "first_fruit_date",
    "harvest_basis",
    "whole_image_path",
    "leaf_image_path",
    "fruit_image_path",
    "whole_model_label",
    "leaf_model_label",
    "fruit_model_label",
    "whole_model_score",
    "leaf_model_score",
    "fruit_model_score",
    "model_observation",
    "model_advice",
]


# =========================================================
# セッション初期化
# =========================================================
if "page" not in st.session_state:
    st.session_state.page = "home"

if "grade" not in st.session_state:
    st.session_state.grade = "3年"

if "class_name" not in st.session_state:
    st.session_state.class_name = "2組"

if "student_number" not in st.session_state:
    st.session_state.student_number = "1番"

if "student_name" not in st.session_state:
    st.session_state.student_name = ""

if "user_id" not in st.session_state:
    st.session_state.user_id = "plant_record"

if "plant_type" not in st.session_state:
    st.session_state.plant_type = "トマト"

if "planting_date" not in st.session_state:
    st.session_state.planting_date = date.today()

if "planting_date_known" not in st.session_state:
    st.session_state.planting_date_known = False

if "diagnosis_record" not in st.session_state:
    st.session_state.diagnosis_record = None


# =========================================================
# URLリンク処理
# =========================================================
try:
    guest_query = st.query_params.get("guest")
    change_query = st.query_params.get("change_student")
    back_home_query = st.query_params.get("back_home")
except Exception:
    guest_query = None
    change_query = None
    back_home_query = None

if guest_query == "1":
    st.session_state.grade = "ゲスト"
    st.session_state.class_name = ""
    st.session_state.student_number = ""
    st.session_state.student_name = "guest"
    st.session_state.user_id = "guest"
    st.session_state.force_scroll_top = True
    st.session_state.page = "diagnosis_upload"
    try:
        st.query_params.clear()
    except Exception:
        pass

if change_query == "1":
    st.session_state.force_scroll_top = True
    st.session_state.page = "diagnosis_upload"
    try:
        st.query_params.clear()
    except Exception:
        pass

if back_home_query == "1":
    st.session_state.force_scroll_top = True
    st.session_state.page = "home"
    try:
        st.query_params.clear()
    except Exception:
        pass

# Googleログイン・パスワード再設定から戻った場合は認証ページへ。
if st.query_params.get('oauth_attempt') or st.query_params.get('recovery_attempt'):
    st.session_state.page = 'account'

# =========================================================
# CSS
# =========================================================
st.markdown(
    """
    <style>
    :root {
        --green: #2f8f47;
        --green-dark: #15342f;
        --muted: #767b83;
        --line: #58b969;
        --card-border: #d8dedb;
        --white: #ffffff;
    }

    #MainMenu, footer, header {
        visibility: hidden;
    }

    html, body, [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 20% 30%, rgba(47,143,71,0.055), transparent 28%),
            radial-gradient(circle at 78% 55%, rgba(47,143,71,0.055), transparent 32%),
            linear-gradient(180deg, #ffffff 0%, #f5fbf7 58%, #fffaf2 100%);
        color: var(--green-dark);
    }

    .main .block-container {
        max-width: 820px;
        padding-top: 0 !important;
        padding-left: 0.75rem;
        padding-right: 0.75rem;
        padding-bottom: 1rem;
    }

    .lab-header {
        width: 100vw;
        margin-left: calc(50% - 50vw);
        margin-bottom: 16px !important;
        padding: 12px 0 12px 0;
        text-align: center;
        border-bottom: 2px solid var(--green);
        background: rgba(255,255,255,.58);
    }

    .lab-title {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 14px;
        font-size: 34px;
        font-weight: 950;
        letter-spacing: .08em;
        color: #163732;
        line-height: 1.1;
    }

    .lab-title .leaf {
        color: var(--green);
        font-size: 26px;
    }

    .lab-subtitle {
        margin-top: 8px;
        font-size: 16px;
        font-weight: 650;
        letter-spacing: .12em;
        color: #717983;
    }

    .select-page-wrap {
        max-width: 760px;
        margin: 4px auto 0 auto;
        text-align: center;
    }

    .select-page-wrap [data-testid="stVerticalBlockBorderWrapper"] {
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        padding: 0 !important;
        box-shadow: none !important;
    }

    .select-card,
    .select-icon {
        display: none;
    }

    .select-title {
        font-size: 30px;
        line-height: 1.12;
        font-weight: 950;
        letter-spacing: .06em;
        color: #143630;
        text-shadow: 0 3px 4px rgba(20,54,48,.15);
        padding-bottom: 8px;
        border-bottom: 2px dotted var(--line);
        margin-bottom: 8px;
        text-align: center;
    }

    .select-help {
        color: #727983;
        font-size: 14px;
        font-weight: 650;
        letter-spacing: .08em;
        margin-bottom: 14px;
    }

    .select-page-wrap [data-testid="stHorizontalBlock"] {
        gap: 1rem;
    }

    [data-testid="stSelectbox"] label,
    [data-testid="stDateInput"] label {
        font-size: 15px !important;
        font-weight: 850 !important;
        color: #303943 !important;
        min-height: 26px;
    }

    .select-page-wrap [data-testid="stSelectbox"] label {
        padding-left: 42px;
    }

    [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        min-height: 44px;
        border-radius: 14px;
        border: 2px solid #d2d9dd;
        background: #ffffff;
        box-shadow: 0 6px 12px rgba(45,63,70,.04);
        font-size: 16px;
        font-weight: 900;
        color: #1f2b34;
        padding-left: 18px;
    }

    [data-testid="stDateInput"] input {
        min-height: 54px;
        border-radius: 14px;
        border: 2px solid #d2d9dd;
        background: #ffffff;
        font-size: 18px;
        font-weight: 800;
        padding-left: 14px;
    }

    .confirm-line {
        border-top: 2px dotted rgba(47,143,71,.45);
        margin-top: 6px;
        padding-top: 6px;
        color: #173830;
        font-size: 18px;
        font-weight: 950;
        letter-spacing: .08em;
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 18px;
    }

    .confirm-line::before,
    .confirm-line::after {
        content: "⌁";
        color: #24994b;
        font-size: 34px;
        font-weight: 500;
    }

    div[data-testid="stButton"] button {
        background: linear-gradient(180deg, #36a555 0%, #238d42 100%);
        color: #ffffff;
        border: none;
        border-radius: 999px;
        min-height: 48px;
        font-size: 18px;
        font-weight: 950;
        letter-spacing: .06em;
        box-shadow: 0 10px 18px rgba(34,148,71,.22);
    }

    div[data-testid="stButton"] button:hover {
        background: linear-gradient(180deg, #2f9c4f, #1f7f3a);
        color: #ffffff;
        border: none;
    }

    .guest-login-link-wrap,
    .student-change-link-wrap {
        width: 100%;
        text-align: center;
        margin: 14px auto 8px auto;
    }

    .guest-login-link,
    .guest-login-link:visited,
    .student-change-link,
    .student-change-link:visited {
        display: inline-block;
        color: #9ca3af !important;
        font-size: 14px;
        font-weight: 500;
        text-decoration: none !important;
        letter-spacing: .03em;
        cursor: pointer;
    }

    .guest-login-link:hover,
    .student-change-link:hover {
        color: #6b7280 !important;
        text-decoration: underline !important;
    }

    .top-bar {
        display: none;
    }

    .home-card {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        margin-top: 0 !important;
    }

    .home-card-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        margin-top: 0 !important;
        margin-bottom: 22px;
    }

    .home-main-title {
        font-size: 36px;
        font-weight: 950;
        color: #163732;
        line-height: 1.1;
        margin-bottom: 6px;
    }

    .home-sub {
        font-size: 14px;
        color: var(--muted);
        margin-top: 4px;
    }

    .last-pill {
        color: var(--muted);
        border: 1px solid #e2e8e4;
        border-radius: 999px;
        padding: 8px 12px;
        font-size: 16px;
        font-weight: 700;
        background: rgba(255,255,255,.35);
    }

    .photo-card {
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        padding: 0 !important;
        margin-bottom: 20px;
    }

    .section-title {
    font-size: 22px;
    font-weight: 900;
    color: #163732;
    margin: 12px 0 10px;
}

.photo-title {
    font-size: 17px;
    font-weight: 800;
    color: #163732;
    margin-bottom: 4px;
}

.photo-help {
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 8px;
}

.days-label {
    font-size: 14px;
    font-weight: 700;
    color: var(--muted);
}

.days-number {
    font-size: 26px;
    font-weight: 900;
    color: #176b34;
}

.evaluation-title {
    font-size: 20px;
    font-weight: 900;
    margin-bottom: 10px;
}

.evaluation-row {
    font-size: 16px;
    margin-bottom: 8px;
    color: #163732;
}

.evaluation-mark {
    font-size: 22px;
    font-weight: 900;
    margin-left: 12px;
    color: #176b34;
}

/* 診断画面のボタンだけ少し小さく */
div[data-testid="stButton"] button {
    min-height: 52px;
    font-size: 18px;
    font-weight: 800;
}

    /* 写真アップロード欄：大きめ・日本語表示 */
    [data-testid="stFileUploader"] {
        background: transparent !important;
        margin-top: 14px !important;
    }

    [data-testid="stFileUploader"] section,
    [data-testid="stFileUploaderDropzone"] {
        position: relative !important;
        background: rgba(255,255,255,.52) !important;
        border: 2px dashed rgba(47,143,71,.42) !important;
        border-radius: 18px !important;
        box-shadow: none !important;
        min-height: 138px !important;
        padding: 26px 18px !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 10px !important;
    }

    [data-testid="stFileUploader"] * {
        box-shadow: none !important;
    }

    [data-testid="stFileUploaderDropzoneInstructions"] {
        display: none !important;
    }

    [data-testid="stFileUploaderDropzone"]::before {
        content: " 植物の写真を選んでください";
        display: block;
        text-align: center;
        color: #304039;
        font-size: 16px;
        font-weight: 800;
        margin-bottom: 2px;
    }

    [data-testid="stFileUploaderDropzone"]::after {
        content: "JPG・JPEG・PNG対応";
        display: block;
        text-align: center;
        color: #8a9390;
        font-size: 12px;
        font-weight: 600;
        margin-top: 2px;
    }

    [data-testid="stFileUploader"] small {
        display: none !important;
    }

    [data-testid="stFileUploader"] button {
        background: #ffffff !important;
        color: transparent !important;
        border: 1.5px solid rgba(47,143,71,.45) !important;
        border-radius: 999px !important;
        min-height: 42px !important;
        height: 42px !important;
        padding: 0 26px !important;
        font-size: 0 !important;
        font-weight: 800 !important;
        box-shadow: 0 6px 14px rgba(47,143,71,.12) !important;
    }

    [data-testid="stFileUploader"] button::after {
        content: "写真を選ぶ";
        color: #2f8f47 !important;
        font-size: 15px !important;
        font-weight: 800 !important;
    }

    [data-testid="stFileUploader"] button:hover {
        background: #f4fbf6 !important;
        border-color: #2f8f47 !important;
    }

    /* 灰色リンク風の戻るリンク */
    .back-link-wrap {
        width: 100%;
        text-align: center;
        margin: 18px auto 10px auto;
    }

    .back-link,
    .back-link:visited {
        display: inline-block;
        color: #9ca3af !important;
        font-size: 14px;
        font-weight: 500;
        text-decoration: none !important;
        letter-spacing: .03em;
        cursor: pointer;
    }

    .back-link:hover {
        color: #6b7280 !important;
        text-decoration: underline !important;
    }



    /* ===== 診断結果ページ：1ページ完結デザイン ===== */
    .result-page-title {
        display: flex;
        align-items: center;
        gap: 10px;
        justify-content: flex-start;
        font-size: 38px;
        font-weight: 950;
        color: #15342f;
        letter-spacing: .04em;
        margin: -8px 0 20px 0;
        line-height: 1.1;
    }

    .result-summary-card {
        min-height: 116px;
        background: rgba(255,255,255,.94);
        border: 1px solid #dfe8e2;
        border-radius: 18px;
        box-shadow: 0 10px 24px rgba(23,107,52,.06);
        padding: 18px 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 18px;
    }

    .days-card-inner {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 18px;
        width: 100%;
    }

    .days-icon {
        font-size: 46px;
        line-height: 1;
    }

    .days-small {
        font-size: 18px;
        font-weight: 800;
        color: #213933;
        margin-bottom: 4px;
    }

    .days-big {
        font-size: 44px;
        font-weight: 950;
        line-height: 1;
        color: #12813a;
    }

    .harvest-card { justify-content: flex-start; }
    .harvest-card-inner { width: 100%; }

    .harvest-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 12px;
    }

    .harvest-title {
        font-size: 20px;
        font-weight: 900;
        color: #173830;
    }

    .harvest-percent {
        font-size: 34px;
        font-weight: 950;
        color: #12813a;
        line-height: 1;
    }

    .harvest-bar {
        width: 100%;
        height: 11px;
        border-radius: 999px;
        background: #e2e4e2;
        overflow: hidden;
        margin-bottom: 10px;
    }

    .harvest-fill {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, #168a3e, #35a857);
    }

    .harvest-note {
        color: #213933;
        font-size: 16px;
        font-weight: 700;
    }

    .result-card {
        height: 360px;
        background: rgba(255,255,255,.94);
        border: 1px solid #dfe8e2;
        border-radius: 18px;
        box-shadow: 0 10px 24px rgba(23,107,52,.055);
        padding: 22px 24px;
        margin-bottom: 18px;
        overflow: hidden;
    }

    .result-card-title {
        font-size: 20px;
        font-weight: 900;
        color: #163732;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .eval-list {
        border: 1px solid #e4ebe7;
        border-radius: 16px;
        padding: 4px 16px;
        background: rgba(255,255,255,.7);
        height: 272px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }

    .eval-item {
        height: 62px;
        display: grid;
        grid-template-columns: 48px 1fr 44px;
        align-items: center;
        border-bottom: 1px dashed #d9e2dd;
        gap: 8px;
    }

    .eval-item:last-child { border-bottom: none; }
    .eval-icon { font-size: 26px; text-align: center; }
    .eval-label { font-size: 16px; font-weight: 850; color: #173830; }
    .eval-mark { font-size: 26px; font-weight: 950; color: #13813b; text-align: center; }
    .eval-mark.warn { color: #f28a00; }

    .advice-card {
        background: rgba(255,255,255,.94);
        border: 1px solid #dfe8e2;
        border-radius: 18px;
        box-shadow: 0 10px 24px rgba(23,107,52,.055);
        padding: 18px 26px;
        margin: 0 0 18px 0;
        display: grid;
        grid-template-columns: 220px 1fr;
        align-items: center;
        gap: 20px;
    }

    .advice-title {
        font-size: 20px;
        font-weight: 900;
        color: #163732;
        margin: 0;
        border-right: 1px solid #d9e2dd;
        padding-right: 18px;
    }

    .advice-line {
        font-size: 15px;
        font-weight: 750;
        color: #173830;
        line-height: 1.55;
        margin: 0;
    }

    .advice-dot { color: #13813b; font-size: 18px; margin-right: 8px; }
    .stPlotlyChart, .stPyplot { display: flex; justify-content: center; }

    /* 結果ページのボタンは低めにする */
    .result-action-row div[data-testid="stButton"] button {
        min-height: 54px !important;
        font-size: 18px !important;
        font-weight: 850 !important;
    }

    @media (max-width: 800px) {
        .lab-header {
            margin-bottom: 34px !important;
            padding: 20px 0 20px 0;
        }

        .lab-title {
            font-size: 30px;
        }

        .lab-subtitle {
            font-size: 15px;
        }

        .select-page-wrap {
            margin-top: 16px;
        }

        .select-page-wrap [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0 !important;
        }

        .select-title {
            font-size: 30px;
        }

        .select-page-wrap [data-testid="stHorizontalBlock"] {
            gap: .5rem;
        }

        .select-page-wrap [data-testid="stSelectbox"] label {
            padding-left: 8px;
            font-size: 14px !important;
        }

        [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            min-height: 64px;
            font-size: 20px;
        }

        .confirm-line {
            font-size: 22px;
        }

        div[data-testid="stButton"] button {
            min-height: 64px;
            font-size: 22px;
        }

        .home-card-head {
            display: block;
        }

        .home-main-title {
            font-size: 34px;
        }

        .last-pill {
            display: inline-block;
            margin-top: 12px;
        }

        .student-change-link,
        .guest-login-link {
            font-size: 14px !important;
        }
    }


    /* ===== 診断結果ページ：今日のようす統合デザイン ===== */
    .main .block-container {
        max-width: 1120px;
    }

    .result-page-title {
        display: flex;
        align-items: center;
        gap: 10px;
        justify-content: flex-start;
        font-size: 38px;
        font-weight: 950;
        color: #15342f;
        letter-spacing: .04em;
        margin: -8px 0 18px 0;
        line-height: 1.1;
    }

    .result-summary-card {
        min-height: 112px;
        background: rgba(255,255,255,.94);
        border: 1px solid #dfe8e2;
        border-radius: 18px;
        box-shadow: 0 10px 24px rgba(23,107,52,.06);
        padding: 16px 22px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 14px;
    }

    .days-card-inner {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 18px;
        width: 100%;
    }

    .days-icon {
        font-size: 42px;
        line-height: 1;
        background: rgba(47,143,71,.08);
        width: 74px;
        height: 74px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .days-small {
        font-size: 18px;
        font-weight: 800;
        color: #213933;
        margin-bottom: 3px;
    }

    .days-big {
        font-size: 44px;
        font-weight: 950;
        line-height: 1;
        color: #12813a;
    }

    .harvest-card { justify-content: flex-start; background: linear-gradient(180deg, rgba(246,251,255,.95), rgba(255,255,255,.94)); border-color: #cfe2f3; }
    .harvest-card-inner { width: 100%; }

    .harvest-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 8px;
    }

    .harvest-title {
        font-size: 24px;
        font-weight: 900;
        color: #173830;
    }

    .harvest-percent {
        font-size: 38px;
        font-weight: 950;
        color: #126fc7;
        line-height: 1;
    }

    .harvest-param-badge {
        display: inline-block;
        border: 1px solid #d6dbe0;
        background: rgba(255,255,255,.75);
        border-radius: 999px;
        padding: 4px 10px;
        color: #66716b;
        font-size: 12px;
        font-weight: 750;
        margin-left: 8px;
    }

    .harvest-bar {
        width: 100%;
        height: 10px;
        border-radius: 999px;
        background: #dfe4e1;
        overflow: hidden;
        margin-bottom: 8px;
    }

    .harvest-fill {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, #168a3e, #35a857);
    }

    .harvest-note {
        color: #213933;
        font-size: 16px;
        font-weight: 700;
    }

    .param-control-wrap {
        margin: -4px 0 14px 0;
        padding: 0 4px;
    }
    .param-control-wrap label {
        font-size: 16px !important;
        color: #66716b !important;
        font-weight: 750 !important;
    }

    .today-card {
        background: rgba(255,255,255,.95);
        border: 1px solid #dfe8e2;
        border-radius: 20px;
        box-shadow: 0 12px 28px rgba(23,107,52,.07);
        padding: 22px 26px 18px 26px;
        margin: 10px 0 20px 0;
        position: relative;
        overflow: hidden;
    }

    .today-card::after {
        content: "";
        position: absolute;
        right: -22px;
        top: 72px;
        width: 135px;
        height: 135px;
        background: radial-gradient(circle, rgba(47,143,71,.08), transparent 70%);
        border-radius: 50%;
    }

    .today-title {
        font-size: 34px;
        font-weight: 950;
        color: #165237;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .today-table {
        border-top: 1px dashed #d7dfda;
    }

    .today-row {
        display: grid;
        grid-template-columns: 90px 190px 210px 1fr;
        align-items: center;
        gap: 12px;
        min-height: 68px;
        border-bottom: 1px dashed #e2e8e4;
        font-size: 20px;
        color: #173830;
        position: relative;
        z-index: 1;
    }

    .today-icon {
        font-size: 36px;
        text-align: center;
    }

    .today-label {
        font-size: 24px;
        font-weight: 900;
        color: #173830;
    }

    .today-status {
        width: fit-content;
        min-width: 150px;
        text-align: center;
        border-radius: 12px;
        padding: 9px 14px;
        font-size: 19px;
        font-weight: 850;
    }

    .today-status.good {
        background: #eef7ee;
        color: #168a3e;
        border: 1px solid #d8eadc;
    }

    .today-status.warn {
        background: #fff4e8;
        color: #e67e00;
        border: 1px solid #ffdcb2;
    }

    .today-comment {
        font-size: 19px;
        font-weight: 720;
        color: #223a34;
        line-height: 1.45;
    }

    .today-advice {
        margin-top: 14px;
        border: 1px solid #dde6df;
        border-radius: 14px;
        background: rgba(255,255,255,.76);
        display: grid;
        grid-template-columns: 210px 1fr;
        align-items: center;
        gap: 18px;
        padding: 12px 18px;
        position: relative;
        z-index: 1;
    }

    .today-advice-title {
        color: #165237;
        font-size: 24px;
        font-weight: 900;
        border-right: 1px solid #d9e2dd;
        padding-right: 16px;
    }

    .today-advice-text {
        color: #173830;
        font-size: 20px;
        font-weight: 750;
        line-height: 1.5;
    }

    .result-action-row div[data-testid="stButton"] button {
        min-height: 64px !important;
        font-size: 24px !important;
        font-weight: 900 !important;
    }

    @media (max-width: 800px) {
        .today-row { grid-template-columns: 56px 1fr; gap: 10px; padding: 12px 0; }
        .today-status, .today-comment { grid-column: 2; }
        .today-advice { grid-template-columns: 1fr; gap: 8px; }
        .today-advice-title { border-right: none; padding-right: 0; }
    }



    /* ===== 今日の観察入力ページ：画像寄せ ===== */
    .observe-head {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 18px;
        margin: -4px 0 18px 0;
    }

    .observe-title-main {
        font-size: 38px;
        font-weight: 950;
        color: #15342f;
        letter-spacing: .02em;
        line-height: 1.2;
        margin-bottom: 8px;
    }

    .observe-lead {
        font-size: 14px;
        font-weight: 650;
        color: #2f3b38;
    }

    .observe-meta {
        min-width: 260px;
        background: rgba(255,255,255,.72);
        border: 1px solid #dfe8e2;
        border-radius: 16px;
        box-shadow: 0 8px 22px rgba(23,107,52,.05);
        padding: 14px 18px;
        color: #173830;
        font-size: 15px;
        font-weight: 800;
        line-height: 1.8;
        text-align: left;
    }

    .observe-card {
        background: rgba(255,255,255,.94);
        border: 1px solid #dfe8e2;
        border-radius: 18px;
        box-shadow: 0 10px 24px rgba(23,107,52,.055);
        padding: 18px 22px;
        margin: 12px 0 16px 0;
    }

    .observe-row {
        display: grid;
        grid-template-columns: 280px 1fr;
        gap: 22px;
        align-items: start;
    }

    .observe-left {
        display: flex;
        gap: 14px;
        align-items: flex-start;
    }

    .observe-step {
        width: 36px;
        height: 36px;
        min-width: 36px;
        border-radius: 999px;
        background: linear-gradient(180deg, #36a555, #238d42);
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
        font-weight: 950;
        box-shadow: 0 7px 16px rgba(34,148,71,.16);
    }

    .observe-label-main {
        font-size: 20px;
        font-weight: 950;
        color: #173830;
        margin-top: 2px;
    }

    .observe-help-small {
        font-size: 13px;
        line-height: 1.7;
        color: #66716b;
        margin-top: 8px;
        font-weight: 650;
    }

    .observe-card div[data-testid="stRadio"] label {
        font-size: 15px !important;
        font-weight: 800 !important;
        color: #173830 !important;
    }

    .observe-card div[data-testid="stCheckbox"] label {
        background: rgba(255,255,255,.92);
        border: 1px solid #d9e2dd;
        border-radius: 12px;
        min-height: 46px;
        padding: 10px 14px !important;
        display: flex !important;
        align-items: center !important;
        font-size: 15px !important;
        font-weight: 800 !important;
        color: #173830 !important;
        box-shadow: 0 4px 10px rgba(23,107,52,.035);
    }

    .observe-card div[data-testid="stCheckbox"] label:hover {
        border-color: rgba(47,143,71,.45);
        background: rgba(245,251,247,.95);
    }

    .observe-card textarea {
        min-height: 96px !important;
        border-radius: 14px !important;
        font-size: 15px !important;
        background: rgba(248,250,252,.85) !important;
    }

    .other-work-box {
        margin-top: 12px;
        padding: 10px 12px 12px 12px;
        border: 1px dashed #c9dfcf;
        border-radius: 14px;
        background: rgba(247,252,248,.72);
    }

    .photo-section-title {
        font-size: 22px;
        font-weight: 950;
        color: #163732;
        margin: 18px 0 10px 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    @media (max-width: 800px) {
        .observe-head { display: block; }
        .observe-meta { margin-top: 14px; min-width: 0; }
        .observe-row { grid-template-columns: 1fr; gap: 12px; }
        .observe-title-main { font-size: 26px; }
    }



    /* ===== 今日の観察入力ページ：白い空枠を出さないシンプル版 ===== */
    .observe-card,
    .observe-row {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        margin: 0 !important;
    }

    .observe-divider {
        height: 1px;
        background: rgba(47,143,71,.16);
        margin: 22px 0;
        width: 100%;
    }

    .observe-section-title {
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 22px;
        font-weight: 950;
        color: #173830;
        margin: 0 0 10px 0;
    }

    .observe-step-inline {
        width: 34px;
        height: 34px;
        min-width: 34px;
        border-radius: 999px;
        background: linear-gradient(180deg, #36a555, #238d42);
        color: #ffffff;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 17px;
        font-weight: 950;
        box-shadow: 0 7px 16px rgba(34,148,71,.14);
    }

    .observe-help-line {
        color: #66716b;
        font-size: 13px;
        font-weight: 650;
        margin: 0 0 12px 46px;
    }

    div[data-testid="stCheckbox"] label {
        min-height: 34px !important;
        font-size: 15px !important;
        font-weight: 750 !important;
        color: #173830 !important;
    }

    div[data-testid="stRadio"] label {
        font-size: 15px !important;
        font-weight: 750 !important;
        color: #173830 !important;
    }

    .observation-record-box {
        margin-top: 10px;
    }

    

    html, body, [data-testid="stAppViewContainer"], section.main {
        scroll-behavior: auto !important;
    }

    .result-action-row div[data-testid="stButton"] button,
    .history-action-row div[data-testid="stButton"] button,
    .growth-card div[data-testid="stButton"] button {
        white-space: nowrap !important;
        line-height: 1.2 !important;
    }



    /* ===== 記録詳細：診断結果を主役にしたコンパクト版 ===== */
    .history-detail-head { display:flex; align-items:baseline; flex-wrap:wrap; gap:8px 24px; margin:0 0 22px; }
    .history-detail-head h2 { margin:0 !important; font-size:26px !important; font-weight:850 !important; color:#173e30 !important; }
    .history-detail-head span { font-size:13px; color:#738079; }
    .history-detail-section { font-size:18px; font-weight:800; color:#174733; margin:0 0 12px; }
    .history-detail-result-list { background:#fff; border:1px solid #dfe9e1; border-radius:13px; overflow:hidden; }
    .history-detail-result-row { display:grid; grid-template-columns:100px 135px minmax(0,1fr); gap:12px; align-items:center; padding:15px 17px; }
    .history-detail-result-row + .history-detail-result-row { border-top:1px solid #edf0ed; }
    .history-detail-result-name { font-size:15px; color:#243a30; font-weight:750; }
    .history-detail-result-value { font-size:15px; color:#17673e; font-weight:850; }
    .history-detail-result-comment { font-size:14px; color:#45564d; line-height:1.55; overflow-wrap:anywhere; }
    .history-detail-advice { margin-top:24px; background:#f1f8f2; border:1px solid #d7e9da; border-radius:13px; padding:17px 20px; }
    .history-detail-note { margin-top:16px; background:#fff; border:1px solid #e0e8e1; border-radius:13px; padding:17px 20px; }
    .history-detail-advice p, .history-detail-note p { font-size:15px; color:#284036; line-height:1.7; margin:0; white-space:pre-wrap; }
    div[data-testid="stVerticalBlock"]:has(> div .history-detail-nav-anchor) div[data-testid="stButton"] button { min-height:38px !important; font-size:13px !important; background:transparent !important; border:1px solid #d7e3da !important; color:#65736b !important; box-shadow:none !important; }
    @media (max-width:720px) {
       .history-detail-result-row { grid-template-columns:78px minmax(0,1fr); gap:4px 12px; }
       .history-detail-result-comment { grid-column:2; }
       .history-detail-head h2 { font-size:22px !important; }
    }

    /* ===== 成長のきろく詳細：写真を小さめにして文字崩れを防ぐ ===== */
    .detail-title { font-size: 28px !important; font-weight: 950 !important; color: #163732 !important; margin: -6px 0 18px 0 !important; letter-spacing: .04em !important; }
    .detail-panel { background: rgba(255,255,255,.95) !important; border: 1px solid #dfe8e2 !important; border-radius: 18px !important; box-shadow: 0 12px 28px rgba(23,107,52,.07) !important; padding: 18px !important; margin-bottom: 16px !important; overflow: hidden !important; }
    .detail-photo-title { font-size: 20px; font-weight: 900; color: #173830; margin: 0 0 12px 0; }
    .detail-photo-note { color: #7a837e; font-size: 12px; font-weight: 650; text-align: center; margin-top: 8px; }
    .detail-summary { display: grid !important; grid-template-columns: 1fr 1fr !important; gap: 12px !important; margin-bottom: 14px !important; }
    .detail-mini-card { background: #f7fbf8 !important; border: 1px solid #e0e9e3 !important; border-radius: 14px !important; padding: 12px 16px !important; }
    .detail-mini-label { color: #6f7772 !important; font-size: 13px !important; font-weight: 800 !important; margin-bottom: 4px !important; }
    .detail-mini-value { color: #12813a !important; font-size: 26px !important; font-weight: 950 !important; line-height: 1.1 !important; }
    .detail-progress-card { background: linear-gradient(180deg, rgba(247,252,248,.95), rgba(255,255,255,.95)); border: 1px solid #cfe6d5; border-radius: 16px; padding: 16px 18px; margin: 12px 0 18px 0; }
    .detail-progress-title { font-size: 17px; font-weight: 900; color: #165237; margin-bottom: 10px; }
    .detail-progress-main { display: flex; align-items: center; gap: 16px; margin-bottom: 8px; }
    .detail-progress-percent { font-size: 34px; font-weight: 950; color: #12813a; min-width: 92px; }
    .detail-progress-comment { font-size: 14px; font-weight: 750; color: #213933; }
    .detail-status-title { font-size: 22px; font-weight: 950; color: #165237; margin: 16px 0 12px 0; }
    .detail-status-list { display: grid; grid-template-columns: 1fr; gap: 10px; }
    .detail-status-item { display: grid; grid-template-columns: 44px 100px 130px minmax(220px, 1fr); align-items: center; gap: 12px; background: rgba(255,255,255,.9); border: 1px solid #e1e9e4; border-radius: 14px; padding: 12px 14px; }
    .detail-status-icon { font-size: 25px; text-align: center; }
    .detail-status-label { font-size: 16px; font-weight: 900; color: #173830; white-space: nowrap; }
    .detail-status-pill { border-radius: 999px; padding: 7px 11px; font-size: 14px; font-weight: 850; text-align: center; white-space: nowrap; }
    .detail-status-pill.good { background: #eef7ee; color: #168a3e; border: 1px solid #d8eadc; }
    .detail-status-pill.warn { background: #fff4e8; color: #e67e00; border: 1px solid #ffdcb2; }
    .detail-status-comment { font-size: 14px; font-weight: 720; color: #223a34; line-height: 1.55; white-space: normal; word-break: keep-all; overflow-wrap: break-word; writing-mode: horizontal-tb !important; }
    .detail-advice-box { margin-top: 14px; background: #f8fcf8; border: 1px solid #dce9df; border-radius: 15px; padding: 14px 16px; }
    .detail-advice-title { font-size: 18px; font-weight: 900; color: #165237; margin-bottom: 6px; }
    .detail-advice-text { font-size: 14px; font-weight: 700; color: #243a34; line-height: 1.65; word-break: keep-all; }
    .detail-record-box { margin-top: 10px; background: rgba(255,255,255,.82); border: 1px dashed #d2e4d6; border-radius: 14px; padding: 12px 14px; font-size: 13px; line-height: 1.7; color: #33433f; font-weight: 650; }
    @media (max-width: 900px) {
        .detail-status-item { grid-template-columns: 38px 1fr; grid-template-areas: "icon label" "icon pill" "icon comment"; gap: 5px 10px; }
        .detail-status-icon { grid-area: icon; }
        .detail-status-label { grid-area: label; }
        .detail-status-pill { grid-area: pill; width: fit-content; }
        .detail-status-comment { grid-area: comment; }
    }


    /* ===== 初回設定画面：1画面に収めるコンパクト版 ===== */
    .select-page-wrap {
        max-width: 900px !important;
        margin-top: 0 !important;
    }

    .select-title {
        font-size: 24px !important;
        padding-bottom: 6px !important;
        margin-bottom: 6px !important;
    }

    .select-help {
        font-size: 14px !important;
        margin-bottom: 8px !important;
    }

    .select-page-wrap [data-testid="stHorizontalBlock"] {
        gap: 0.75rem !important;
    }

    .select-page-wrap [data-testid="stSelectbox"] label,
    .select-page-wrap [data-testid="stDateInput"] label {
        min-height: 18px !important;
        font-size: 13px !important;
        margin-bottom: 2px !important;
    }

    .select-page-wrap [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    .select-page-wrap [data-testid="stDateInput"] input {
        min-height: 42px !important;
        height: 42px !important;
        font-size: 16px !important;
        border-radius: 11px !important;
    }

    .select-page-wrap [data-testid="stSelectbox"],
    .select-page-wrap [data-testid="stDateInput"] {
        margin-bottom: 4px !important;
    }

    .confirm-line {
        margin-top: 4px !important;
        padding-top: 5px !important;
        font-size: 17px !important;
    }

    .confirm-line::before,
    .confirm-line::after {
        font-size: 24px !important;
    }

    .select-page-wrap div[data-testid="stButton"] button {
        min-height: 46px !important;
        font-size: 17px !important;
        margin-top: 0 !important;
    }

    .guest-login-link-wrap {
        margin: 6px auto 2px auto !important;
    }

    .lab-header {
        margin-bottom: 14px !important;
        padding: 10px 0 10px 0 !important;
    }

    .lab-title {
        font-size: 27px !important;
    }

    .lab-title .leaf {
        font-size: 24px !important;
    }

    @media (max-width: 800px) {
        .lab-header {
            margin-bottom: 10px !important;
            padding: 8px 0 !important;
        }

        .select-title {
            font-size: 22px !important;
        }

        .select-page-wrap [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        .select-page-wrap [data-testid="stDateInput"] input {
            min-height: 40px !important;
            height: 40px !important;
        }
    }


    /* ===== 全体写真：お手本とアップロード欄を横並び ===== */
    [data-testid="stFileUploader"] {
        margin-top: 0 !important;
    }

    [data-testid="stFileUploader"] section,
    [data-testid="stFileUploaderDropzone"] {
        min-height: 300px !important;
    }


    /* ===== 写真アップロード部分：余白と横並び調整 ===== */
    .observe-divider {
        margin: 12px 0 !important;
    }

    .observe-section-title {
        margin-bottom: 4px !important;
    }

    .observe-help-line {
        margin-bottom: 8px !important;
    }

    [data-testid="stFileUploader"] {
        margin-top: 0 !important;
    }

    /* 左右の列の中身を上揃え */
    [data-testid="stHorizontalBlock"] {
        align-items: flex-start !important;
    }


    /* ===== お手本写真とアップロード枠を1:1で揃える ===== */
    [data-testid="stHorizontalBlock"] {
        align-items: flex-start !important;
    }

    [data-testid="stFileUploader"] section,
    [data-testid="stFileUploaderDropzone"] {
        width: 100% !important;
        min-height: 300px !important;
    }


    /* ===== 診断入力画面：文字を見やすく、全体をコンパクトに ===== */

    /* 上部 */
    .observe-head {
        margin: -4px 0 8px 0 !important;
    }

    .observe-title-main {
        font-size: 27px !important;
        margin-bottom: 3px !important;
    }

    .observe-meta {
        padding: 9px 14px !important;
        font-size: 13px !important;
        line-height: 1.45 !important;
    }

    /* セクション間の余白 */
    .observe-divider {
        margin: 10px 0 !important;
    }

    .observe-section-title {
        margin: 0 0 5px 0 !important;
        font-size: 20px !important;
        gap: 9px !important;
    }

    .observe-step-inline {
        width: 30px !important;
        height: 30px !important;
        min-width: 30px !important;
        font-size: 15px !important;
    }

    /* 灰色の補足文字を少し大きく・濃く */
    .observe-help-line,
    .photo-help,
    .detail-photo-note,
    .home-sub {
        color: #59635f !important;
        font-size: 14px !important;
        font-weight: 700 !important;
    }

    .observe-help-line {
        margin: 0 0 7px 39px !important;
    }

    /* ラジオ・チェックを少し詰める */
    div[data-testid="stRadio"] {
        margin-bottom: 0 !important;
    }

    div[data-testid="stCheckbox"] {
        margin-bottom: -2px !important;
    }

    div[data-testid="stCheckbox"] label,
    div[data-testid="stRadio"] label {
        min-height: 30px !important;
        font-size: 14px !important;
    }

    /* 写真エリア */
    [data-testid="stFileUploader"] {
        margin-top: 0 !important;
    }

    [data-testid="stFileUploader"] section,
    [data-testid="stFileUploaderDropzone"] {
        min-height: 235px !important;
        padding: 16px 14px !important;
    }

    /* 診断ボタン周辺 */
    .stButton {
        margin-top: 2px !important;
    }

    /* ===== 診断結果画面も少しだけ詰める ===== */
    .result-page-title {
        margin: -8px 0 10px 0 !important;
        font-size: 27px !important;
    }

    .result-summary-card {
        min-height: 92px !important;
        padding: 12px 18px !important;
        margin-bottom: 10px !important;
    }

    .today-card {
        padding: 16px 20px 14px 20px !important;
        margin: 6px 0 12px 0 !important;
    }

    .today-title {
        font-size: 24px !important;
        margin-bottom: 7px !important;
    }

    .today-row {
        min-height: 48px !important;
    }

    .today-advice {
        margin-top: 9px !important;
        padding: 9px 14px !important;
    }

    .today-advice-title {
        font-size: 18px !important;
    }

    .today-advice-text {
        font-size: 14px !important;
        line-height: 1.45 !important;
    }

    .result-action-row div[data-testid="stButton"] button {
        min-height: 48px !important;
        font-size: 17px !important;
    }


    /* ===== 植物からのサイン：1行表示 ===== */
    .today-advice {
        grid-template-columns: 210px 1fr !important;
    }

    .today-advice-title {
        white-space: nowrap !important;
        word-break: keep-all !important;
        font-size: 18px !important;
    }

</style>
    """,
    unsafe_allow_html=True,
)

# 記録一覧：写真がないデータも見やすいカードに整える
if st.session_state.page == "history_calendar":
    st.markdown("""
    <style>
    .history-v3-title {font-size:29px;font-weight:850;color:#173e2c;margin:4px 0 7px;}
    .history-v3-lead {color:#697a70;font-size:14px;margin:0 0 24px;line-height:1.65;}
    .history-v3-date {font-size:18px;font-weight:800;color:#174c32;margin:7px 0 9px;}
    /* 記録一覧の写真だけ、縦長写真もコンパクトに表示 */
    div[data-testid="stMainBlockContainer"]:has(.history-v3-title) [data-testid="stImage"] img {
      max-height:190px !important;
      max-width:170px !important;
      width:auto !important;
      object-fit:contain !important;
      object-position:left center !important;
      border-radius:9px;
    }
    /* 記録一覧の写真：縦横の向きにかかわらず同じ正方形の枠で表示 */
    div[data-testid="stMainBlockContainer"]:has(.history-v3-title) [data-testid="stImage"] {
      width:220px !important; max-width:100% !important;
    }
    div[data-testid="stMainBlockContainer"]:has(.history-v3-title) [data-testid="stImage"] img {
      width:220px !important; height:220px !important; max-width:100% !important;
      object-fit:contain !important; object-position:center !important;
      background:#f4f8f5 !important; border-radius:10px !important;
    }
    .history-v3-no-photo {height:220px;width:220px;max-width:100%;border-radius:10px;background:#f2f6f3;
      display:flex;align-items:center;justify-content:center;color:#88948c;font-size:13px;}
    .history-v3-diagnosis {font-size:13px;line-height:1.75;color:#30483b;min-height:56px;}
    .history-v3-muted {font-size:13px;color:#86918a;min-height:56px;}
    .history-v3-note {font-size:12px;color:#697a70;margin-top:8px;line-height:1.55;}
    /* 記録一覧：同じ行のカードを同じ高さにし、ボタンを下端に揃える */
    div[data-testid="stHorizontalBlock"]:has(.history-v3-date) {
      align-items:stretch !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.history-v3-date) > div[data-testid="stColumn"] {
      display:flex !important;
      flex-direction:column !important;
    }
    div[data-testid="stColumn"]:has(.history-v3-date)
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.history-v3-date) {
      display:flex !important;
      flex:1 1 auto !important;
      width:100% !important;
      min-height:510px !important;
    }
    div[data-testid="stColumn"]:has(.history-v3-date)
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.history-v3-date)
    > div[data-testid="stVerticalBlock"] {
      display:flex !important;
      flex-direction:column !important;
      flex:1 1 auto !important;
      width:100% !important;
    }
    div[data-testid="stColumn"]:has(.history-v3-date)
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.history-v3-date)
    [data-testid="stElementContainer"]:has([class*="st-key-detail_"]) {
      margin-top:auto !important;
    }
    @media (max-width: 640px) {
      div[data-testid="stColumn"]:has(.history-v3-date)
      div[data-testid="stVerticalBlockBorderWrapper"]:has(.history-v3-date) {
        min-height:0 !important;
      }
    }
    .history-v3-foot {text-align:center;color:#87938c;font-size:12px;margin:25px 0 8px;}
    .st-key-global_home_navigation button {min-height:29px !important; height:29px !important;
      padding:2px 7px !important;font-size:11px !important;font-weight:600 !important;
      background:transparent !important;color:#52645a !important;
      border:1px solid #d7e2da !important;border-radius:8px !important;box-shadow:none !important;}
    [class*="st-key-detail_"] button {min-height:37px !important;height:37px !important;
      background:#fff !important;background-image:none !important;color:#248348 !important;
      border:1px solid #b9d6c2 !important;border-radius:9px !important;box-shadow:none !important;
      font-size:13px !important;font-weight:700 !important;}
    [class*="st-key-detail_"] button:hover {background:#eff8f1 !important;}
    </style>""", unsafe_allow_html=True)

# =========================================================
# 共通ナビゲーション：ロゴでホーム、最下部で1ページ前へ
# =========================================================
# ページ移動履歴はセッションごとに保持します。
# 既存の各ページによる page 変更は、次の再実行時に自動的に検知します。
if "nav_history" not in st.session_state:
    st.session_state.nav_history = []
if "nav_last_page" not in st.session_state:
    st.session_state.nav_last_page = st.session_state.page

if st.session_state.page == "select_user":
    st.session_state.page = "diagnosis_upload"

if st.session_state.page != st.session_state.nav_last_page:
    previous = st.session_state.nav_last_page
    if st.session_state.page == "home":
        st.session_state.nav_history = []
    elif previous and previous != st.session_state.page:
        st.session_state.nav_history.append(previous)
    st.session_state.nav_last_page = st.session_state.page


def go_home() -> None:
    st.session_state.nav_history = []
    st.session_state.nav_last_page = "home"
    st.session_state.page = "home"
    st.session_state.force_scroll_top = True
    st.rerun()


def go_back() -> None:
    history = st.session_state.nav_history
    previous = history.pop() if history else "home"
    # ホームや戻り操作を新しい進行履歴として記録しない。
    st.session_state.nav_last_page = previous
    st.session_state.page = previous
    st.session_state.force_scroll_top = True
    st.rerun()


def bottom_back_button() -> None:
    if st.session_state.page == "home":
        return
    st.markdown('<div class="app-bottom-nav-spacer"></div>', unsafe_allow_html=True)
    if st.button("← 1ページ前に戻る", key="shared_bottom_back", use_container_width=True):
        go_back()

st.markdown("""
<style>
.st-key-app_brand_home button {
    background:transparent !important;
    background-image:none !important;
    border:0 !important;
    box-shadow:none !important;
    color:#165237 !important;
    font-size:clamp(25px,3.2vw,38px) !important;
    font-weight:900 !important;
    letter-spacing:0 !important;
    padding:4px 1px !important;
    min-height:35px !important;
    text-align:left !important;
    justify-content:flex-start !important;
    white-space:nowrap !important;
}
/* ホームの共通ボタン指定より詳細な指定にして、全ページで文字サイズを統一 */
div[data-testid="stMainBlockContainer"] .st-key-app_brand_home .stButton > button {
    font-size:clamp(25px,3.2vw,38px) !important;
    font-weight:900 !important;
    min-height:48px !important;
    line-height:1.2 !important;
    padding:4px 1px !important;
    white-space:nowrap !important;
}
/* ロゴの文字そのものにも指定する。Streamlit の button 内 p のサイズを上書き */
div[data-testid="stMainBlockContainer"] [class*="st-key-app_brand_home"] button,
div[data-testid="stMainBlockContainer"] [class*="st-key-app_brand_home"] button p,
div[data-testid="stMainBlockContainer"] [class*="st-key-app_brand_home"] button span {
    font-size: 40px !important;
    font-weight: 900 !important;
    line-height: 1.25 !important;
    white-space: nowrap !important;
}
@media (max-width: 640px) {
    div[data-testid="stMainBlockContainer"] [class*="st-key-app_brand_home"] button,
    div[data-testid="stMainBlockContainer"] [class*="st-key-app_brand_home"] button p,
    div[data-testid="stMainBlockContainer"] [class*="st-key-app_brand_home"] button span {
        font-size: 27px !important;
    }
}
.st-key-app_brand_home button:hover {color:#208c49 !important; background:transparent !important;}
.st-key-header_account_open button {
    min-height:34px !important;
    padding:3px 7px !important;
    font-size:11px !important;
    font-weight:650 !important;
    background:transparent !important;
    color:#52645a !important;
    border:1px solid #d7e2da !important;
    border-radius:8px !important;
    box-shadow:none !important;
    white-space:nowrap !important;
}
.app-bottom-nav-spacer {height:20px;}
.st-key-shared_bottom_back button {
    background:transparent !important;
    color:#62756a !important;
    border:1px solid #d7e2da !important;
    box-shadow:none !important;
    border-radius:9px !important;
    min-height:40px !important;
    font-size:14px !important;
    font-weight:650 !important;
}
.st-key-shared_bottom_back button:hover {
    background:#f3f8f4 !important;
    color:#247a46 !important;
}
</style>
""", unsafe_allow_html=True)

brand_col, account_col = st.columns([3, 1], gap="small", vertical_alignment="center")
with brand_col:
    if st.button("AI生育診断アプリ", key="app_brand_home"):
        go_home()
with account_col:
    if st.session_state.page != "account":
        logged_in = history_cloud.user() is not None
        if st.button("マイページ" if logged_in else "ログイン・登録",
                     key="header_account_open", use_container_width=True):
            st.session_state.page = "account"
            st.session_state.force_scroll_top = True
            st.rerun()

if st.session_state.page == "diagnosis_upload":
    st.markdown('<div class="diagnosis-header-rule"></div>', unsafe_allow_html=True)
elif st.session_state.page == "account":
    pass  # ログイン画面には上部の区切り線を表示しない
else:
    st.divider()

# =========================================================
# 関数
# =========================================================
def make_safe_name(text: str) -> str:
    bad_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', ' ']
    safe = str(text).strip()
    for ch in bad_chars:
        safe = safe.replace(ch, "_")
    return safe if safe else "no_name"


def make_user_id(grade: str, class_name: str, student_number: str, student_name: str) -> str:
    grade_num = grade.replace("年", "")
    class_num = class_name.replace("組", "")
    number_num = student_number.replace("番", "").zfill(2)
    name = make_safe_name(student_name)
    return f"{grade_num}-{class_num}-{number_num}_{name}"


def get_student_name(grade: str, class_name: str, student_number: str) -> str:
    return STUDENTS.get(grade, {}).get(class_name, {}).get(student_number, "")


def is_guest_user() -> bool:
    """Everyone is an anonymous visitor on the public edition."""
    return True


def can_save_history() -> bool:
    """Only authenticated accounts can access cloud history."""
    return history_cloud.user() is not None


def validated_upload(uploaded_file) -> Image.Image:
    """Safely decode photos even when iOS MIME/extension metadata differs."""
    if uploaded_file is None:
        raise ValueError("写真が選択されていません。")
    data = uploaded_file.getvalue()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("写真は10MB以下にしてください。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                # Safari may relabel/transcode iPhone photos on upload. The
                # extension is filtered by Streamlit; trust a successful PIL
                # raster decode rather than rejecting an unexpected format tag.
                source.load()
                return ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("写真を読み込めませんでした。別の写真を選ぶか、画像をJPEG形式で保存してお試しください。") from exc


def get_user_dir() -> Path:
    if not can_save_history():
        raise RuntimeError("この環境ではサーバーへの記録保存を無効にしています。")
    user_dir = USER_DATA_DIR / st.session_state.user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "photos").mkdir(exist_ok=True)
    return user_dir


def get_history_path() -> Path:
    return get_user_dir() / "diagnosis_history.csv"


def calculate_days_grown(planting_date: date, target_date: date) -> int:
    return max((target_date - planting_date).days + 1, 1)


def append_csv(path: Path, columns: list[str], row: dict) -> None:
    if path.exists():
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            old_columns = reader.fieldnames or []
            if old_columns != columns:
                previous = list(reader)
                with path.open("w", newline="", encoding="utf-8-sig") as out:
                    writer = csv.DictWriter(out, fieldnames=columns)
                    writer.writeheader()
                    for old in previous:
                        writer.writerow({k: old.get(k, "") for k in columns})
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def load_last_history() -> dict | None:
    rows = load_history_rows()
    return rows[-1] if rows else None


def load_history_rows() -> list[dict]:
    if not can_save_history():
        return []
    return history_cloud.list_history()


def format_history_date(created_at: str) -> str:
    try:
        dt = datetime.fromisoformat(created_at)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return created_at[:10]


def group_history_by_date(rows: list[dict]) -> dict:
    grouped = {}
    for row in rows:
        day = format_history_date(row.get("created_at", ""))
        grouped.setdefault(day, []).append(row)
    return grouped


def show_sample_image(path: str, caption: str) -> None:
    """
    お手本画像がある場合だけ表示します。
    元画像より大きく引き伸ばさず、画質が荒くならないように表示します。
    """
    try:
        image_path = APP_DIR / path
        if image_path.exists():
            image = Image.open(image_path).convert("RGB")
            display_width = min(image.width, 360)
            st.image(image, caption=caption, width=display_width)
    except Exception:
        pass


def save_diagnosis_image(uploaded_file, image_type: str) -> str:
    # ゲストの写真は端末・サーバー側に保存しない
    if uploaded_file is None or not can_save_history():
        return ""

    user_dir = get_user_dir()
    photo_dir = user_dir / "photos"
    photo_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    filename = f"{timestamp}_{image_type}.jpg"
    save_path = photo_dir / filename

    image = validated_upload(uploaded_file)
    image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
    image.save(save_path, format="JPEG", quality=85, optimize=True)
    return str(save_path)


# =========================================================
# 3つの Teachable Machine モデル
# 入力は共通の全体写真1枚。切り抜き処理は行わない。
# models/whole, models/leaf, models/fruit に各モデルを配置。
# =========================================================
MODEL_DIR = APP_DIR / "models"
MODEL_NAMES = {
    "whole": "株全体",
    "leaf": "葉",
    "fruit": "実",
}


@st.cache_resource
def load_tm_model(model_key: str, model_mtime: float):
    """モデルごとに読み込み、同じモデルの再読み込みを避ける。"""
    from tensorflow.keras.models import load_model
    path = MODEL_DIR / model_key / "keras_model.h5"
    return load_model(str(path), compile=False)


@st.cache_data
def load_tm_labels(model_key: str, labels_mtime: float):
    path = MODEL_DIR / model_key / "labels.txt"
    labels = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        labels.append(parts[1] if len(parts) == 2 and parts[0].isdigit() else line)
    return labels


def predict_three_models(uploaded_file, include_fruit: bool = True) -> dict:
    """写真を共通前処理し、写真に実がある場合だけ実モデルも使う。"""
    source = validated_upload(uploaded_file)
    image = ImageOps.fit(source, (224, 224), method=Image.Resampling.LANCZOS)
    normalized = np.asarray(image, dtype=np.float32) / 127.5 - 1.0
    tensor = np.expand_dims(normalized, axis=0)

    results = {}
    for key, title in MODEL_NAMES.items():
        if key == "fruit" and not include_fruit:
            continue
        folder = MODEL_DIR / key
        model_path = folder / "keras_model.h5"
        labels_path = folder / "labels.txt"
        if not model_path.is_file() or not labels_path.is_file():
            missing = [str(x.relative_to(APP_DIR)) for x in (model_path, labels_path) if not x.is_file()]
            raise FileNotFoundError("モデルファイルがありません: " + "、".join(missing))
        model = load_tm_model(key, model_path.stat().st_mtime)
        labels = load_tm_labels(key, labels_path.stat().st_mtime)
        prediction = np.asarray(model.predict(tensor, verbose=0)[0], dtype=float)
        if len(prediction) != len(labels) or not np.isfinite(prediction).all():
            raise ValueError(f"{title}モデルの出力と labels.txt が一致しないか、無効な値です。")
        best = int(np.argmax(prediction))
        results[key] = {
            "label": labels[best],
            "score": float(prediction[best]),
        }
    return results


# 学習時に登録した分類名と、診断画面右側に出す説明文の対応表。
# サンプル数は学習に使った画像の数であり、正解率・確信度ではありません。
MODEL_COMMENTS = {
    "whole": {
        "良好": "順調に育っています",
        "葉が重なっている": "葉に日光が当たるようにしましょう",
        "誘引必要": "株が倒れ気味なため、誘引をしましょう",
    },
    "leaf": {
        "良好": "順調に大きくなっています",
        "白い斑点が見られる": "葉に白い斑点が見られます",
        "葉が黄色い": "窒素不足・水分不足の可能性があります",
        "葉が淡い黄緑色": "水分過多の可能性があります",
        "しおれている": "水分不足の可能性があります",
        "葉が濃い緑色": "窒素過多の可能性があります",
        "虫食い": "虫がいる可能性があります",
        "順調": "順調に育っています",
        "正常": "順調に育っています",
        "好調": "順調に育っています",
        "要注意": "環境を見直してみましょう",
    },
    "fruit": {
        "成長途中": "順調に育っています",
        "成長中": "この調子で育てていきましょう",
        "成熟中": "色づき始めました",
        "収穫間近": "収穫まであと少しです",
        "成長段階": "成長段階です",
    },
}


def model_comment(key: str, label: str) -> str:
    """3モデルの分類名に対応する説明文を返す。未登録の名称は捏造しない。"""
    normalized = str(label or "").strip().replace("　", " ")
    if not normalized:
        return "判定できませんでした。"
    if key == "fruit" and normalized == "実なし（未診断）":
        return "写真に実が写っていないため、実の成熟度は診断していません。"
    # 以前の葉モデルにあった良好①～④を、表示上だけ良好へまとめる。
    if key == "leaf" and normalized in ("良好①", "良好②", "良好③", "良好④"):
        normalized = "良好"
    return MODEL_COMMENTS.get(key, {}).get(
        normalized,
        "この分類に対応する説明文は未設定です。",
    )


def model_signs(predictions: dict) -> str:
    return " / ".join(
        f"{MODEL_NAMES[key]}：{predictions[key]['label']}" for key in MODEL_NAMES if key in predictions
    )


# アドバイスの定型文とユーザー指定の優先度。
# 数字が大きいほど優先（10が最高、1が最低）。同点は全体→葉→実の順。
# 最大2文表示。分類名は各モデルの labels.txt と照合する。
ADVICE_RULES = {
    "whole": {
        "良好": ("今の育て方を続けながら、株の成長を観察しましょう。", 2),
        "葉が重なっている": ("葉全体に日光が当たるように、茎の位置や葉の重なりを確認しましょう。", 8),
        "誘引必要": ("株を安定させるために、茎を強く締め付けないように注意しながら、支柱に固定しましょう。", 9),
    },
    "leaf": {
        "良好": ("葉の色や数の変化を観察しながら、今の育て方を続けましょう。", 1),
        "白い斑点が見られる": ("葉の表と裏を確認し、白い斑点が広がっていないか観察しましょう。", 3),
        "葉が黄色い": ("土の湿り具合や肥料の記録を確認し、葉が黄色くなった原因を考えましょう。", 7),
        "葉が淡い黄緑色": ("土が湿りすぎていないか確認し、水やりの回数を見直しましょう。", 7),
        "しおれている": ("土の乾き具合を確認し、乾燥していたら水をあげましょう。", 9),
        "葉が濃い緑色": ("肥料を与えすぎていないか、これまでの記録を確認しましょう。", 5),
        "虫食い": ("葉の裏や茎を観察し、虫がいないか確認しましょう。", 9),
        "順調": ("この調子で育てながら、葉の成長を観察しましょう。", 2),
        "正常": ("この調子で育てながら、葉の成長を観察しましょう。", 2),
        "好調": ("この調子で育てながら、葉の成長を観察しましょう。", 2),
        "要注意": ("葉の色や形、土の状態を確認し、気になる変化を探しましょう。", 9),
    },
    "fruit": {
        "成長途中": ("実の大きさや色の変化を観察しましょう。", 1),
        "成長中": ("実が少しずつ大きくなっているか、前回の写真と比べましょう。", 2),
        "成熟中": ("実の色づき具合を確認し、変化を記録しましょう。", 2),
        "収穫間近": ("実の色や傷の有無を確認し、収穫のタイミングを考えましょう。", 7),
        "成長段階": ("この調子で育てながら、成長を観察しましょう。", 1),
    },
}


def _normalize_advice_label(model_key: str, label: str) -> str:
    normalized = str(label or "").strip().replace("　", " ")
    if model_key == "leaf" and normalized in ("良好①", "良好②", "良好③", "良好④"):
        return "良好"
    return normalized


def model_advice(predictions: dict) -> str:
    """優先度の高い定型文を最大2つ表示する。同点は全体→葉→実。"""
    candidates = []
    for order, key in enumerate(("whole", "leaf", "fruit")):
        label = _normalize_advice_label(key, predictions.get(key, {}).get("label", ""))
        item = ADVICE_RULES[key].get(label)
        if item is not None:
            sentence, priority = item
            candidates.append((priority, order, sentence))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    selected = []
    for _, _, sentence in candidates:
        if sentence not in selected:
            selected.append(sentence)
        if len(selected) == 2:
            break
    return " ".join(selected) if selected else "診断結果に対応するアドバイスが未設定です。モデルの分類名を確認してください。"


# 実モデルの分類結果を収穫の目安として表示。日数や確率は推測しない。
# 1枚の全体写真では複数の実の成熟段階が異なる場合がある。
HARVEST_GUIDANCE = {
    "成長途中": ("成長途中", "実の成長を見守る段階です。"),
    "成長段階": ("成長段階", "実の大きさや色を引き続き観察しましょう。"),
    "成長中": ("成長中", "まだ成長中です。色の変化も確認しましょう。"),
    "成熟中": ("色づき中", "色づきが進んでいるか確認しましょう。"),
    "収穫間近": ("収穫が近い可能性", "実の色や傷を確認し、収穫できるか確かめましょう。"),
    "実なし（未診断）": ("実の診断なし", "写真に実が写るようになったら成熟度を確認できます。"),
}


# 表示用の独自進捗指標。収穫確率・日数・実測された成熟率ではありません。
HARVEST_PERCENT = {
    "成長途中": 20,
    "成長段階": 30,
    "成長中": 50,
    "成熟中": 75,
    "収穫間近": 90,
}


def harvest_percent(fruit_label: str) -> int | None:
    return HARVEST_PERCENT.get(str(fruit_label or "").strip())


def harvest_percent_text(fruit_label: str) -> str:
    value = harvest_percent(fruit_label)
    return f"{value}%" if value is not None else "判定なし"


# 過去の観察例：6月17日ごろ実を確認 → 7月30日ごろ収穫（約43日）。
# 1株・1期間の参考値であり、品種・気温・実ごとの差を表すものではない。
REFERENCE_FRUIT_TO_HARVEST_DAYS = 43
VISUAL_STAGE_WEIGHT = 0.70
ELAPSED_DAYS_WEIGHT = 0.30


def estimate_harvest_progress(fruit_label: str, first_fruit_date: date | None,
                              observation_date: date) -> tuple[int | None, str]:
    """実の分類と経過日数から独自の進行度を算出する（確率ではない）。"""
    stage_pct = harvest_percent(fruit_label)
    if stage_pct is None:
        return None, "実モデルの分類が未対応です。"
    if first_fruit_date is None:
        return stage_pct, "実モデルの成熟段階のみから算出（実の確認日が未入力）。"
    if first_fruit_date > observation_date:
        return stage_pct, "実の確認日が未来のため、成熟段階のみから算出。"

    elapsed = (observation_date - first_fruit_date).days
    day_pct = min(100.0, elapsed * 100.0 / REFERENCE_FRUIT_TO_HARVEST_DAYS)
    combined = round(stage_pct * VISUAL_STAGE_WEIGHT + day_pct * ELAPSED_DAYS_WEIGHT)
    # 収穫を確認するまでは100%にしない。
    return min(95, max(0, combined)), (
        f"実の成熟段階70％＋実の確認から{elapsed}日（参考43日）の経過30％で算出。"
    )


def recorded_harvest_percent(record: dict) -> int | None:
    """履歴は診断当日に記録した値を優先し、古い履歴は分類値に戻す。"""
    raw = record.get("harvest_progress", "")
    if raw not in (None, ""):
        try:
            return max(0, min(100, round(float(raw) * 100)))
        except (ValueError, TypeError):
            pass
    return harvest_percent(record.get("fruit_model_label", ""))


def recorded_harvest_text(record: dict) -> str:
    value = recorded_harvest_percent(record)
    return f"{value}%" if value is not None else "判定なし"


def harvest_guidance(fruit_label: str) -> tuple[str, str]:
    return HARVEST_GUIDANCE.get(
        str(fruit_label or "").strip(),
        ("判定できません", "実が十分に写っているか確認してください。"),
    )


def save_diagnosis_history(record: dict, whole_file, leaf_file, fruit_file) -> None:
    # ゲストは診断結果・入力内容・写真を一切保存しない
    if not can_save_history():
        return

    whole_path = save_diagnosis_image(whole_file, "whole")
    leaf_path = save_diagnosis_image(leaf_file, "leaf")
    fruit_path = save_diagnosis_image(fruit_file, "fruit")

    row = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "grade": st.session_state.grade,
        "class_name": st.session_state.class_name,
        "student_number": st.session_state.student_number,
        "student_name": st.session_state.student_name,
        "plant_type": record["plant_type"],
        "planting_date": st.session_state.planting_date.isoformat(),
        "watered_today": record.get("watered_today", ""),
        "work_items": record.get("work_items", ""),
        "observation_note": record.get("observation_note", ""),
        "days_grown": record["days_grown"],
        "leaf_color_mark": record["leaf_color_mark"],
        "leaf_count_mark": record["leaf_count_mark"],
        "fruit_color_mark": record["fruit_color_mark"],
        "calyx_shape_mark": record["calyx_shape_mark"],
        "leaf_color_score": record["leaf_color_score"],
        "leaf_count_score": record["leaf_count_score"],
        "fruit_color_score": record["fruit_color_score"],
        "calyx_shape_score": record["calyx_shape_score"],
        "harvest_progress": round(float(record.get("harvest_progress", 0)), 2),
        "first_fruit_date": record.get("first_fruit_date", ""),
        "harvest_basis": record.get("harvest_basis", ""),
        "whole_image_path": whole_path,
        "leaf_image_path": leaf_path,
        "fruit_image_path": fruit_path,
        "whole_model_label": record.get("whole_model_label", ""),
        "leaf_model_label": record.get("leaf_model_label", ""),
        "fruit_model_label": record.get("fruit_model_label", ""),
        "whole_model_score": record.get("whole_model_score", ""),
        "leaf_model_score": record.get("leaf_model_score", ""),
        "fruit_model_score": record.get("fruit_model_score", ""),
        "model_observation": record.get("model_observation", ""),
        "model_advice": record.get("model_advice", ""),
    }

    append_csv(get_history_path(), HISTORY_COLUMNS, row)


def photo_uploader_card(
    title: str,
    help_text: str,
    sample_path: str,
    sample_caption: str,
    uploader_label: str,
    key: str,
):
    st.markdown('<div class="photo-card">', unsafe_allow_html=True)

    if title:
        st.markdown(f'<div class="photo-title">{title}</div>', unsafe_allow_html=True)
    if help_text:
        st.markdown(f'<div class="photo-help">{help_text}</div>', unsafe_allow_html=True)

    show_sample_image(sample_path, sample_caption)

    uploaded_file = st.file_uploader(
        "写真をアップロード",
        type=SUPPORTED_UPLOAD_TYPES,
        key=key,
        label_visibility="collapsed",
    )

    if uploaded_file is not None:
        try:
            st.image(validated_upload(uploaded_file), caption="アップロード済み", width=180)
        except ValueError as exc:
            st.warning(str(exc))

    st.markdown("</div>", unsafe_allow_html=True)
    return uploaded_file


def compare_with_previous(previous: dict | None, current: dict) -> list[str]:
    if previous is None:
        return ["今回が最初の診断です。これから成長を記録していきましょう。"]

    messages = []
    score_items = [
        ("葉の色", "leaf_color_score"),
        ("葉の数", "leaf_count_score"),
        ("実の色", "fruit_color_score"),
        ("ヘタの形", "calyx_shape_score"),
    ]

    for label, key in score_items:
        try:
            prev = int(float(previous[key]))
            now = int(float(current[key]))
        except Exception:
            continue

        if now > prev:
            messages.append(f"{label}：前回より良くなりました。")
        elif now < prev:
            messages.append(f"{label}：前回より少し下がりました。")
        else:
            messages.append(f"{label}：前回と同じくらいです。")

    return messages


def back_link(label: str, target_page: str = "home") -> None:
    href = "?back_home=1" if target_page == "home" else "?change_student=1"
    st.markdown(
        f'<div class="back-link-wrap"><a class="back-link" href="{href}">{label}</a></div>',
        unsafe_allow_html=True,
    )


def force_scroll_top() -> None:
    """Streamlitの仮想ページ切り替え後でも、できるだけ確実に一番上へ戻す。"""
    components.html(
        """
        <script>
        (function() {
            function goTop() {
                try {
                    const doc = window.parent.document;
                    const targets = [
                        window.parent,
                        doc.documentElement,
                        doc.body,
                        doc.querySelector('section.main'),
                        doc.querySelector('[data-testid="stAppViewContainer"]'),
                        doc.querySelector('[data-testid="stMain"]'),
                        doc.querySelector('.main')
                    ].filter(Boolean);

                    targets.forEach(function(t) {
                        try {
                            if (t.scrollTo) {
                                t.scrollTo(0, 0);
                            }
                            t.scrollTop = 0;
                        } catch(e) {}
                    });
                } catch(e) {}
            }
            [0, 50, 150, 300, 600, 1000, 1500].forEach(function(ms) {
                setTimeout(goTop, ms);
            });
        })();
        </script>
        """,
        height=0,
    )


# =========================================================
# ② ホーム画面（コンパクト版：PCは2列／スマホは1列）
# =========================================================
if st.session_state.page == "home":
    if st.session_state.get("force_scroll_top", False):
        force_scroll_top()
        st.session_state.force_scroll_top = False

    st.markdown(
        """
        <style>
        /* ホーム画面：読みやすい余白を確保。ほかの画面は変更しない */
        div[data-testid="stMainBlockContainer"] {
            max-width: 950px !important;
            padding-top: 0.35rem !important;
            padding-bottom: 1.25rem !important;
        }
        /* カード外側は適度にコンパクトに */
        div[data-testid="stMainBlockContainer"] > div > div[data-testid="stVerticalBlock"] {
            gap: 0.9rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.compact-home-card-title) {
            border-radius: 14px !important;
            padding: 0.4rem 0.2rem !important;
        }
        /* 各カード内の要素は重ならないよう縦間隔を確保 */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.compact-home-card-title)
        [data-testid="stVerticalBlock"] {
            gap: 0.9rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.compact-home-card-title)
        [data-testid="stElementContainer"] {
            min-height: 0;
        }
        .compact-home-heading {
            font-size: 22px; font-weight: 850; color: #184c32;
            margin: 10px 0 3px; line-height: 1.4;
        }
        .compact-home-sub {
            color: #5d7165; font-size: 14px; line-height: 1.55;
            margin: 0 0 8px;
        }
        .compact-home-card-title {
            font-size: 19px; font-weight: 850; color: #153e2d;
            line-height: 1.45; margin-bottom: 8px;
        }
        .compact-home-card-desc {
            font-size: 14px; color: #52645a; line-height: 1.6;
            margin-bottom: 3px;
        }
        /* ボタンは押しやすい高さを維持。強調色は診断だけ */
        div[data-testid="stMainBlockContainer"] .stButton > button,
        div[data-testid="stMainBlockContainer"] .stLinkButton > a {
            min-height: 44px !important;
            font-size: 14px !important;
            font-weight: 800 !important;
            box-shadow: none !important;
            border-radius: 10px !important;
        }
        div[data-testid="stMainBlockContainer"] .stButton > button[kind="secondary"]:not(:disabled) {
            background: #fff !important;
            color: #207d43 !important;
            border: 1px solid #91c7a0 !important;
        }
        .st-key-home_start_diagnosis button {
            background:#fff !important;
            color:#207d43 !important;
            border:1px solid #91c7a0 !important;
        }
        div[data-testid="stMainBlockContainer"] .stButton > button:disabled {
            background: #f0f2f0 !important;
            color: #818b85 !important;
            border: 1px solid #e0e5e1 !important;
        }
        @media (max-width: 640px) {
            .compact-home-heading {font-size: 20px;}
            .compact-home-card-title {font-size: 18px;}
            .compact-home-sub,.compact-home-card-desc {font-size: 13px;}
        }
        </style>
        <div class="compact-home-heading">作物を診断する</div>
        <div class="compact-home-sub">診断はログイン不要。記録を残したいときだけログインしてください。</div>
        """,
        unsafe_allow_html=True,
    )

    diagnose_col, history_col = st.columns(2, gap="small")
    with diagnose_col:
        with st.container(border=True):
            st.markdown('<div class="compact-home-card-title">AI生育診断</div>'
                        '<div class="compact-home-card-desc">全体写真1枚から診断します。</div>',
                        unsafe_allow_html=True)
            if st.button("AI生育診断をはじめる", type="secondary", use_container_width=True,
                         key="home_start_diagnosis"):
                st.session_state.page = "diagnosis_upload"
                st.session_state.force_scroll_top = True
                st.rerun()
    with history_col:
        with st.container(border=True):
            st.markdown('<div class="compact-home-card-title">成長の記録</div>'
                        '<div class="compact-home-card-desc">保存した診断結果や栽培記録を確認できます。</div>',
                        unsafe_allow_html=True)
            if st.button("成長の記録を見る", use_container_width=True, key="home_open_history"):
                if can_save_history():
                    st.session_state.page = "history_calendar"
                    st.session_state.force_scroll_top = True
                    st.rerun()
                else:
                    st.session_state.page = "account"
                    st.session_state.login_view = "login"
                    st.rerun()

    if st.session_state.get("show_history_login_help") and not can_save_history():
        st.info("成長の記録を見るには、右上の『ログイン・登録』からログインしてください。")

    st.markdown('<div class="compact-home-heading">AIの開発・改善</div>', unsafe_allow_html=True)
    model_col, program_col = st.columns(2, gap="small")
    with model_col:
        with st.container(border=True):
            st.markdown('<div class="compact-home-card-title">① AIモデルを改善する</div>'
                        '<div class="compact-home-card-desc">学習写真を追加・分類し、AIの判定精度を高めます。</div>',
                        unsafe_allow_html=True)
            if st.button("AIモデルの改善へ", use_container_width=True, key="home_open_model_registry"):
                st.session_state.page = "model_improve"
                st.session_state.force_scroll_top = True
                st.rerun()
    with program_col:
        with st.container(border=True):
            st.markdown('<div class="compact-home-card-title">② プログラムを改善する</div>'
                        '<div class="compact-home-card-desc">診断結果に応じた条件分岐やアドバイスを変更します。</div>',
                        unsafe_allow_html=True)
            st.button("プログラムの改善へ（準備中）", use_container_width=True,
                      key="home_program_pending", disabled=True)
            st.caption("教材用の編集画面は今後追加します。")

    with st.expander("GitHub・アプリの開発に参加する"):
        st.link_button("ソースコードを見る", "https://github.com/yuika200-cmyk/tomato-diagnosis-lab",
                       use_container_width=True)
        st.link_button("参加方法を見る", "https://github.com/yuika200-cmyk/tomato-diagnosis-lab/blob/main/CONTRIBUTING.md",
                       use_container_width=True)
    st.caption("現在の診断対象はミニトマトです。AIの判定は参考情報としてご利用ください。")


# =========================================================
# =========================================================
# ログイン・登録・パスワード再設定画面
# =========================================================
elif st.session_state.page == "account":
    auth_screen.show()

# =========================================================
# ③ 写真アップロード画面
# =========================================================
elif st.session_state.page == "diagnosis_upload":
    if st.session_state.get("force_scroll_top", False):
        force_scroll_top()
        st.session_state.force_scroll_top = False

    # 画面統合版：入力は植え付け日（任意）・全体写真・実の有無の3点のみ。
    st.session_state.plant_type = "トマト"
    plant_type = st.session_state.plant_type
    today_text = date.today().strftime("%Y/%m/%d")

    # 診断画面だけを程よくコンパクトにする（結果画面やホームは変更しない）。
    st.markdown("""
    <style>
      /* 診断画面だけ：ページ上部と共通ヘッダーの余白を縮める */
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title) {
        max-width: 850px !important;
        padding-top: 0.6rem !important;
        padding-bottom: 1rem !important;
      }
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title)
      > div > div[data-testid="stVerticalBlock"] {
        gap: 0.4rem !important;
      }
      .diagnosis-header-rule {height:1px;background:#dce6df;margin:0 0 2px;}
      .diagnosis-new-title { font-size: 27px; font-weight: 900; color: #153e2d; margin: 0 0 3px; }
      .diagnosis-new-meta { color: #52645a; font-size: 13px; margin-bottom: 5px; }
      .diagnosis-new-section { font-size: 19px; font-weight: 850; color: #173e2c; margin: 2px 0 1px; }
      .diagnosis-new-help { color: #596b61; font-size: 13px; margin: 0 0 4px; }
      .diagnosis-photo-label {font-size: 14px;font-weight: 750;color:#173e2c;margin:0 0 5px;}
      .diagnosis-back-link {text-align:center;margin:8px 0 4px;}
      .diagnosis-back-link a {font-size:13px;color:#62756a;text-decoration:none;padding:5px 10px;}
      .diagnosis-back-link a:hover {color:#4f6159;text-decoration:underline;}
      .diagnosis-back-link a:visited {color:#62756a;}

      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title) [data-testid="stFileUploaderDropzone"] {
        min-height: 150px !important;
      }

      /* この画面では縦の基本間隔を少し詰める。重なりが出ない値にする。 */
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title)
      [data-testid="stCheckbox"] {margin: 0 !important;}
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title)
      [data-testid="stHorizontalBlock"] {align-items:start;}

      div[data-testid="stMainBlockContainer"] [data-testid="stDivider"] { margin: 0.15rem 0 !important; }
      div[data-testid="stFileUploader"] { margin-top: 0 !important; }
      div[data-testid="stFileUploader"] section,
      div[data-testid="stFileUploaderDropzone"] {
        min-height: 125px !important;
        padding: 12px !important;
      }
      /* 選択ボタンの文字が縦に折り返されないようにする。 */
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title)
      [data-testid="stFileUploader"] button {
        white-space: nowrap !important;
        min-width: 140px !important;
        font-size: 15px !important;
        padding: 0 18px !important;
      }
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title)
      [data-testid="stFileUploaderDropzone"] {
        align-items: center !important;
        justify-content: center !important;
      }
      /* 写真選択ボタンを真ん中に。元の英語ラベルの幅も消す。 */
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title)
      [data-testid="stFileUploader"] button {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 170px !important;
        min-width: 170px !important;
        margin: 0 auto !important;
        padding: 0 12px !important;
        font-size: 0 !important;
        line-height: 1 !important;
        text-align: center !important;
      }
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title)
      [data-testid="stFileUploader"] button::after {
        content: "写真を選ぶ" !important;
        display: block !important;
        font-size: 15px !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
      }
      /* 写真選択ボタン：標準ラベルの幅に左右されず、表示文字を厳密に中央へ。 */
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title)
      [data-testid="stFileUploader"] button {
        position: relative !important;
        display: block !important;
        width: 170px !important;
        height: 44px !important;
        min-width: 170px !important;
        max-width: 170px !important;
        margin-inline: auto !important;
        padding: 0 !important;
        font-size: 0 !important;
        line-height: 0 !important;
        text-align: center !important;
      }
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title)
      [data-testid="stFileUploader"] button > * {
        visibility: hidden !important;
      }
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title)
      [data-testid="stFileUploader"] button::after {
        content: "写真を選ぶ" !important;
        display: block !important;
        position: absolute !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        width: max-content !important;
        font-size: 15px !important;
        line-height: 1.2 !important;
        font-weight: 800 !important;
        color: #2f8f47 !important;
        white-space: nowrap !important;
        pointer-events: none !important;
      }
      /* 選択後の「写真を変更する」は控えめな灰色の文字ボタンに。 */
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title)
      .st-key-diagnosis_change_photo button {
        background: transparent !important;
        color: #77837c !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 6px !important;
        font-size: 12px !important;
        font-weight: 500 !important;
        min-height: 28px !important;
        height: 28px !important;
        padding: 2px 8px !important;
      }
      div[data-testid="stMainBlockContainer"]:has(.diagnosis-new-title)
      .st-key-diagnosis_change_photo button:hover {
        background: #f2f5f2 !important;
        color: #5a6960 !important;
        box-shadow: none !important;
      }
      /* 診断するボタンは操作しやすい高さを確保。 */
      div[data-testid="stMainBlockContainer"] .stButton button { min-height: 44px; }
      @media (max-width: 640px) {
        .diagnosis-new-title { font-size: 24px; }
        .diagnosis-new-section { font-size: 18px; }
      }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="diagnosis-new-title">今日の診断</div>'
                f'<div class="diagnosis-new-meta">記録日：{today_text}　｜　対象：ミニトマト</div>',
                unsafe_allow_html=True)

    st.markdown('<div class="diagnosis-new-section">① 植え付け日</div>', unsafe_allow_html=True)
    known = st.checkbox("植え付け日が分かる", value=st.session_state.planting_date_known,
                        key="diagnosis_planting_known")
    st.session_state.planting_date_known = known
    if known:
        st.session_state.planting_date = st.date_input(
            "植え付け日", value=min(st.session_state.planting_date, date.today()),
            max_value=date.today(), key="diagnosis_planting_date")

    st.markdown('<div class="diagnosis-header-rule"></div>', unsafe_allow_html=True)
    st.markdown('<div class="diagnosis-new-section">② 写真をアップロード</div>'
                '<div class="diagnosis-new-help">ミニトマトの全体が写る写真を1枚選んでください。</div>',
                unsafe_allow_html=True)
    # 左：お手本写真／右：写真選択（選択後は同じ列にプレビュー）。
    # 画像はPillowで検証・変換し、StreamlitにJPEGバイト列として渡す。
    # 画像表示用の縮小・余白追加はAI判定に利用する画像には影響しない。
    def display_preview_bytes(image: Image.Image) -> bytes:
        canvas_size = (640, 360)
        preview = ImageOps.contain(
            ImageOps.exif_transpose(image).convert("RGB"),
            canvas_size,
            method=Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGB", canvas_size, (248, 251, 249))
        canvas.paste(preview, ((640 - preview.width) // 2, (360 - preview.height) // 2))
        output = io.BytesIO()
        canvas.save(output, format="JPEG", quality=88)
        return output.getvalue()

    # Streamlit のメディア配信URLを使わずに、表示用JPEGをHTMLに直接埋め込む。
    # AI判定用の元画像データには一切触れない。
    def show_inline_preview(image: Image.Image) -> None:
        encoded = base64.b64encode(display_preview_bytes(image)).decode("ascii")
        st.markdown(
            '<img src="data:image/jpeg;base64,' + encoded + '" '
            'style="display:block;width:100%;aspect-ratio:16/9;object-fit:contain;'
            'border-radius:10px;border:1px solid #e0e9e2;" '
            'alt="ミニトマトの写真">',
            unsafe_allow_html=True,
        )

    sample_col, upload_col = st.columns(2, gap="medium")
    with sample_col:
        st.markdown('<div class="diagnosis-photo-label">全体写真のお手本</div>', unsafe_allow_html=True)
        sample_path = APP_DIR / "sample_whole_image.png"
        if sample_path.is_file():
            try:
                with Image.open(sample_path) as sample_source:
                    sample_source.load()
                    show_inline_preview(sample_source)
            except Exception as exc:
                LOGGER.exception("Sample image failed to load: %s", sample_path)
                st.error("お手本写真を表示できません。画像ファイルの中身を確認してください。")
                st.caption(f"ファイル: {sample_path.name} / {type(exc).__name__}: {exc}")
        else:
            st.warning("お手本写真が見つかりません。")
            st.caption(f"確認先：{sample_path}")

    with upload_col:
        st.markdown('<div class="diagnosis-photo-label">選択した写真</div>', unsafe_allow_html=True)

        # アップロード済みなら、大きな選択枠の代わりに写真を表示する。
        # Widgetが一時的に非表示でも診断できるよう、元画像のバイト列を保持。
        saved_photo = st.session_state.get("diagnosis_selected_photo_bytes")
        if saved_photo is None:
            uploaded = st.file_uploader(
                "全体写真をアップロード",
                type=SUPPORTED_UPLOAD_TYPES,
                key="diagnosis_whole",
                label_visibility="collapsed",
            )
            if uploaded is not None:
                try:
                    # エラー画像を保存しないよう、最初に検証する。
                    checked_image = validated_upload(uploaded)
                    saved_photo = uploaded.getvalue()
                    st.session_state.diagnosis_selected_photo_bytes = saved_photo
                    # アップロードが完了したら直ちに描画をやり直し、
                    # 大きなアップロード枠を消して右列を写真に置き換える。
                    st.rerun()
                except ValueError as exc:
                    st.warning(str(exc))
            else:
                st.caption("JPG・PNG・HEIC／最大10MB")
        else:
            try:
                show_inline_preview(validated_upload(io.BytesIO(saved_photo)))
            except ValueError as exc:
                st.warning(str(exc))
                saved_photo = None
                st.session_state.diagnosis_selected_photo_bytes = None

        if saved_photo is not None:
            # 次のクリック時に状態を解除し、アップロード欄を再表示。
            if st.button("写真を変更する", key="diagnosis_change_photo", type="secondary"):
                st.session_state.diagnosis_selected_photo_bytes = None
                st.rerun()

    # モデル入力用には加工していない元のアップロード画像を渡す。
    whole_file = io.BytesIO(saved_photo) if saved_photo is not None else None

    fruit_visible = st.radio(
        "写真に実が写っていますか？", ["写っている", "写っていない"],
        index=1, horizontal=True,
        help="『写っていない』場合は実の成熟度を診断しません。") == "写っている"

    # AIの結果を見る前に自己評価する。入力しなくても診断できる。
    # 選択肢は現在のAIモデルの分類名と対応させる。
    st.markdown('<div class="diagnosis-header-rule"></div>', unsafe_allow_html=True)
    st.markdown('<div class="diagnosis-new-section">③ 自分で観察してみよう（任意）</div>',
                unsafe_allow_html=True)
    self_options = {
        "whole": ["未選択", "良好", "葉が重なっている", "誘引必要"],
        "leaf": ["未選択", "良好", "白い斑点が見られる", "葉が黄色い", "葉が淡い黄緑色",
                 "しおれている", "葉が濃い緑色", "虫食い", "要注意"],
        "fruit": ["未選択", "成長途中", "成長中", "成熟中", "収穫間近", "成長段階"],
    }
    col_whole, col_leaf, col_fruit = st.columns(3, gap="small")
    with col_whole:
        self_whole = st.selectbox("株全体", self_options["whole"], key="self_eval_whole")
    with col_leaf:
        self_leaf = st.selectbox("葉", self_options["leaf"], key="self_eval_leaf")
    with col_fruit:
        self_fruit = (st.selectbox("実", self_options["fruit"], key="self_eval_fruit")
                      if fruit_visible else "未選択")

    # 実の初確認日は入力しないため、収穫進行度はAIの成熟段階のみを使用。
    first_fruit_date = None
    # 従来の履歴項目は互換性のため残し、未入力として保存する。
    watered_today = "未入力"
    work_items = []

    missing_models = [key for key in MODEL_NAMES if not (MODEL_DIR / key / "keras_model.h5").is_file() or not (MODEL_DIR / key / "labels.txt").is_file()]
    if missing_models:
        st.error("AI診断用の学習済みモデルが未配置です。管理者にお問い合わせください。写真や記録は送信されません。")

    if st.button("診断する", use_container_width=True, disabled=bool(missing_models)):
        if whole_file is None:
            st.warning("全体写真を1枚アップロードしてください。")
        elif plant_type != "トマト":
            st.warning("現在の3つのAIモデルはトマト用です。トマトを選んで診断してください。")
        else:
            try:
                with st.spinner("AIモデルで診断しています..."):
                    predictions = predict_three_models(whole_file, include_fruit=fruit_visible)
            except ValueError as exc:
                st.warning(str(exc))
            except Exception:
                LOGGER.exception("AI diagnosis failed")
                st.error("診断中に問題が起きました。別の写真で再試行してください。解決しない場合は管理者にお問い合わせください。")
            else:
                days_grown = (calculate_days_grown(st.session_state.planting_date, date.today())
                              if st.session_state.planting_date_known else "不明")
                if fruit_visible:
                    progress_value, harvest_basis = estimate_harvest_progress(
                        predictions["fruit"]["label"], first_fruit_date, date.today()
                    )
                else:
                    progress_value, harvest_basis = None, "今回の写真に実が写っていないため、算出していません。"
                record = {
                    "plant_type": plant_type,
                    "days_grown": days_grown,
                    "watered_today": watered_today,
                    "work_items": "、".join(work_items) if work_items else "なし",
                    "observation_note": "",
                    "leaf_color_mark": "", "leaf_count_mark": "", "fruit_color_mark": "", "calyx_shape_mark": "",
                    "leaf_color_score": "", "leaf_count_score": "", "fruit_color_score": "", "calyx_shape_score": "",
                    "harvest_progress": (progress_value / 100 if progress_value is not None else ""),
                    "first_fruit_date": first_fruit_date.isoformat() if first_fruit_date else "",
                    "harvest_basis": harvest_basis,
                    "model_observation": model_signs(predictions),
                    "model_advice": model_advice(predictions),
                }
                for key in MODEL_NAMES:
                    if key in predictions:
                        record[f"{key}_model_label"] = predictions[key]["label"]
                        record[f"{key}_model_score"] = predictions[key]["score"]
                    else:
                        record[f"{key}_model_label"] = "実なし（未診断）"
                        record[f"{key}_model_score"] = ""
                # 履歴DBの列を増やさず、今回の自己評価を画面表示用に保持する。
                # 保存時には既存の observation_note に読みやすい文章で記録する。
                st.session_state.diagnosis_self_evaluation = {
                    "whole": self_whole if self_whole != "未選択" else "",
                    "leaf": self_leaf if self_leaf != "未選択" else "",
                    "fruit": self_fruit if self_fruit != "未選択" else "",
                }
                st.session_state.previous_record = load_last_history()
                st.session_state.diagnosis_record = record
                st.session_state.pop("diagnosis_observation_memo", None)
                st.session_state.diagnosis_photo_bytes = None
                if can_save_history():
                    picture = validated_upload(whole_file)
                    buffer = io.BytesIO()
                    picture.save(buffer, format="JPEG", quality=83)
                    st.session_state.diagnosis_photo_bytes = buffer.getvalue()
                st.session_state.diagnosis_saved = False
                st.session_state.diagnosis_saved_note = None
                st.session_state.diagnosis_saved_record_id = None
                st.session_state.force_scroll_top = True
                st.session_state.page = "diagnosis_result"
                st.rerun()



# =========================================================
# ④ 結果画面
# =========================================================
elif st.session_state.page == "diagnosis_result":
    record = st.session_state.diagnosis_record
    if st.session_state.get("force_scroll_top", False):
        force_scroll_top()
        st.session_state.force_scroll_top = False

    if record is None:
        st.warning("まだ診断記録がありません。")
        bottom_back_button()
        st.stop()

    # この画面にだけ適用するCSS。既存のホーム・写真アップロード画面は変更しない。
    st.markdown("""
    <style>
      .result-v2-heading {font-size:26px;font-weight:900;color:#153e2d;margin:0 0 4px;line-height:1.3;}
      .result-v2-date {color:#65746c;font-size:13px;font-weight:600;}
      .result-v2-day {font-size:14px;color:#315b43;margin:2px 0 4px;}
      .result-v2-section {border:1px solid #dce8de;border-radius:15px;padding:12px 16px;
        background:rgba(255,255,255,.95);margin:6px 0 8px;}
      .result-v2-section-title {font-size:18px;font-weight:900;color:#153e2d;margin-bottom:5px;}
      .result-v2-item {display:grid;grid-template-columns:92px minmax(85px,140px) 1fr;
        align-items:center;gap:10px;padding:8px 0;border-bottom:1px dashed #dce6df;}
      .result-v2-item:last-child {border-bottom:0;}
      .result-v2-name {font-weight:850;color:#173e2c;}
      .result-v2-status {font-weight:850;color:#216d42;overflow-wrap:anywhere;}
      .result-v2-comment {font-size:14px;color:#3c5246;line-height:1.4;overflow-wrap:anywhere;}
      .result-v2-advice {border:1px solid #9dd1ae;border-radius:15px;padding:12px 16px;
        background:white;margin:7px 0 4px;}
      .result-v2-advice-title {font-size:20px;font-weight:900;color:#14663b;margin-bottom:7px;}
      .result-v2-advice-content {font-size:16px;font-weight:700;color:#213d2d;line-height:1.6;
        background:#f0f8f1;border-radius:10px;padding:10px 13px;white-space:pre-wrap;}
      .result-v2-note {font-size:12px;color:#66746b;line-height:1.5;margin:7px 0 3px;}
      .result-v2-memo-title {font-size:18px;font-weight:900;color:#173e2c;margin-top:2px;}
      .result-v2-memo-help {font-size:13px;color:#65746c;margin:0 0 4px;}
      .result-v2-compare {border:1px solid #dce8de;border-radius:14px;padding:12px 16px;background:#fbfdfb;margin:7px 0;}
      .result-v2-compare-title {font-size:17px;font-weight:900;color:#173e2c;margin-bottom:7px;}
      .result-v2-compare-row {display:grid;grid-template-columns:75px 1fr 1fr;gap:8px;
        padding:7px 0;border-top:1px dashed #dce6df;font-size:14px;align-items:center;}
      .result-v2-compare-head {font-size:12px;font-weight:800;color:#65746c;}
      .result-v2-compare-note {font-size:12px;color:#66746b;margin-top:7px;}

      /* 診断結果・自己評価の統合表 */
      .result-v2-unified-row {display:grid;align-items:start;gap:10px;
        padding:10px 0;border-bottom:1px dashed #dce6df;font-size:14px;color:#2d493a;}
      .result-v2-unified-row:last-of-type {border-bottom:none;}
      .result-v2-unified-row.comparison {grid-template-columns:80px minmax(0,1fr) minmax(0,1.2fr) 74px;}
      .result-v2-unified-row.simple {grid-template-columns:80px minmax(75px,120px) minmax(0,1fr);align-items:center;}
      .result-v2-unified-name {font-weight:850;color:#173e2c;}
      .result-v2-unified-comment {font-size:12px;font-weight:500;color:#66746b;line-height:1.4;margin-top:2px;}
      .result-v2-unified-head {font-size:12px;font-weight:800;color:#65746c;padding:5px 0;}
      .result-v2-unified-flag {font-size:12px;font-weight:800;white-space:nowrap;}
      .result-v2-unified-flag.match {color:#22844e;}
      .result-v2-unified-flag.diff {color:#aa6b13;}
      .result-v2-unified-flag.neutral {color:#7b8980;}
      @media(max-width:680px) {
        .result-v2-unified-row {gap:5px;font-size:12px;}
        .result-v2-unified-row.comparison {grid-template-columns:49px minmax(0,1fr) minmax(0,1.1fr) 54px;}
        .result-v2-unified-row.simple {grid-template-columns:52px minmax(58px,92px) minmax(0,1fr);}
        .result-v2-unified-head,.result-v2-unified-flag {font-size:10px;}
        .result-v2-unified-comment {font-size:11px;}
      }
      /* 結果画面のみ: アプリ名の上・ヘッダー下の無駄な余白を減らす */
      div[data-testid="stMainBlockContainer"]:has(.result-v2-heading) {
        padding-top: 0.35rem !important;
        padding-bottom: 1rem !important;
      }
      div[data-testid="stMainBlockContainer"]:has(.result-v2-heading)
      > div > div[data-testid="stVerticalBlock"] {
        gap: 0.45rem !important;
      }
      div[data-testid="stMainBlockContainer"]:has(.result-v2-heading)
      [data-testid="stHorizontalBlock"] { margin-bottom: 0 !important; }
      /* 結果タイトルと日付をまとめ、上部を小さくする */
      .result-v2-topline {display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin:1px 0 2px;}
      .result-v2-heading {margin:0 !important;font-size:25px;}
      .result-v2-date {white-space:nowrap;}
      /* 比較表: 列の見やすさと状態ラベルを改善 */
      .result-v2-section {padding:14px 17px;margin:3px 0 5px;}
      .result-v2-section-title {font-size:19px;margin-bottom:8px;}
      .result-v2-unified-row {gap:14px;padding:11px 8px;font-size:14px;line-height:1.45;align-items:center;}
      .result-v2-unified-row.comparison {grid-template-columns:75px minmax(0,1.15fr) minmax(0,1.35fr) 84px;}
      .result-v2-unified-row.simple {grid-template-columns:82px minmax(85px,145px) minmax(0,1fr);}
      .result-v2-unified-head {background:#f4f8f5;border-radius:7px;padding:8px 8px;font-size:12px;}
      .result-v2-unified-comment {margin-top:3px;font-size:12px;}
      .result-v2-unified-flag {display:inline-block;width:fit-content;padding:4px 8px;border-radius:999px;font-size:12px;}
      .result-v2-unified-flag.match {background:#e9f6ed;color:#1e7c45;}
      .result-v2-unified-flag.diff {background:#fff2df;color:#9d5e00;}
      .result-v2-unified-flag.neutral {background:#f1f3f1;color:#66746b;}
      .result-v2-advice {margin:6px 0 3px;padding:13px 16px;}
      .result-v2-advice-content {font-size:15px;line-height:1.55;}
      @media(max-width:680px) {
        .result-v2-topline {align-items:center;}
        .result-v2-heading {font-size:22px;}
        .result-v2-section {padding:11px 10px;}
        .result-v2-unified-row {gap:5px;padding:9px 3px;font-size:12px;}
        .result-v2-unified-row.comparison {grid-template-columns:44px minmax(0,1fr) minmax(0,1fr) 56px;}
        .result-v2-unified-row.simple {grid-template-columns:47px 72px minmax(0,1fr);}
        .result-v2-unified-head {font-size:10px;}
        .result-v2-unified-flag {font-size:10px;padding:3px 4px;}
        .result-v2-unified-comment {font-size:11px;}
      }
      /* 文字を読みやすくする調整：結果画面のみに適用 */
      .result-v2-section-title {font-size:22px;line-height:1.4;margin-bottom:10px;}
      .result-v2-unified-row {font-size:17px;line-height:1.55;padding:12px 8px;gap:12px;}
      .result-v2-unified-head {font-size:14px;line-height:1.35;padding:8px;}
      .result-v2-unified-name {font-size:17px;}
      .result-v2-unified-comment {font-size:14px;line-height:1.5;margin-top:3px;}
      .result-v2-unified-flag {font-size:14px;padding:5px 9px;}
      .result-v2-compare-note {font-size:13px;line-height:1.5;margin-top:9px;}
      .result-v2-advice-title {font-size:22px;}
      .result-v2-advice-content {font-size:17px;line-height:1.65;padding:12px 14px;}
      .result-v2-note {font-size:13px;line-height:1.6;}
      .result-v2-memo-title {font-size:20px;}
      .result-v2-memo-help {font-size:15px;line-height:1.5;}
      div[data-testid="stMainBlockContainer"]:has(.result-v2-heading) textarea {
        font-size:16px !important;line-height:1.55 !important;
      }
      @media(max-width:680px) {
        .result-v2-section-title {font-size:19px;}
        .result-v2-unified-row {font-size:14px;gap:5px;padding:10px 3px;}
        .result-v2-unified-name {font-size:14px;}
        .result-v2-unified-head {font-size:12px;}
        .result-v2-unified-flag {font-size:11px;padding:3px 5px;}
        .result-v2-unified-comment {font-size:12px;}
        .result-v2-advice-content {font-size:16px;}
      }
      .result-v2-back {text-align:center;margin:7px 0 0;}
      .result-v2-back a {font-size:13px;color:#758079;text-decoration:none;}
      .result-v2-back a:hover {text-decoration:underline;color:#526158;}
      @media(max-width:680px) {
        .result-v2-item {grid-template-columns:68px 1fr;gap:3px 9px;padding:7px 0;}
        .result-v2-comment {grid-column:2;}
        .result-v2-section {padding:11px 10px;}
        .result-v2-advice {padding:11px 12px;}
      }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(
        '<div class="result-v2-topline"><div class="result-v2-heading">診断結果</div>'
        f'<div class="result-v2-date">記録日：{date.today().strftime("%Y/%m/%d")}</div></div>',
        unsafe_allow_html=True,
    )
    if isinstance(record.get("days_grown"), int):
        st.markdown(
            f'<div class="result-v2-day">🌱 育て始めて <b>{record["days_grown"]}日目</b></div>',
            unsafe_allow_html=True,
        )

    # 診断結果と自己評価を1つの表に統合する。
    # 自己評価がなければ従来の「今日のようす」を表示する。
    self_eval = st.session_state.get("diagnosis_self_evaluation", {}) or {}
    visible = []
    for key, name in (("whole", "株全体"), ("leaf", "葉"), ("fruit", "実")):
        ai_label = record.get(f"{key}_model_label", "")
        if key == "fruit" and ai_label in ("実なし（未診断）", ""):
            continue
        visible.append((key, name, ai_label))

    has_self_eval = any(self_eval.get(key) for key, _, _ in visible)
    rows = []
    for key, name, ai_label in visible:
        ai_text = ai_label or "記録なし"
        comment = model_comment(key, ai_label) if ai_label else "診断結果がありません。"
        own = self_eval.get(key, "")
        if has_self_eval:
            if own and ai_label:
                same = own == _normalize_advice_label(key, ai_label)
                comparison = "一致" if same else "違いあり"
                comparison_class = "match" if same else "diff"
            else:
                comparison = "—"
                comparison_class = "neutral"
            rows.append(
                '<div class="result-v2-unified-row comparison">'
                f'<div class="result-v2-unified-name">{escape(name)}</div>'
                f'<div>{escape(own or "—")}</div>'
                f'<div><span class="result-v2-status">{escape(ai_text)}</span>'
                f'<div class="result-v2-unified-comment">{escape(comment)}</div></div>'
                f'<div class="result-v2-unified-flag {comparison_class}">{comparison}</div>'
                '</div>'
            )
        else:
            rows.append(
                '<div class="result-v2-unified-row simple">'
                f'<div class="result-v2-unified-name">{escape(name)}</div>'
                f'<div class="result-v2-status">{escape(ai_text)}</div>'
                f'<div class="result-v2-unified-comment">{escape(comment)}</div>'
                '</div>'
            )

    if has_self_eval:
        title = "今日のようす・AIとの比較"
        header = (
            '<div class="result-v2-unified-row comparison result-v2-unified-head">'
            '<span>項目</span><span>自分の評価</span><span>AIの判定</span><span>比較</span>'
            '</div>'
        )
        note = ('<div class="result-v2-compare-note">'
                '※ 一致・不一致は正解・不正解を意味しません。実際の作物を観察して確認しましょう。'
                '</div>')
    else:
        title = "今日のようす"
        header = ''
        note = ''

    st.markdown(
        '<div class="result-v2-section">'
        f'<div class="result-v2-section-title">{title}</div>'
        + header + ''.join(rows) + note + '</div>', unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="result-v2-advice"><div class="result-v2-advice-title">💡 今日のアドバイス</div>'
        f'<div class="result-v2-advice-content">{escape(record.get("model_advice", "") or "アドバイスはありません。")}</div>'
        '<div class="result-v2-note">ⓘ AIの診断結果は参考情報です。実際の作物の状態や栽培記録も確認してください。</div>'
        '</div>', unsafe_allow_html=True,
    )

    st.markdown('<div class="result-v2-memo-title">📝 観察メモ</div>', unsafe_allow_html=True)
    st.markdown('<div class="result-v2-memo-help">気づいたことや、実際に観察したようすを記録しましょう。</div>', unsafe_allow_html=True)
    if "diagnosis_observation_memo" not in st.session_state:
        st.session_state.diagnosis_observation_memo = record.get("observation_note", "")
    memo = st.text_area(
        "観察メモ", key="diagnosis_observation_memo", height=76,
        placeholder="例：下の葉が黄色くなっていた。",
        label_visibility="collapsed", max_chars=2000,
    )
    # 保存ボタンを押す前に、クラウド保存へ渡すレコードにメモを反映する。
    # 既存の観察メモ列に自己評価も保存する（DBスキーマ変更不要）。
    self_eval = st.session_state.get("diagnosis_self_evaluation", {})
    names = {"whole": "株全体", "leaf": "葉", "fruit": "実"}
    self_lines = [f"{names[k]}：{self_eval[k]}" for k in ("whole", "leaf", "fruit") if self_eval.get(k)]
    if self_lines:
        record["observation_note"] = "【自己評価】\n" + "\n".join(self_lines) + ("\n【観察メモ】\n" + memo if memo else "")
    else:
        record["observation_note"] = memo

    if can_save_history():
        # 初回は診断結果を1件だけ保存し、以後メモはその記録を更新する。
        if not st.session_state.get("diagnosis_saved", False):
            try:
                previous_ids = {
                    str(item.get("id"))
                    for item in history_cloud.list_history()
                    if item.get("id") is not None
                }
                save_result = history_cloud.save(
                    record, st.session_state.get("diagnosis_photo_bytes")
                )
                record_id = None
                if isinstance(save_result, dict):
                    record_id = save_result.get("id")
                if not record_id:
                    added_rows = [
                        item for item in history_cloud.list_history()
                        if item.get("id") is not None
                        and str(item.get("id")) not in previous_ids
                    ]
                    if len(added_rows) == 1:
                        record_id = added_rows[0]["id"]
                st.session_state.diagnosis_saved = True
                st.session_state.diagnosis_saved_record_id = record_id
                st.session_state.diagnosis_saved_note = record["observation_note"]
                st.session_state.diagnosis_autosave_error = False
            except Exception:
                LOGGER.exception("Cloud history auto save failed")
                st.session_state.diagnosis_autosave_error = True

        if st.session_state.get("diagnosis_saved", False):
            record_id = st.session_state.get("diagnosis_saved_record_id")
            saved_note = st.session_state.get("diagnosis_saved_note")
            if record["observation_note"] != saved_note:
                if not record_id:
                    st.warning("メモの保存先を特定できません。画面を移動する前に管理者へお問い合わせください。")
                else:
                    try:
                        history_note_sync.update_note(record_id, record["observation_note"])
                        st.session_state.diagnosis_saved_note = record["observation_note"]
                    except Exception:
                        LOGGER.exception("Observation memo update failed")
                        st.error("観察メモを反映できませんでした。通信状況を確認してください。")
            elif record_id:
                st.caption("診断結果・観察メモは自動保存されます。")
            else:
                st.caption("診断結果は自動保存されました。")
        else:
            st.error("診断結果を自動保存できませんでした。接続を確認してください。")
            if st.button("保存を再試行", key="result_autosave_retry"):
                st.rerun()

        if st.button("成長の記録を見る", use_container_width=True, key="result_history"):
            st.session_state.page = "history_calendar"
            st.rerun()
    else:
        st.caption("ゲスト利用では診断履歴と観察メモは保存されません。")



# =========================================================
# ⑤ 成長のきろく：アルバム表示
# =========================================================
elif st.session_state.page == "history_calendar":
    if st.session_state.get("force_scroll_top", False):
        force_scroll_top()
        st.session_state.force_scroll_top = False

    st.markdown('<div class="history-v3-title">成長の記録</div>', unsafe_allow_html=True)
    st.markdown('<div class="history-v3-lead">保存した診断結果や観察メモを、日付ごとに確認できます。</div>', unsafe_allow_html=True)

    rows = load_history_rows()
    if not rows:
        st.info("まだ記録がありません。ログインした状態で診断すると、結果が自動保存されます。")
        bottom_back_button()
        st.stop()

    rows_sorted = list(reversed(rows))
    if st.session_state.pop("history_delete_success", False):
        st.success("記録を削除しました。")

    def first_image_path(row: dict) -> str:
        for key in ("whole_image_path", "leaf_image_path", "fruit_image_path"):
            path_text = row.get(key, "") or ""
            if isinstance(path_text, str) and (path_text.startswith("https://") or Path(path_text).exists()):
                return path_text
        return ""

    for row_start in range(0, len(rows_sorted), 3):
        cols = st.columns(3, gap="medium")
        for offset, col in enumerate(cols):
            idx = row_start + offset
            if idx >= len(rows_sorted):
                continue
            row = rows_sorted[idx]
            img_path = first_image_path(row)
            day_text = format_history_date(row.get("created_at", ""))
            with col:
                with st.container(border=True):
                    if img_path:
                        try:
                            st.image(img_path, width=220)
                        except Exception:
                            st.markdown('<div class="history-v3-no-photo">写真を表示できません</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="history-v3-no-photo">写真なし</div>', unsafe_allow_html=True)

                    st.markdown(f'<div class="history-v3-date">{escape(day_text)}</div>', unsafe_allow_html=True)
                    summary = []
                    for key, label in (("whole", "全体"), ("leaf", "葉"), ("fruit", "実")):
                        value = row.get(f"{key}_model_label", "")
                        if value and value not in ("実なし（未診断）", "判定なし"):
                            summary.append(f"{label}：{value}")
                    if summary:
                        st.markdown('<div class="history-v3-diagnosis">' + '<br>'.join(escape(part) for part in summary) + '</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="history-v3-muted">診断結果の記録はありません</div>', unsafe_allow_html=True)
                    note = (row.get("observation_note", "") or "").strip()
                    if note:
                        short_note = note[:55] + ("…" if len(note) > 55 else "")
                        st.markdown(f'<div class="history-v3-note">メモ：{escape(short_note)}</div>', unsafe_allow_html=True)

                    if st.button("記録を見る", key=f"detail_{idx}", use_container_width=True):
                        st.session_state.selected_history_index = idx
                        st.session_state.selected_history_id = row.get("id")
                        st.session_state.force_scroll_top = True
                        st.session_state.page = "history_detail"
                        st.rerun()

    st.markdown('<div class="history-v3-foot">記録は新しい順に表示しています。</div>', unsafe_allow_html=True)


# =========================================================
# ⑥ 成長のきろく：詳細表示
# =========================================================
elif st.session_state.page == "history_detail":
    if st.session_state.get("force_scroll_top", False):
        force_scroll_top()
        st.session_state.force_scroll_top = False

    rows = load_history_rows()
    rows_sorted = list(reversed(rows))
    selected_idx = st.session_state.get("selected_history_index", 0)
    selected_id = st.session_state.get("selected_history_id")
    if selected_id:
        selected_idx = next((i for i, item in enumerate(rows_sorted) if item.get("id") == selected_id), len(rows_sorted))

    if not rows_sorted or not isinstance(selected_idx, int) or selected_idx < 0 or selected_idx >= len(rows_sorted):
        st.warning("表示できる記録がありません。")
        st.session_state.force_scroll_top = True
        st.session_state.page = "history_calendar"
        st.rerun()

    row = rows_sorted[selected_idx]
    day_text = format_history_date(row.get("created_at", ""))

    image_paths = [
        ("全体のようす", row.get("whole_image_path", "")),
        ("葉のようす", row.get("leaf_image_path", "")),
        ("実のようす", row.get("fruit_image_path", "")),
    ]
    main_label, main_image_path = next(
        ((label, p) for label, p in image_paths if p and (p.startswith("https://") or Path(p).exists())),
        (None, None),
    )
    # 記録詳細：重要なAI結果を先に表示し、旧形式の収穫予想は表示しない。
    days_raw = row.get("days_grown")
    try:
        days_num = int(days_raw)
        days_text = f"育て始めて {days_num} 日目" if days_num >= 1 else ""
    except (TypeError, ValueError):
        days_text = ""

    st.markdown(
        f'<div class="history-detail-head"><h2>{escape(day_text)} の記録</h2>'
        + (f'<span>{escape(days_text)}</span>' if days_text else "")
        + '</div>',
        unsafe_allow_html=True,
    )

    # 記録詳細画面は、画面最下部にホームへの移動を配置する。
    # ページ上部はアプリ名・マイページ・記録タイトルのみとする。
    # 詳細画面だけの調整：ヘッダー・日付・写真の間の空白を詰める。
    st.markdown("""
    <style>
    /* Streamlit の上部標準余白を抑える。見出し周りを詰めすぎない。 */
    [data-testid="stMainBlockContainer"]:has(.history-detail-head),
    .block-container:has(.history-detail-head) {
        padding-top: 1.0rem !important;
        padding-bottom: 1.4rem !important;
    }
    /* 日付見出しや結果の間に残る不要な空白を除く */
    [data-testid="stMainBlockContainer"]:has(.history-detail-head) [data-testid="stVerticalBlock"] {
        row-gap: .75rem !important;
    }
    [data-testid="stMainBlockContainer"]:has(.history-detail-head) [data-testid="stElementContainer"]:empty {
        margin: 0 !important;
    }
    [data-testid="stMainBlockContainer"]:has(.history-detail-head) hr { margin: .25rem 0 .45rem !important; }
    div[data-testid="stMainBlockContainer"]:has(.history-detail-head)
    > div > div[data-testid="stVerticalBlock"] {
        gap: .55rem !important;
    }
    div[data-testid="stMainBlockContainer"]:has(.history-detail-head)
    [data-testid="stDivider"] { margin: .15rem 0 !important; }
    div[data-testid="stMainBlockContainer"]:has(.history-detail-head)
    .history-detail-head { margin: 1px 0 12px !important; align-items:baseline; }
    div[data-testid="stMainBlockContainer"]:has(.history-detail-head)
    .history-detail-head h2 {font-size:25px !important; line-height:1.35 !important;}
    .st-key-detail_back_to_list button,
    .st-key-detail_bottom_home button {
       min-height: 36px !important;
       height: 36px !important;
       background:transparent !important;
       color:#64756b !important;
       border:1px solid #d6e1da !important;
       border-radius:9px !important;
       box-shadow:none !important;
       font-size:13px !important;
       font-weight:600 !important;
    }
    .st-key-detail_back_to_list button:hover,
    .st-key-detail_bottom_home button:hover {background:#f3f8f4 !important;color:#217447 !important;}
    div[data-testid="stMainBlockContainer"]:has(.history-detail-head)
    .history-detail-section {margin:0 0 7px !important;}
    div[data-testid="stMainBlockContainer"]:has(.history-detail-head)
    .history-detail-advice {margin-top:15px !important;}
    div[data-testid="stMainBlockContainer"]:has(.history-detail-head)
    .history-detail-note {margin-top:10px !important;}
    div[data-testid="stMainBlockContainer"]:has(.history-detail-head) [data-testid="stImage"] img {
        max-height: 240px !important;
        max-width: 100% !important;
        width: auto !important;
        object-fit: contain !important;
        border-radius: 10px;
    }
    div[data-testid="stMainBlockContainer"]:has(.history-detail-head) [data-testid="stImage"] {
        max-width: 230px;
    }
    @media (max-width: 640px) {
        div[data-testid="stMainBlockContainer"]:has(.history-detail-head) [data-testid="stImage"] img {
            max-height: 200px !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

    # 写真がある場合だけ表示。写真が保存されていない記録は空の写真枠を作らない。
    if main_image_path:
        photo_col, summary_col = st.columns([0.72, 2.28], gap="medium")
        with photo_col:
            st.markdown('<div class="history-detail-section">記録写真</div>', unsafe_allow_html=True)
            try:
                st.image(main_image_path, caption=main_label, width=220)
            except Exception:
                st.caption("写真を表示できませんでした。")
    else:
        summary_col = st.container()

    with summary_col:
        st.markdown('<div class="history-detail-section">AI診断結果</div>', unsafe_allow_html=True)
        result_parts = []
        for key, title in (("whole", "株全体"), ("leaf", "葉"), ("fruit", "実")):
            value = (row.get(f"{key}_model_label", "") or "").strip()
            if not value or value in ("実なし（未診断）", "判定なし", "未診断"):
                continue
            commentary = model_comment(key, value)
            result_parts.append(
                '<div class="history-detail-result-row">'
                f'<div class="history-detail-result-name">{escape(title)}</div>'
                f'<div class="history-detail-result-value">{escape(value)}</div>'
                f'<div class="history-detail-result-comment">{escape(commentary)}</div>'
                '</div>'
            )
        if result_parts:
            st.markdown('<div class="history-detail-result-list">' + ''.join(result_parts) + '</div>', unsafe_allow_html=True)
        else:
            st.caption("この記録にはAIの判定結果がありません。")

    advice = (row.get("model_advice", "") or "").strip()
    note = (row.get("observation_note", "") or "").strip()
    st.markdown(
        '<div class="history-detail-advice"><div class="history-detail-section">今日のアドバイス</div>'
        f'<p>{escape(advice) if advice else "この記録にはアドバイスがありません。"}</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="history-detail-note"><div class="history-detail-section">観察メモ</div>'
        f'<p>{escape(note) if note else "メモはありません。"}</p></div>',
        unsafe_allow_html=True,
    )

    # 削除は詳細表示中の記録IDを指定し、必ず本人に確認してから実行する。
    record_id_to_delete = row.get("id")
    if can_save_history() and record_id_to_delete:
        with st.expander("🗑️ この記録を削除する", expanded=False):
            st.warning("この記録と保存写真を削除します。削除した記録は元に戻せません。")
            with st.form(f"delete_history_form_{record_id_to_delete}"):
                delete_confirmed = st.checkbox("この記録を削除することを確認しました")
                delete_submitted = st.form_submit_button(
                    "削除を確定する", use_container_width=True
                )
            if delete_submitted:
                if not delete_confirmed:
                    st.warning("確認欄にチェックを入れてください。")
                elif not can_save_history():
                    st.error("ログインが必要です。もう一度ログインしてください。")
                else:
                    try:
                        history_cloud.delete_record(record_id_to_delete)
                    except Exception:
                        LOGGER.exception("Cloud history deletion failed")
                        st.error("削除できませんでした。通信状況を確認してもう一度お試しください。")
                    else:
                        st.session_state.pop("selected_history_id", None)
                        st.session_state.pop("selected_history_index", None)
                        st.session_state.history_delete_success = True
                        st.session_state.force_scroll_top = True
                        st.session_state.page = "history_calendar"
                        st.rerun()



# =========================================================
# AIモデル改善：3つの入口をわかりやすく配置
# =========================================================
elif st.session_state.page == "model_improve":
    if st.session_state.get("force_scroll_top", False):
        force_scroll_top()
        st.session_state.force_scroll_top = False

    # モデル改善の入口：2カードのみ。診断・登録機能は変更しない。
    st.markdown("""
    <style>
    .hub-title {font-size:clamp(25px,3vw,33px);font-weight:850;color:#173b2b;line-height:1.3;margin:6px 0 8px;}
    .hub-sub {font-size:14px;color:#62766b;line-height:1.7;margin:0 0 18px;}
    .hub-card-title {font-size:19px;font-weight:820;color:#1a4230;margin:0 0 9px;}
    .hub-card-sub {font-size:13px;line-height:1.65;color:#65756c;min-height:65px;margin-bottom:8px;}
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.hub-card-title) {
      border:1px solid #dce7df!important;border-radius:14px!important;background:#fff!important;
      box-shadow:none!important;padding:12px!important;
    }
    .st-key-hub_original button,.st-key-hub_register button {
      background:#2f8f47!important;color:#fff!important;border:1px solid #2f8f47!important;
      font-size:14px!important;border-radius:9px!important;min-height:44px!important;
      box-shadow:none!important;
    }
    .st-key-hub_original button:hover,.st-key-hub_register button:hover {
      background:#26793d!important;color:#fff!important;
    }
    .hub-tm-note {color:#65756c;font-size:13px;text-align:center;margin-top:15px;}
    .hub-tm-link {color:#236d45!important;text-decoration:underline;text-underline-offset:3px;}
    @media(max-width:650px){.hub-title{font-size:26px}.hub-card-sub{min-height:0}}
    </style>
    <div class="hub-title">AIモデルを改善する</div>
    <div class="hub-sub">AIモデルの学習・改善と登録ができます。</div>
    """, unsafe_allow_html=True)

    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(border=True):
            st.markdown(
                '<div class="hub-card-title">元のモデルを改良する</div>'
                '<div class="hub-card-sub">株全体・葉・実のモデルを確認し、学習画像を追加して改善します。</div>',
                unsafe_allow_html=True,
            )
            if st.button("元のモデルを見る", key="hub_original", use_container_width=True):
                st.session_state.page = "training_gallery"
                st.session_state.force_scroll_top = True
                st.rerun()
    with right:
        with st.container(border=True):
            st.markdown(
                '<div class="hub-card-title">モデルを登録・管理する</div>'
                '<div class="hub-card-sub">Teachable Machineで作成したモデルを登録し、一覧から確認します。</div>',
                unsafe_allow_html=True,
            )
            if st.button("モデルを登録・一覧を見る", key="hub_register", use_container_width=True):
                st.session_state.page = "model_registry"
                st.session_state.force_scroll_top = True
                st.rerun()

    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
    if st.button("登録したモデルで診断する", key="hub_registered_diagnosis", use_container_width=True):
        st.session_state.page = "registered_model_diagnosis"
        st.session_state.force_scroll_top = True
        st.rerun()

    st.markdown(
        '<div class="hub-tm-note">新しくモデルを作成する場合：'
        '<a class="hub-tm-link" href="https://teachablemachine.withgoogle.com/train/image" '
        'target="_blank" rel="noopener noreferrer">Teachable Machineを開く ↗</a></div>',
        unsafe_allow_html=True,
    )

elif st.session_state.page == "registered_model_diagnosis":
    registered_model_diagnosis.show()

elif st.session_state.page == "model_choice":
    if st.session_state.get("force_scroll_top", False):
        force_scroll_top()
        st.session_state.force_scroll_top = False
    st.markdown("## AIモデルを選んで診断")
    st.write("現在は標準モデル（全体・葉・実）で診断できます。")
    with st.container(border=True):
        st.markdown("**標準モデル**")
        st.caption("現在のAI生育診断アプリで使用しているモデルです。")
        if st.button("標準モデルで診断する", type="primary", use_container_width=True, key="use_standard_model"):
            st.session_state.page = "diagnosis_upload"
            st.session_state.force_scroll_top = True
            st.rerun()
    st.info("登録されたモデルへの切り替えは、モデルの読み込み・分類名との対応付けを実装後に利用できます。")

# =========================================================
# ⑦ AIモデル登録・一覧（既存診断機能とは独立）
# =========================================================
elif st.session_state.page == "model_registry":
    model_registry.show()

elif st.session_state.page == "training_gallery":
    if st.session_state.get("force_scroll_top", False):
        force_scroll_top()
        st.session_state.force_scroll_top = False

    # 元のAIモデルを生徒が各自のコピーとして改良するための画面。
    # `.tm` はTeachable Machineの学習画像・分類情報を含むプロジェクトファイル。
    # 診断に使う models/ 以下の学習済みモデルには一切触れない。
    st.markdown("""
    <style>
      div[data-testid="stMainBlockContainer"]:has(.tm-gallery-page) {
        max-width: 1050px !important;
        padding-top: .35rem !important;
        padding-bottom: 1.25rem !important;
      }
      .tm-gallery-page {height:0;}
      .tm-gallery-title {font-size:clamp(25px,3vw,32px);font-weight:850;
        color:#173b2b;line-height:1.3;margin:0 0 7px;}
      .tm-gallery-intro {font-size:14px;color:#617469;line-height:1.65;margin:0 0 15px;}
      .tm-gallery-card-title {font-size:19px;font-weight:850;color:#19412e;margin:0 0 7px;}
      .tm-gallery-card-desc {font-size:13px;color:#64776d;line-height:1.65;min-height:43px;}
      div[data-testid="stVerticalBlockBorderWrapper"]:has(.tm-gallery-card-title) {
        background:#fff !important;border:1px solid #dce7df !important;
        border-radius:13px !important;box-shadow:none !important;padding:9px 8px 7px !important;
      }
      [class*="st-key-tm_project_download_"] button {
        min-height:44px !important;border-radius:9px !important;
        background:#23874b !important;border:1px solid #23874b !important;
        color:white !important;box-shadow:none !important;
        font-size:14px !important;font-weight:750 !important;
      }
      [class*="st-key-tm_project_open_"] a {
        min-height:44px !important;border-radius:9px !important;
        background:#fff !important;border:1px solid #a7cbb3 !important;
        color:#246d45 !important;box-shadow:none !important;
        font-size:14px !important;font-weight:750 !important;
      }
      .tm-gallery-steps {font-size:14px;color:#405a4a;line-height:1.9;
        background:#f8fbf9;border:1px solid #e1eae3;border-radius:11px;
        padding:13px 17px;margin:6px 0 0;}
      @media(max-width:640px) {
        .tm-gallery-card-desc {min-height:0;}
        .tm-gallery-title {font-size:25px;}
      }
    </style>
    <div class="tm-gallery-page"></div>
    <div class="tm-gallery-title">元のAIモデル</div>
    <div class="tm-gallery-intro">改善したいモデルを選んでください。</div>
    """, unsafe_allow_html=True)

    original_models = (
        ("whole", "株全体モデル", "株全体の生育状態を判定", "whole.tm"),
        ("leaf", "葉モデル", "葉の色や状態を判定", "leaf.tm"),
        ("fruit", "実モデル", "実の成長段階を判定", "fruit.tm"),
    )
    project_dir = APP_DIR / "tm_projects"
    cols = st.columns(3, gap="medium")
    for col, (model_key, model_title, desc, filename) in zip(cols, original_models):
        project_path = project_dir / filename
        with col:
            with st.container(border=True):
                st.markdown(
                    f'<div class="tm-gallery-card-title">{escape(model_title)}</div>'
                    f'<div class="tm-gallery-card-desc">{escape(desc)}</div>',
                    unsafe_allow_html=True,
                )
                if project_path.is_file():
                    st.download_button(
                        "プロジェクトを保存",
                        data=project_path.read_bytes(),
                        file_name=filename,
                        mime="application/octet-stream",
                        key=f"tm_project_download_{model_key}",
                        use_container_width=True,
                    )
                else:
                    st.warning("プロジェクトファイルが見つかりません。")
                    st.caption(f"tm_projects/{filename} を配置してください")
                st.link_button(
                    "Teachable Machineを開く ↗",
                    "https://teachablemachine.withgoogle.com/train/image",
                    use_container_width=True,
                )


# =========================================================
# ⑧ 過去の写真を既存モデルで一括仮分類（必ず人が確認）
# =========================================================
elif st.session_state.page == "bulk_classifier":
    bulk_classifier.show(load_tm_model, load_tm_labels)
# 全ページ共通の最下部ナビゲーション。各ページの内容の後に表示。
bottom_back_button()