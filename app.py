import os
import io
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
    st.session_state.page = "select_user"

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
    st.session_state.page = "select_user"
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

# 共通ヘッダー
st.markdown(
    """
    <div class="lab-header">
        <div class="lab-title"><span class="leaf">🌱</span><span>植物診断ラボ</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

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
    """Server history must be explicitly enabled on a trusted deployment."""
    return ENABLE_SERVER_HISTORY and not is_guest_user()


def validated_upload(uploaded_file) -> Image.Image:
    """Reject oversized, malformed and decompression-bomb images."""
    if uploaded_file is None:
        raise ValueError("写真が選択されていません。")
    data = uploaded_file.getvalue()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("写真は10MB以下にしてください。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ("JPEG", "PNG", "HEIF", "HEIC"):
                    raise ValueError("JPEG・PNG・HEIC形式の写真を選んでください。")
                source.verify()
            with Image.open(io.BytesIO(data)) as source:
                return ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("写真を読み込めませんでした。別のJPEG・PNG・HEIC写真をお試しください。") from exc


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
    if not can_save_history():
        return None

    history_path = get_history_path()
    if not history_path.exists():
        return None

    with history_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return None
    return rows[-1]


def load_history_rows() -> list[dict]:
    if not can_save_history():
        return []

    history_path = get_history_path()
    if not history_path.exists():
        return []

    with history_path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


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
# ① 初回設定画面
# =========================================================
if st.session_state.page == "select_user":
    if st.session_state.get("force_scroll_top", False):
        force_scroll_top()
        st.session_state.force_scroll_top = False

    st.markdown('<div class="select-page-wrap">', unsafe_allow_html=True)

    st.markdown('<div class="select-title">🍅 トマトの状態をAIで確認</div>', unsafe_allow_html=True)
    st.markdown('<div class="select-help">登録不要・無料。写真を1枚選んで診断できます。</div>', unsafe_allow_html=True)
    st.info("このアプリはトマト専用です。結果は参考情報であり、病気の確定診断ではありません。")
    st.caption("写真・入力内容・診断結果はサーバーに記録しません。")
    planting_date_known = st.checkbox("植え付け日が分かる", value=st.session_state.planting_date_known)
    planting_date = date.today()
    if planting_date_known:
        planting_date = st.date_input("植え付け日", value=st.session_state.planting_date, max_value=date.today())

    st.write("")

    if planting_date > date.today():
        st.warning("植え付け日は今日以前の日付を選んでください。")

    if st.button("📷 写真診断をはじめる ›", use_container_width=True, disabled=planting_date > date.today()):
        st.session_state.grade = ""
        st.session_state.class_name = ""
        st.session_state.student_number = ""
        st.session_state.student_name = ""
        st.session_state.plant_type = "トマト"
        st.session_state.planting_date = planting_date
        st.session_state.planting_date_known = planting_date_known
        st.session_state.user_id = "guest"
        st.session_state.force_scroll_top = True
        st.session_state.page = "diagnosis_upload"
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


# =========================================================
# ② ホーム画面
# =========================================================
elif st.session_state.page == "home":

    if st.session_state.get("force_scroll_top", False):
        force_scroll_top()
        st.session_state.force_scroll_top = False

    last_history = load_last_history()
    last_date_text = "保存しない設定" if not can_save_history() else "まだありません"

    if not ENABLE_SERVER_HISTORY:
        st.info("プライバシー保護のため、この公開向け設定では写真・診断履歴をサーバーに保存しません。")
    else:
        st.warning("この保存機能にはログイン認証がありません。同じ学年・組・植物を選んだ利用者の記録が共有されます。信頼できる閉じた環境でのみお使いください。")

    if last_history is not None:
        last_date_text = last_history.get("created_at", "")
        try:
            last_date_text = datetime.fromisoformat(last_date_text).strftime("%Y/%m/%d")
        except Exception:
            last_date_text = last_date_text[:10]

    st.markdown(
        f"""
        <div class="home-card-head">
            <div>
                <div class="home-main-title">診断をはじめる</div>
                <div class="home-sub">{st.session_state.plant_type}のようすを記録して診断します</div>
            </div>
            <div class="last-pill">前回診断：{last_date_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="today-card" style="margin-bottom:18px;">
            <div class="today-title">🌱 初回設定</div>
            <div class="today-advice" style="margin-top:0;">
                <div class="today-advice-title">{st.session_state.grade}{st.session_state.class_name}</div>
                <div class="today-advice-text">育てている植物：{st.session_state.plant_type}<br>植え付け日：{st.session_state.planting_date.strftime('%Y/%m/%d')}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_diagnosis, col_history = st.columns(2, gap="large")

    with col_diagnosis:
        if st.button("📷 今日の診断をする", use_container_width=True):
            st.session_state.force_scroll_top = True
            st.session_state.page = "diagnosis_upload"
            st.rerun()

    with col_history:
        if st.button("🌱 成長の記録を見る", use_container_width=True, disabled=not can_save_history()):
            st.session_state.force_scroll_top = True
            st.session_state.page = "history_calendar"
            st.rerun()

    st.markdown(
        '<div class="student-change-link-wrap"><a class="student-change-link" href="?change_student=1">初回設定を変更する</a></div>',
        unsafe_allow_html=True,
    )


# =========================================================
# ③ 写真アップロード画面
# =========================================================
elif st.session_state.page == "diagnosis_upload":
    if st.session_state.get("force_scroll_top", False):
        force_scroll_top()
        st.session_state.force_scroll_top = False

    plant_type = st.session_state.plant_type
    today_text = date.today().strftime("%Y/%m/%d")

    st.markdown(
        f"""
        <div class="observe-head simple-observe-head">
            <div>
                <div class="observe-title-main"> 今日の観察と写真</div>
            </div>
            <div class="observe-meta">
                📅 記録日：{today_text}<br>
                {st.session_state.grade}{st.session_state.class_name}　｜　{st.session_state.plant_type}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="observe-divider"></div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="observe-section-title">
            <span class="observe-step-inline">1</span>
            <span> 水やりをしましたか？</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    watered_today = st.radio(
        "水やりをしましたか？",
        ["した", "していない"],
        horizontal=True,
        label_visibility="collapsed",
    )

    st.markdown('<div class="observe-divider"></div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="observe-section-title">
            <span class="observe-step-inline">2</span>
            <span> 今日行った作業</span>
        </div>
        <div class="observe-help-line">行った作業をすべて選んでください（複数選択可）</div>
        """,
        unsafe_allow_html=True,
    )

    work_col1, work_col2 = st.columns(2, gap="large")
    with work_col1:
        work_topping = st.checkbox(" 摘心", key="work_topping")
        work_fertilizer = st.checkbox(" 追肥（肥料）", key="work_fertilizer")
        work_pollination = st.checkbox(" 受粉", key="work_pollination")
        work_other = st.checkbox(" その他", key="work_other")
    with work_col2:
        work_side_shoot = st.checkbox(" わき芽取り", key="work_side_shoot")
        work_support = st.checkbox(" 支柱立て", key="work_support")
        work_harvest = st.checkbox(" 収穫", key="work_harvest")

    other_work_text = ""
    if work_other:
        other_work_text = st.text_input(
            "その他の作業",
            placeholder="例：葉かき、土寄せ、間引き など",
        )

    work_items = []
    if work_topping:
        work_items.append("摘心")
    if work_side_shoot:
        work_items.append("わき芽取り")
    if work_fertilizer:
        work_items.append("追肥")
    if work_support:
        work_items.append("支柱立て")
    if work_pollination:
        work_items.append("受粉")
    if work_harvest:
        work_items.append("収穫")
    if work_other and other_work_text.strip():
        work_items.append(other_work_text.strip())
    elif work_other:
        work_items.append("その他")

    st.markdown('<div class="observe-divider"></div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="observe-section-title">
            <span class="observe-step-inline">3</span>
            <span> 全体写真をアップロードしよう</span>
        </div>
        <div class="observe-help-line">植物全体が入る写真を1枚アップロードしてください</div>
        """,
        unsafe_allow_html=True,
    )

    fruit_visible = st.radio(
        "今回の写真にトマトの実が写っていますか？",
        ["写っていない", "写っている"],
        horizontal=True,
        help="実が写っていないときは収穫の進み具合を判定しません。",
    ) == "写っている"

    # 実の初確認日が分かる場合だけ、経過日数を収穫進行度に加える。
    known_fruit_date = st.checkbox(
        "実を初めて確認した日が分かる", key="known_first_fruit_date", disabled=not fruit_visible
    ) if fruit_visible else False
    first_fruit_date = None
    if known_fruit_date:
        first_fruit_date = st.date_input(
            "実を初めて確認した日",
            value=date.today(),
            min_value=(st.session_state.planting_date if st.session_state.planting_date_known else None),
            max_value=date.today(),
            key="first_fruit_date_value",
        )
    st.caption("過去の観察記録（実の確認から収穫まで約43日）を目安に使用します。実の確認日が不明なら入力不要です。")

    photo_col, upload_col = st.columns(2, gap="large")

    with photo_col:
        show_sample_image(
            "sample_whole_image.png",
            "全体写真の例",
        )

    with upload_col:
        whole_file = st.file_uploader(
            "全体写真をアップロード",
            type=SUPPORTED_UPLOAD_TYPES,
            key="diagnosis_whole",
            label_visibility="collapsed",
        )


    st.divider()

    missing_models = [key for key in MODEL_NAMES if not (MODEL_DIR / key / "keras_model.h5").is_file() or not (MODEL_DIR / key / "labels.txt").is_file()]
    if missing_models:
        st.error("AI診断用の学習済みモデルが未配置です。管理者にお問い合わせください。写真や記録は送信されません。")
    st.caption("対応形式：JPEG・PNG・HEIC／最大10MB。AIの判定は参考情報であり、病気や収穫時期を保証するものではありません。")

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
                st.session_state.previous_record = load_last_history()
                st.session_state.diagnosis_record = record
                if can_save_history():
                    try:
                        save_diagnosis_history(record, whole_file, None, None)
                    except (OSError, ValueError):
                        LOGGER.exception("Could not save diagnosis history")
                        st.warning("診断はできましたが、履歴を保存できませんでした。")
                st.session_state.force_scroll_top = True
                st.session_state.page = "diagnosis_result"
                st.rerun()

    if not can_save_history():
        back_link("設定画面に戻る", "select_user")
    else:
        back_link("前のページに戻る", "home")


# =========================================================
# ④ 結果画面
# =========================================================
elif st.session_state.page == "diagnosis_result":
    record = st.session_state.diagnosis_record

    # 結果画面を開いたら一番上に戻す
    force_scroll_top()
    st.session_state.force_scroll_top = False

    if record is None:
        st.warning("まだ診断記録がありません。")
        back_link("前のページに戻る", "home")
        st.stop()

    st.markdown('<div class="result-page-title">診断結果 <span>🌿</span></div>', unsafe_allow_html=True)

    days_col, info_col = st.columns([1, 1.75], gap="large")
    days_text = f"{record['days_grown']}日目" if isinstance(record.get("days_grown"), int) else "不明"
    with days_col:
        st.markdown(
            f'<div class="result-summary-card"><div class="days-card-inner">'
            f'<div class="days-icon">🌱</div><div><div class="days-small">育て始めて</div>'
            f'<div class="days-big">{days_text}</div></div></div></div>',
            unsafe_allow_html=True,
        )
    with info_col:
        fruit_label = record.get("fruit_model_label", "")
        harvest_stage, harvest_note = harvest_guidance(fruit_label)
        percent = recorded_harvest_percent(record)
        percent_width = percent if percent is not None else 0
        st.markdown(
            '<div class="result-summary-card harvest-card"><div class="harvest-card-inner">'
            '<div class="harvest-head"><div class="harvest-title">🍅 収穫の進み具合（目安）</div>'
            f'<div class="harvest-percent">{recorded_harvest_text(record)}</div></div>'
            '<div class="harvest-bar">'
            f'<div class="harvest-fill" style="width:{percent_width}%;"></div></div>'
            f'<div class="harvest-note">{escape(harvest_stage)}：{escape(harvest_note)}<br>{escape(record.get("harvest_basis", ""))}</div>'
            '</div></div>',
            unsafe_allow_html=True,
        )

    result_rows = []
    for key, icon in [("whole", "🌱"), ("leaf", "🍃"), ("fruit", "🍅")]:
        model_label = record.get(f"{key}_model_label", "")
        if model_label:
            status = escape(model_label)
            comment = escape(model_comment(key, model_label))
        else:
            status = "記録なし"
            comment = "この項目の診断結果はありません。"
        result_rows.append(
            '<div class="today-row">'
            f'<div class="today-icon">{icon}</div>'
            f'<div class="today-label">{MODEL_NAMES[key]}</div>'
            f'<div class="today-status neutral">{status}</div>'
            f'<div class="today-comment">{comment}</div>'
            '</div>'
        )
    advice = escape(record.get("model_advice", ""))
    today_html = (
        '<div class="today-card"><div class="today-title">🌿 今日のようす</div>'
        '<div class="today-table">' + "".join(result_rows) + '</div>'
        '<div class="today-advice">'
        '<div class="today-advice-title">💡 アドバイス</div>'
        f'<div class="today-advice-text">{advice}</div></div></div>'
    )
    st.markdown(today_html, unsafe_allow_html=True)

    st.markdown('<div class="result-action-row">', unsafe_allow_html=True)

    if not can_save_history():
        if st.button("↻ もう一度診断する", use_container_width=True):
            st.session_state.page = "diagnosis_upload"
            st.rerun()
        st.caption("プライバシー保護のため、診断結果・写真・入力内容は保存されません。画面を閉じる前に結果を確認してください。")
    else:
        col_again, col_history = st.columns(2, gap="large")

        with col_again:
            if st.button("↻ もう一度診断する", use_container_width=True):
                st.session_state.page = "diagnosis_upload"
                st.rerun()

        with col_history:
            if st.button("🌱 成長の記録", use_container_width=True):
                st.session_state.force_scroll_top = True
                st.session_state.page = "history_calendar"
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


    

# =========================================================
# ⑤ 成長のきろく：アルバム表示
# =========================================================
elif st.session_state.page == "history_calendar":
    st.markdown('<div class="growth-page-title">🌱 成長のきろく</div>', unsafe_allow_html=True)
    st.markdown('<div class="growth-subtitle">写真をタップすると、くわしい記録が見られます</div>', unsafe_allow_html=True)

    rows = load_history_rows()

    if not rows:
        st.warning("まだ成長のきろくがありません。")
        back_link("前のページに戻る", "home")
        st.stop()

    rows_sorted = list(reversed(rows))

    def first_image_path(row: dict) -> str:
        for key in ["whole_image_path", "leaf_image_path", "fruit_image_path"]:
            path_text = row.get(key, "")
            if path_text and Path(path_text).exists():
                return path_text
        return ""

    for row_start in range(0, len(rows_sorted), 3):
        cols = st.columns(3, gap="large")
        for offset, col in enumerate(cols):
            idx = row_start + offset
            if idx >= len(rows_sorted):
                continue

            row = rows_sorted[idx]
            img_path = first_image_path(row)
            day_text = format_history_date(row.get("created_at", ""))
            with col:
                st.markdown('<div class="growth-card">', unsafe_allow_html=True)

                if img_path:
                    st.image(img_path, width="stretch")
                else:
                    st.markdown('<div class="growth-image-box">🌱</div>', unsafe_allow_html=True)

                stage, _ = harvest_guidance(row.get("fruit_model_label", ""))
                st.markdown(
                    f'<div class="growth-date">{day_text}</div>'
                    f'<div class="growth-mini">育て始めて {escape(str(row.get("days_grown", "")))}日目　収穫の目安：{recorded_harvest_text(row)}</div>',
                    unsafe_allow_html=True,
                )

                if st.button("くわしく見る", key=f"detail_{idx}", use_container_width=True):
                    st.session_state.selected_history_index = idx
                    st.session_state.force_scroll_top = True
                    st.session_state.page = "history_detail"
                    st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="history-action-row">', unsafe_allow_html=True)
    col_back, col_home = st.columns(2, gap="large")

    with col_back:
        if st.button("← 診断画面に戻る", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()

    with col_home:
        if st.button("🏠 ホームに戻る", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


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

    if not rows_sorted or selected_idx >= len(rows_sorted):
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
        ((label, p) for label, p in image_paths if p and Path(p).exists()),
        (None, None),
    )
    st.markdown(f'<div class="detail-title">📅 {day_text} の記録</div>', unsafe_allow_html=True)
    col_photo, col_info = st.columns([0.75, 1.45], gap="large")
    with col_photo:
        st.markdown('<div class="detail-photo-title">📷 写真</div>', unsafe_allow_html=True)
        if main_image_path:
            st.image(main_image_path, caption=main_label, width=340)
        else:
            st.info("写真は保存されていません。")
        st.markdown('<div class="detail-photo-note">成長を比べるための記録写真です</div>', unsafe_allow_html=True)
    with col_info:
        fruit_label = row.get("fruit_model_label", "")
        stage, harvest_note = harvest_guidance(fruit_label)
        pct = recorded_harvest_percent(row)
        pct_width = pct if pct is not None else 0
        st.markdown(
            f'<div class="detail-mini-card"><div class="detail-mini-label">育て始めて</div>'
            f'<div class="detail-mini-value">{escape(str(row.get("days_grown", "")))}日目</div></div>'
            '<div class="detail-progress-card">'
            '<div class="detail-progress-title">🍅 収穫の進み具合（目安）</div>'
            f'<div class="detail-progress-percent">{recorded_harvest_text(row)}</div>'
            '<div class="harvest-bar">'
            f'<div class="harvest-fill" style="width:{pct_width}%;"></div></div>'
            f'<div class="detail-progress-comment">{escape(stage)}：{escape(harvest_note)}<br>{escape(row.get("harvest_basis", ""))}</div></div>',
            unsafe_allow_html=True,
        )
        detail_rows = []
        for key, icon in [("whole", "🌱"), ("leaf", "🍃"), ("fruit", "🍅")]:
            label = row.get(f"{key}_model_label", "")
            status = escape(label) if label else "記録なし（旧形式）"
            detail_rows.append(
                '<div class="detail-status-item">'
                f'<div class="detail-status-icon">{icon}</div>'
                f'<div class="detail-status-label">{MODEL_NAMES[key]}</div>'
                f'<div class="detail-status-pill neutral">{status}</div>'
                f'<div class="detail-status-comment">{escape(model_comment(key, label))}</div>'
                '</div>'
            )
        st.markdown(
            '<div class="detail-status-title">🌿 AI診断結果</div>'
            '<div class="detail-status-list">' + ''.join(detail_rows) + '</div>'
            '<div class="detail-advice-box"><div class="detail-advice-title">💡 アドバイス</div>'
            f'<div class="detail-advice-text">{escape(row.get("model_advice", "") or "この記録にはアドバイスが保存されていません。")}</div></div>'
            '<div class="detail-record-box">'
            f'<b>📝 観察メモ</b><br>水やり：{escape(row.get("watered_today", "") or "記録なし")}<br>'
            f'今日の作業：{escape(row.get("work_items", "") or "なし")}</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="history-action-row">', unsafe_allow_html=True)
    col_back, col_again, col_home = st.columns(3, gap="large")

    with col_back:
        if st.button("← きろく一覧へ", use_container_width=True):
            st.session_state.force_scroll_top = True
            st.session_state.page = "history_calendar"
            st.rerun()

    with col_again:
        if st.button("📷 もう一度診断する", use_container_width=True):
            st.session_state.force_scroll_top = True
            st.session_state.page = "diagnosis_upload"
            st.rerun()

    with col_home:
        if st.button("🏠 ホームに戻る", use_container_width=True):
            st.session_state.force_scroll_top = True
            st.session_state.page = "home"
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
