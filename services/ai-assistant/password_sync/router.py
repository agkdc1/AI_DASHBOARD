"""Password sync router — self-service AD + Google password change."""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

router = APIRouter()
log = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = (
    "YOUR_GOOGLE_OAUTH_CLIENT_ID"
)


class PasswordChangeRequest(BaseModel):
    google_credential: str  # JWT from Google Sign-In
    new_password: str


class PasswordChangeResponse(BaseModel):
    ad_ok: bool
    google_ok: bool
    message: str


@router.post("/password-sync/change", response_model=PasswordChangeResponse)
async def change_password(req: PasswordChangeRequest, request: Request):
    """Verify Google identity, then set new password in AD + Google."""
    # Verify the Google ID token
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        idinfo = id_token.verify_oauth2_token(
            req.google_credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except ValueError as e:
        log.warning("Google token verification failed: %s", e)
        raise HTTPException(401, "Google 認証に失敗しました。やり直してください。")

    email = idinfo.get("email", "").lower()
    if not email.endswith("@your-domain.com"):
        raise HTTPException(403, "your-domain.com のアカウントのみ利用できます")

    if not idinfo.get("email_verified"):
        raise HTTPException(403, "メールアドレスが確認されていません")

    if len(req.new_password) < 8:
        raise HTTPException(400, "パスワードは8文字以上にしてください")

    svc = request.app.state.password_sync
    result = await svc.sync_password(email, req.new_password)

    # Only raise 400 if both failed
    if not result["ad_ok"] and not result["google_ok"]:
        raise HTTPException(
            400, result.get("error", "パスワードの変更に失敗しました")
        )

    if result["ad_ok"] and result["google_ok"]:
        msg = "パスワードが変更されました（ファイル共有 + Google）"
    elif result["ad_ok"]:
        msg = "ファイル共有のパスワードが変更されました（Google は管理者に連絡してください）"
    else:
        msg = "Google パスワードは変更されましたが、ファイル共有の更新に失敗しました"

    return PasswordChangeResponse(
        ad_ok=result["ad_ok"],
        google_ok=result["google_ok"],
        message=msg,
    )


@router.get("/password-sync", response_class=HTMLResponse)
async def password_sync_page():
    """Serve the self-service password sync page."""
    return HTMLResponse(_PAGE_HTML)


_PAGE_HTML = (
    """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>パスワード同期 - Shinbee Japan</title>
<script src="https://accounts.google.com/gsi/client" async defer></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f5f5f5; color: #333; min-height: 100vh;
       display: flex; justify-content: center; align-items: center; padding: 20px; }
.card { background: #fff; border-radius: 12px; padding: 36px;
        box-shadow: 0 4px 24px rgba(0,0,0,0.1); max-width: 440px; width: 100%; }
h1 { font-size: 1.4em; margin-bottom: 6px; text-align: center; }
.subtitle { color: #666; font-size: 0.88em; text-align: center; margin-bottom: 24px; line-height: 1.5; }
.step { margin-bottom: 14px; }
.step-num { display: inline-block; width: 26px; height: 26px; border-radius: 50%;
            background: #1a73e8; color: #fff; text-align: center; line-height: 26px;
            font-size: 0.82em; font-weight: bold; margin-right: 8px; vertical-align: middle; }
.step-label { font-weight: 600; font-size: 0.95em; vertical-align: middle; }
.step-desc { color: #666; font-size: 0.83em; margin-top: 3px; margin-left: 34px; }
.google-btn-wrap { display: flex; justify-content: center; margin: 16px 0 8px; }
.form-group { margin-bottom: 14px; }
label { display: block; font-weight: 600; margin-bottom: 5px; font-size: 0.92em; }
input[type="password"] {
  width: 100%; padding: 11px 12px; border: 1px solid #ddd;
  border-radius: 8px; font-size: 0.95em; }
input:focus { outline: none; border-color: #1a73e8; box-shadow: 0 0 0 3px rgba(26,115,232,0.1); }
.hint { font-size: 0.8em; color: #888; margin-top: 4px; }
.btn { display: block; width: 100%; padding: 13px; border: none; border-radius: 8px;
       font-size: 1em; font-weight: 600; cursor: pointer; margin-top: 16px;
       transition: background 0.2s; background: #1a73e8; color: #fff; }
.btn:hover { background: #1557b0; }
.btn:disabled { background: #ccc; cursor: not-allowed; }
.status { padding: 12px; border-radius: 8px; margin-top: 16px; font-size: 0.9em;
          display: none; line-height: 1.4; }
.status.success { display: block; background: #e8f5e9; color: #2e7d32; }
.status.error { display: block; background: #fce4ec; color: #c62828; }
.status.info { display: block; background: #e3f2fd; color: #1565c0; }
.user-info { background: #f0f7ff; padding: 10px 14px; border-radius: 8px;
             margin-bottom: 16px; font-size: 0.9em; display: none; }
.user-info .email { font-weight: 600; color: #1a73e8; }
.divider { border-top: 1px solid #eee; margin: 16px 0; }
.logo { text-align: center; margin-bottom: 12px; font-size: 2em; }
#step2-section { display: none; }
</style>
</head>
<body>
<div class="card">
  <div class="logo">&#x1f511;</div>
  <h1>パスワード同期</h1>
  <p class="subtitle">ファイル共有 (Z: ドライブ) と Google アカウントの<br>パスワードを統一設定します</p>

  <div id="step1-section">
    <div class="step">
      <span class="step-num">1</span>
      <span class="step-label">本人確認</span>
      <p class="step-desc">会社の Google アカウントでログインしてください</p>
    </div>
    <div class="google-btn-wrap">
      <div id="g_id_onload"
           data-client_id=\""""
    + GOOGLE_CLIENT_ID
    + """\"
           data-callback="onGoogleSignIn"
           data-auto_prompt="false"
           data-hosted_domain="your-domain.com">
      </div>
      <div class="g_id_signin"
           data-type="standard"
           data-size="large"
           data-theme="outline"
           data-text="sign_in_with"
           data-shape="rectangular"
           data-logo_alignment="left"
           data-width="300">
      </div>
    </div>
  </div>

  <div id="step2-section">
    <div class="user-info" id="user-info">
      ログイン中: <span class="email" id="user-email"></span>
    </div>

    <div class="step">
      <span class="step-num">2</span>
      <span class="step-label">新しいパスワードを設定</span>
      <p class="step-desc">ファイル共有と Google の両方に適用されます</p>
    </div>

    <form id="pw-form" onsubmit="submitForm(event)">
      <div class="form-group">
        <label for="new-pw">新しいパスワード</label>
        <input type="password" id="new-pw" placeholder="8文字以上" required minlength="8">
        <p class="hint">英数字・記号を組み合わせてください</p>
      </div>
      <div class="form-group">
        <label for="confirm-pw">新しいパスワード（確認）</label>
        <input type="password" id="confirm-pw" placeholder="もう一度入力" required>
      </div>
      <button type="submit" class="btn" id="submit-btn">パスワードを変更</button>
    </form>
  </div>

  <div id="status" class="status"></div>
</div>

<script>
let googleCredential = null;

function onGoogleSignIn(response) {
  googleCredential = response.credential;
  // Decode JWT payload to show email
  try {
    const payload = JSON.parse(atob(googleCredential.split('.')[1]));
    if (payload.email) {
      document.getElementById('user-email').textContent = payload.email;
      document.getElementById('user-info').style.display = 'block';
    }
    if (!payload.email.endsWith('@your-domain.com')) {
      showStatus('error', 'your-domain.com のアカウントでログインしてください');
      return;
    }
  } catch(e) {}
  // Show step 2
  document.getElementById('step1-section').style.display = 'none';
  document.getElementById('step2-section').style.display = 'block';
  document.getElementById('status').style.display = 'none';
  document.getElementById('new-pw').focus();
}

async function submitForm(e) {
  e.preventDefault();
  const newPw = document.getElementById('new-pw').value;
  const confirmPw = document.getElementById('confirm-pw').value;

  if (newPw !== confirmPw) {
    showStatus('error', '新しいパスワードが一致しません');
    return;
  }
  if (newPw.length < 8) {
    showStatus('error', 'パスワードは8文字以上にしてください');
    return;
  }

  const btn = document.getElementById('submit-btn');
  btn.disabled = true;
  btn.textContent = '変更中...';
  showStatus('info', 'パスワードを変更しています...');

  try {
    const resp = await fetch('/password-sync/change', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        google_credential: googleCredential,
        new_password: newPw,
      }),
    });
    const data = await resp.json();

    if (resp.ok && data.ad_ok && data.google_ok) {
      showStatus('success',
        'パスワードが変更されました！<br>' +
        'ファイル共有 (Z: ドライブ) と Google の両方に適用されています。<br>' +
        '<br>このページを閉じてください。');
      document.getElementById('pw-form').reset();
    } else if (resp.ok) {
      showStatus('error', data.message);
    } else {
      const detail = data.detail || data.message || 'Unknown error';
      showStatus('error', detail);
    }
  } catch (e) {
    showStatus('error', 'ネットワークエラー: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'パスワードを変更';
  }
}

function showStatus(type, msg) {
  const el = document.getElementById('status');
  el.className = 'status ' + type;
  el.innerHTML = msg;
  el.style.display = 'block';
}
</script>
</body>
</html>"""
)
