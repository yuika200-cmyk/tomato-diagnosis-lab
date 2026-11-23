"""画面表示専用の認証UI。既存 history_cloud.py の認証処理を再利用する。"""
import httpx
import streamlit as st
import history_cloud as auth


def _go(view):
    st.session_state.login_view = view
    st.rerun()


def show():
    # OAuth/パスワード復旧は既存コードのPKCE処理に委譲する。
    if not auth.configured():
        st.info('現在、ログイン機能は準備中です。診断はログインなしで利用できます。')
        return
    auth._google_callback()
    auth._recovery_callback()

    st.markdown('''<style>
    div[data-testid="stMainBlockContainer"]:has(.login-view-marker) { max-width: 800px !important; padding-top:.45rem !important; }
    .login-view-marker {height:0;}
    .login-heading{text-align:center;font-size:28px;font-weight:850;color:#174b32;margin:5px 0 6px;}
    .login-explain{text-align:center;color:#64746a;font-size:14px;margin-bottom:12px;}
    .login-foot{text-align:center;color:#728079;font-size:13px;margin:12px 0;}
    div[data-testid="stMainBlockContainer"]:has(.login-view-marker) div[data-testid="stForm"] {border:0!important;padding:0!important;}
    </style><div class="login-view-marker"></div>''', unsafe_allow_html=True)
    _, center, _ = st.columns([1, 2.5, 1])
    with center:
        if st.session_state.get('history_password_recovery'):
            st.markdown('<div class="login-heading">新しいパスワードの設定</div>',unsafe_allow_html=True)
            auth._recovery_form()
            return
        if st.session_state.pop('history_password_reset_success', False):
            st.success('パスワードを変更しました。新しいパスワードでログインしてください。')
        current = auth.user()
        if current:
            st.markdown('<div class="login-heading">マイページ</div>',unsafe_allow_html=True)
            st.success('ログイン中')
            st.caption('保存した診断結果や観察メモを確認できます。')
            if st.button('成長の記録を見る',use_container_width=True,key='account_history'):
                st.session_state.page='history_calendar'; st.rerun()
            if st.button('ログアウト',use_container_width=True,key='account_logout'):
                try:
                    auth.client().auth.sign_out()
                    st.session_state.pop('history_google_url',None)
                    st.session_state.page='home'
                    st.rerun()
                except Exception as exc:
                    auth._show_auth_error(exc)
            return
        view=st.session_state.get('login_view','login')
        headings={'login':'ログイン','register':'新規登録','reset':'パスワードの再設定'}
        subtexts={'login':'ログインすると、診断結果や観察メモを保存できます。',
                  'register':'アカウントを作成して、成長の記録を残しましょう。',
                  'reset':'登録したメールアドレスを入力してください。'}
        st.markdown(f'<div class="login-heading">{headings.get(view,"ログイン")}</div>',unsafe_allow_html=True)
        st.markdown(f'<div class="login-explain">{subtexts.get(view,subtexts["login"])}</div>',unsafe_allow_html=True)
        if view!='reset':
            if st.button('Googleでログイン・登録',use_container_width=True,key='auth_google_start'):
                try:
                    st.session_state.history_google_url=auth._make_google_link()
                except Exception as exc:
                    auth._show_auth_error(exc)
            if st.session_state.get('history_google_url'):
                st.link_button('Googleの認証画面へ進む',st.session_state.history_google_url,use_container_width=True)
            st.caption('またはメールアドレスで')
        if view=='login':
            with st.form('auth_login_form'):
                email=st.text_input('メールアドレス',placeholder='example@email.com',key='auth_login_email')
                password=st.text_input('パスワード',type='password',key='auth_login_password')
                submitted=st.form_submit_button('ログインする',use_container_width=True,type='primary')
            if submitted:
                if not email.strip() or not password:
                    st.warning('メールアドレスとパスワードを入力してください。')
                else:
                    try:
                        response=auth.client().auth.sign_in_with_password({'email':email.strip(),'password':password})
                        if not response.session: st.warning('ログインセッションを取得できませんでした。')
                        else:
                            st.session_state.page='home'; st.session_state.pop('history_signup_notice',None); st.rerun()
                    except Exception as exc: auth._show_auth_error(exc)
            a,b=st.columns(2)
            with a:
                if st.button('新規登録はこちら',use_container_width=True,key='auth_go_register'): _go('register')
            with b:
                if st.button('パスワードを忘れた方',use_container_width=True,key='auth_go_reset'): _go('reset')
        elif view=='register':
            if st.session_state.get('history_signup_notice'):
                st.success('登録手続きを受け付けました。初めて登録する方は確認メールをご確認ください。')
                st.info('すでに登録済みの場合は、新規登録せずログインしてください。')
            with st.form('auth_register_form'):
                email=st.text_input('メールアドレス',placeholder='example@email.com',key='auth_register_email')
                password=st.text_input('パスワード（8文字以上）',type='password',key='auth_register_password')
                again=st.text_input('パスワード（確認）',type='password',key='auth_register_password_again')
                submitted=st.form_submit_button('アカウントを作成',use_container_width=True,type='primary')
            if submitted:
                if not email.strip() or '@' not in email: st.warning('メールアドレスを確認してください。')
                elif len(password)<8: st.warning('パスワードは8文字以上で入力してください。')
                elif password != again: st.warning('確認用パスワードが一致しません。')
                else:
                    try:
                        result=auth.client().auth.sign_up({'email':email.strip(),'password':password})
                        if result.session: st.session_state.page='home'
                        else: st.session_state.history_signup_notice=True
                        st.rerun()
                    except Exception as exc: auth._show_signup_error(exc)
            if st.button('ログイン画面に戻る',use_container_width=True,key='auth_register_back'): _go('login')
        else:
            with st.form('auth_reset_form'):
                email=st.text_input('登録したメールアドレス',placeholder='example@email.com',key='auth_recovery_email')
                submitted=st.form_submit_button('再設定メールを送信',use_container_width=True,type='primary')
            if submitted:
                if not email.strip() or '@' not in email: st.warning('メールアドレスを確認してください。')
                else:
                    try:
                        auth._send_recovery_email(email.strip())
                        st.info('登録済みのアドレスなら再設定メールが届きます。メールのリンクをご確認ください。')
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code==429: st.warning('送信回数の上限に達しました。時間を空けてお試しください。')
                        else: st.error('再設定メールを送信できませんでした。')
                    except Exception as exc: auth._show_auth_error(exc)
            if st.button('ログイン画面に戻る',use_container_width=True,key='auth_reset_back'): _go('login')
        st.markdown('<div class="login-foot">診断だけならログインは不要です。</div>',unsafe_allow_html=True)
