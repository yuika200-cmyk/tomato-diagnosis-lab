"""Personal registered Teachable Machine model diagnostic preview.

Uses only authenticated user's model_registrations rows (RLS) and a browser-side
Teachable Machine image model. This is isolated from normal 3-model diagnosis,
advice mapping, and saved diagnosis history.
"""
import base64
import io
import json
from html import escape

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps

import history_cloud
from model_registry import validate_model_url

_MODEL_TYPES = ("株全体", "葉", "実")


def _navigate(page):
    st.session_state.page = page
    st.session_state.force_scroll_top = True
    st.rerun()


def _iframe(model_url, image_bytes):
    """Run TM TFJS exported model in the browser, never install/execute remote Python."""
    img_b64 = base64.b64encode(image_bytes).decode("ascii")
    safe_url = validate_model_url(model_url)
    # JSON serialization ensures user-supplied registered data cannot inject JS.
    model_js = json.dumps(safe_url)
    img_js = json.dumps("data:image/jpeg;base64," + img_b64)
    document = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<style>
  body{margin:0;background:#fff;color:#173b2b;font-family:system-ui,-apple-system,sans-serif}
  .box{padding:14px;border:1px solid #dbe9df;border-radius:12px}
  h3{font-size:17px;margin:0 0 8px} p{font-size:13px;color:#596b60}
  #photo{max-height:195px;max-width:100%;object-fit:contain;border-radius:8px}
  .progress{height:10px;border-radius:12px;background:#eaf2ec;overflow:hidden;margin:4px 0 11px}
  .fill{height:100%;background:#2f8f47;border-radius:12px}
  .line{display:flex;justify-content:space-between;gap:12px;font-size:13px;line-height:1.5}
  #state{font-size:14px;line-height:1.65} .muted{color:#7a857c;font-size:12px}
</style>
<script src="https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@1.3.1/dist/tf.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@teachablemachine/image@0.8/dist/teachablemachine-image.min.js"></script>
</head><body><div class="box">
<h3>登録モデルの判定結果</h3>
<img id="photo" alt="判定する写真">
<p id="state">AIモデルを読み込んでいます…</p><div id="scores"></div>
<p class="muted">この画面の判定は登録モデルによるものです。標準診断の履歴やアドバイスには反映しません。</p>
</div>
<script>
const url = __MODEL_URL__;
const photo = __IMAGE_DATA__;
function el(tag, className, text){const x=document.createElement(tag);if(className)x.className=className;if(text!==undefined)x.textContent=text;return x;}
async function run(){
 const state=document.getElementById('state');
 const img=document.getElementById('photo');
 img.src=photo;
 try {
  if(!window.tmImage){throw Error('Teachable Machineの実行ライブラリを読み込めませんでした。');}
  await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('写真を読み込めませんでした。'));});
  const model=await tmImage.load(url+'model.json', url+'metadata.json');
  const results=await model.predict(img, false);
  results.sort((a,b)=>b.probability-a.probability);
  state.textContent='判定結果：'+results[0].className;
  const scores=document.getElementById('scores');scores.replaceChildren();
  for(const x of results){
   const pct=Math.round(x.probability*1000)/10;
   const line=el('div','line');line.append(el('span','',x.className),el('strong','',pct.toFixed(1)+'%'));
   const outer=el('div','progress');const inner=el('div','fill');inner.style.width=pct+'%';outer.append(inner);
   scores.append(line,outer);
  }
 }catch(e){state.textContent='診断できませんでした。モデルURLの公開設定や通信状況を確認してください。';
   const help=el('p','muted',String(e && e.message || e));document.getElementById('scores').replaceChildren(help);
 }
}
run();
</script></body></html>"""
    document = document.replace('__MODEL_URL__',model_js).replace('__IMAGE_DATA__',img_js)
    components.html(document, height=540, scrolling=True)


def show():
    st.markdown('## 登録したモデルで診断する')
    st.caption('自分が登録したTeachable Machineのモデルで写真を判定します。標準モデルには影響しません。')
    try:
        db, user = history_cloud.client(), history_cloud.user()
    except Exception:
        db, user = None, None
    if db is None or user is None:
        st.info('登録モデルの診断にはログインが必要です。')
        if st.button('ログイン・登録へ',key='registered_model_login'):
            _navigate('account')
        if st.button('← AIモデルの改善へ戻る',key='registered_model_back_nologin'):
            _navigate('model_improve')
        return
    try:
        rows=(db.table('model_registrations')
              .select('id,name,model_type,model_url,created_at')
              .eq('user_id',str(user.id))
              .order('created_at',desc=True).execute().data or [])
    except Exception:
        st.error('登録モデルを取得できませんでした。ログイン状態や通信を確認してください。')
        if st.button('← 戻る',key='registered_model_back_error'):_navigate('model_improve')
        return
    valid=[]
    for row in rows:
        if row.get('model_type') not in _MODEL_TYPES:continue
        try: row['model_url']=validate_model_url(row.get('model_url',''))
        except (ValueError,TypeError):continue
        valid.append(row)
    if not valid:
        st.info('使用できる登録モデルがまだありません。先にモデルを登録してください。')
        if st.button('モデルを登録する',key='registered_model_to_registry'):_navigate('model_registry')
        if st.button('← 戻る',key='registered_model_back_empty'):_navigate('model_improve')
        return
    choice=st.selectbox('診断に使用するモデル',range(len(valid)),
        format_func=lambda i:f"{valid[i]['name']}（{valid[i]['model_type']}）",key='registered_selected_model')
    model=valid[choice]
    st.caption('診断対象：'+model['model_type']+'／モデル名：'+str(model['name']))
    photo=st.file_uploader('診断するミニトマトの写真を選択',type=['jpg','jpeg','png','heic','heif'],key='registered_model_photo')
    if photo is not None:
        try:
            if photo.size>10*1024*1024:raise ValueError('画像は10MB以下にしてください。')
            raw=photo.getvalue()
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                rgb=ImageOps.exif_transpose(im).convert('RGB')
                if rgb.width*rgb.height>25_000_000:raise ValueError('画像が大きすぎます。')
                rgb.thumbnail((1400,1400),Image.Resampling.LANCZOS)
                buf=io.BytesIO();rgb.save(buf,format='JPEG',quality=85)
                jpeg=buf.getvalue()
        except (OSError,ValueError) as exc:
            st.warning('画像を確認できませんでした：'+str(exc));jpeg=None
        if jpeg is not None:
            if st.button('このモデルで診断する',type='primary',use_container_width=True,key='registered_model_run'):
                st.session_state['registered_preview']={'id':str(model['id']),'photo':jpeg}
            preview=st.session_state.get('registered_preview')
            if preview and preview['id']==str(model['id']) and preview['photo']==jpeg:
                _iframe(model['model_url'],jpeg)
    if st.button('← AIモデルの改善へ戻る',key='registered_model_back'):
        _navigate('model_improve')
