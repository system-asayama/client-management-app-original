"""
Gmail IMAP クライアント（最小実装）

Gmail の IMAP でメールを取得し、添付ファイルを抽出する。
認証は「アプリパスワード」を利用（2段階認証必須）。

参考:
  - IMAPホスト: imap.gmail.com:993 (SSL)
  - アプリパスワード: https://myaccount.google.com/apppasswords
"""
import imaplib
import email
from email.header import decode_header, make_header
from email.utils import parseaddr

IMAP_HOST = 'imap.gmail.com'
IMAP_PORT = 993


class GmailImapError(RuntimeError):
    pass


def _decode(s) -> str:
    if not s:
        return ''
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return str(s)


class GmailImapClient:
    def __init__(self, email_address: str, app_password: str,
                 host: str = IMAP_HOST, port: int = IMAP_PORT):
        if not email_address or not app_password:
            raise GmailImapError('メールアドレスとアプリパスワードが必要です')
        self.email_address = email_address.strip()
        self.app_password = app_password
        self.host = host or IMAP_HOST
        self.port = port or IMAP_PORT
        self._conn = None

    def connect(self):
        try:
            self._conn = imaplib.IMAP4_SSL(self.host, self.port)
            self._conn.login(self.email_address, self.app_password)
        except imaplib.IMAP4.error as e:
            raise GmailImapError(f'Gmail IMAPログインに失敗しました: {e}')
        except Exception as e:
            raise GmailImapError(f'Gmail IMAP接続エラー: {e}')
        return self

    def close(self):
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def verify(self) -> bool:
        """疎通確認（接続してすぐ閉じる）"""
        self.connect()
        self.close()
        return True

    def fetch_new_with_attachments(self, since_uid: int = 0, mailbox: str = 'INBOX',
                                   max_messages: int = 100) -> list:
        """
        since_uid より大きいUIDのメールから添付付きのものを取得。

        Returns: [{
            'uid': int, 'from': str(email小文字), 'subject': str, 'date': str,
            'attachments': [{'filename': str, 'data': bytes}]
        }], および処理した最大UID
        """
        if not self._conn:
            self.connect()
        typ, _ = self._conn.select(mailbox, readonly=True)
        if typ != 'OK':
            raise GmailImapError(f'メールボックスを開けません: {mailbox}')

        # UID検索（since_uidの次から）
        search_from = (since_uid or 0) + 1
        typ, data = self._conn.uid('search', None, f'UID {search_from}:*')
        if typ != 'OK':
            return [], since_uid
        uids = [int(x) for x in data[0].split()] if data and data[0] else []
        # UID a:* は該当が無くても最後の1件を返すことがあるため since_uid 以下を除外
        uids = sorted(u for u in uids if u > (since_uid or 0))
        uids = uids[:max_messages]

        results = []
        max_uid = since_uid or 0
        for uid in uids:
            max_uid = max(max_uid, uid)
            typ, msg_data = self._conn.uid('fetch', str(uid), '(RFC822)')
            if typ != 'OK' or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            from_addr = parseaddr(msg.get('From', ''))[1].lower()
            subject = _decode(msg.get('Subject', ''))
            date = msg.get('Date', '')

            attachments = []
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                disp = (part.get('Content-Disposition') or '')
                filename = part.get_filename()
                if not filename and 'attachment' not in disp.lower():
                    continue
                if not filename:
                    continue
                filename = _decode(filename)
                try:
                    payload = part.get_payload(decode=True)
                except Exception:
                    payload = None
                if payload:
                    attachments.append({'filename': filename, 'data': payload})

            if attachments:
                results.append({
                    'uid': uid, 'from': from_addr, 'subject': subject,
                    'date': date, 'attachments': attachments,
                })

        return results, max_uid
