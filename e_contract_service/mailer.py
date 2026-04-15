"""
電子契約サービス メール送信ユーティリティ

テナントのSMTP設定を使って署名依頼メールを送信する。
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


def _get_store_smtp(store_id: int) -> Optional[dict]:
    """メインDBから店舗のSMTP設定を取得する"""
    try:
        from app.db import SessionLocal as MainSessionLocal
        from app.models_login import TTenpo
        db = MainSessionLocal()
        try:
            store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
            if not store:
                return None
            host = getattr(store, 'smtp_host', None)
            if not host:
                return None
            return {
                'host': host,
                'port': getattr(store, 'smtp_port', None) or 587,
                'username': getattr(store, 'smtp_username', None),
                'password': getattr(store, 'smtp_password', None),
                'use_tls': getattr(store, 'smtp_use_tls', 1),
                'from_email': getattr(store, 'smtp_from_email', None),
                'from_name': getattr(store, 'smtp_from_name', None) or '',
            }
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"店舗SMTP設定取得エラー: {e}")
        return None


def _get_tenant_smtp(tenant_id: int) -> Optional[dict]:
    """後方互換: テナントIDからSMTP設定を取得（非推奨）"""
    return None


def send_signing_request_email(
    tenant_id: int,
    signer_name: str,
    signer_email: str,
    contract_title: str,
    sign_url: str,
    expires_at: str,
    store_id: Optional[int] = None,
) -> bool:
    """
    署名依頼メールを送信する。
    store_id が指定された場合は店舗のSMTP設定を優先して使用する。

    Returns:
        True: 送信成功
        False: 送信失敗（SMTP未設定含む）
    """
    smtp = None
    if store_id:
        smtp = _get_store_smtp(store_id)
        if not smtp:
            logger.info(f"店舗 {store_id} のSMTP設定がないためメール送信をスキップ")
            return False
    else:
        logger.info(f"store_id が未指定のためメール送信をスキップ")
        return False

    from_addr = smtp['from_email']
    from_name = smtp['from_name']
    if not from_addr:
        logger.warning(f"店舗 {store_id} の差出人メールアドレスが未設定")
        return False

    subject = f"【電子署名のご依頼】{contract_title}"

    html_body = f"""
<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"></head>
<body style="font-family: 'Helvetica Neue', Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
  <div style="background: #f8f9fa; border-radius: 8px; padding: 24px; margin-bottom: 24px;">
    <h1 style="color: #1a1a2e; font-size: 1.3em; margin: 0 0 8px 0;">📝 電子署名のご依頼</h1>
    <p style="color: #6b7280; margin: 0; font-size: 0.9em;">{from_name}</p>
  </div>

  <p>{signer_name} 様</p>
  <p>以下の契約書への電子署名をお願いいたします。</p>

  <div style="background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 24px 0;">
    <table style="width: 100%; border-collapse: collapse;">
      <tr>
        <td style="padding: 8px 0; color: #6b7280; font-size: 0.9em; width: 120px;">契約書名</td>
        <td style="padding: 8px 0; font-weight: 600;">{contract_title}</td>
      </tr>
      <tr>
        <td style="padding: 8px 0; color: #6b7280; font-size: 0.9em;">署名期限</td>
        <td style="padding: 8px 0;">{expires_at}</td>
      </tr>
    </table>
  </div>

  <div style="text-align: center; margin: 32px 0;">
    <a href="{sign_url}"
       style="background: #2563a8; color: #fff; padding: 14px 32px; border-radius: 6px;
              text-decoration: none; font-weight: 600; font-size: 1em; display: inline-block;">
      ✍️ 署名ページを開く
    </a>
  </div>

  <p style="font-size: 0.85em; color: #6b7280;">
    上記ボタンが機能しない場合は、以下のURLをブラウザに貼り付けてください：<br>
    <a href="{sign_url}" style="color: #2563a8; word-break: break-all;">{sign_url}</a>
  </p>

  <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
  <p style="font-size: 0.8em; color: #9ca3af;">
    このメールは {from_name} の電子契約システムから自動送信されています。<br>
    心当たりのない場合はこのメールを無視してください。
  </p>
</body>
</html>
"""

    text_body = f"""{signer_name} 様

{contract_title} への電子署名をお願いいたします。

署名ページ: {sign_url}
署名期限: {expires_at}

このメールは {from_name} の電子契約システムから自動送信されています。
"""

    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{from_name} <{from_addr}>" if from_name else from_addr
        msg['To'] = signer_email
        msg['Subject'] = subject
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        use_tls = smtp['use_tls']
        host = smtp['host']
        port = int(smtp['port'])
        user = smtp['username']
        pwd = smtp['password']

        if use_tls == 2:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if use_tls == 1:
                server.starttls()

        if user and pwd:
            server.login(user, pwd)

        server.sendmail(from_addr, [signer_email], msg.as_string())
        server.quit()
        logger.info(f"署名依頼メール送信成功: {signer_email} ({contract_title})")
        return True

    except Exception as e:
        logger.error(f"署名依頼メール送信エラー: {signer_email} - {e}")
        return False
