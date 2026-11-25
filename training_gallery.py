"""Original Teachable Machine project downloads (standalone Streamlit page).

Place this module next to app.py, and put the provided .tm archives in
``tm_projects/``. app.py already calls training_gallery.show().
"""
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = BASE_DIR / "tm_projects"
TM_NEW_IMAGE_PROJECT_URL = "https://teachablemachine.withgoogle.com/train/image"

MODELS = [
    ("株全体モデル", "株の生育状態を学習するための元プロジェクトです。", "whole.tm"),
    ("葉モデル", "葉の状態を学習するための元プロジェクトです。", "leaf.tm"),
    ("実モデル", "実の成長状態を学習するための元プロジェクトです。", "fruit.tm"),
]


def show():
    st.markdown("""
    <style>
      /* This page only: avoid changing the diagnosis and other screens. */
      [data-testid="stMainBlockContainer"]:has(.tm-original-page) {
          padding-top: .35rem !important;
          padding-bottom: 1.5rem !important;
      }
      .tm-original-page {margin: 0 0 12px;}
      .tm-original-title {font-size:clamp(25px, 3vw, 32px);font-weight:850;
          line-height:1.3;color:#173e2c;margin:0 0 6px;}
      .tm-original-lead {font-size:14px;color:#607369;line-height:1.65;margin:0 0 10px;}
      .tm-card-title {font-size:18px;font-weight:800;color:#173e2c;margin:0 0 5px;}
      .tm-card-desc {font-size:13px;color:#607369;line-height:1.55;min-height:40px;}
      [data-testid="stVerticalBlockBorderWrapper"]:has(.tm-card-title) {
          border:1px solid #dfe9e1 !important;
          border-radius:13px !important;
          background:#fff !important;
          box-shadow:none !important;
      }
      [class*="st-key-tm_download_"] button {
          background:#228a4a !important;color:white !important;
          border:1px solid #228a4a !important;
          box-shadow:none !important;border-radius:9px !important;
          font-size:14px !important;min-height:42px !important;
      }
      [class*="st-key-tm_open_"] a {
          background:white !important;color:#207344 !important;
          border:1px solid #a4cbb0 !important;
          box-shadow:none !important;border-radius:9px !important;
          font-size:14px !important;min-height:42px !important;
      }
      .st-key-tm_back button {
          background:transparent !important;color:#617368 !important;
          border:1px solid #dce6df !important;box-shadow:none !important;
          font-size:13px !important;min-height:38px !important;
          border-radius:9px !important;
      }
      @media(max-width:760px){.tm-card-desc{min-height:0;}}
    </style>
    <div class="tm-original-page">
      <div class="tm-original-title">元のAIモデル</div>
      <div class="tm-original-lead">改良したいモデルのプロジェクトをダウンロードしてください。</div>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(3, gap="small")
    for idx, ((name, desc, filename), col) in enumerate(zip(MODELS, cols)):
        with col:
            with st.container(border=True):
                st.markdown(f'<div class="tm-card-title">{name}</div><div class="tm-card-desc">{desc}</div>', unsafe_allow_html=True)
                path = PROJECTS_DIR / filename
                if path.is_file():
                    st.download_button(
                        "プロジェクトをダウンロード",
                        data=path.read_bytes(),
                        file_name=filename,
                        mime="application/octet-stream",
                        key=f"tm_download_{idx}",
                        use_container_width=True,
                    )
                else:
                    st.warning("プロジェクトファイルがありません。管理者にお問い合わせください。")
                st.link_button(
                    "Teachable Machineを開く",
                    TM_NEW_IMAGE_PROJECT_URL,
                    use_container_width=True,
                )

    st.info("Teachable Machineでは「プロジェクトを開く」→「ファイルから」を選び、ダウンロードした .tm ファイルを読み込んでください。画像を追加して再学習できます。")
    st.caption("※ ここで配布するのは再編集用のプロジェクトです。現在のAI診断で使っている標準モデルは変更されません。")
    if st.button("← 1ページ前に戻る", key="tm_back"):
        st.session_state.page = "model_improve"
        st.session_state.force_scroll_top = True
        st.rerun()
