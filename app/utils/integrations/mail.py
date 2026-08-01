"""
汎用メール受信（IMAP）ユーティリティ

Gmail / Outlook(M365) / Yahoo / iCloud / その他 を、接続先(IMAPホスト)の違いだけで
同一に扱う。プロバイダを選ぶと host/port が自動で決まる（other は手動指定）。

添付ファイルの抽出ロジックは Gmail 用実装を一般化したもの。
"""
import imaplib
import email
from email.header import decode_header, make_header
from email.utils import parseaddr


# プロバイダ・プリセット（画面の選択肢＝接続先の自動補完）
MAIL_PROVIDERS = {
    'gmail':   {'label': 'Gmail / Google Workspace', 'host': 'imap.gmail.com',        'port': 993},
    'outlook': {'label': 'Outlook / Microsoft 365',  'host': 'outlook.office365.com', 'port': 993},
    'yahoo':   {'label': 'Yahoo!メール',              'host': 'imap.mail.yahoo.co.jp', 'port': 993},
    'icloud':  {'label': 'iCloud メール',             'host': 'imap.mail.me.com',      'port': 993},
    'other':   {'label': 'その他（IMAP手動設定）',    'host': '',                      'port': 993},
}


def provider_label(name: str) -> str:
    p = MAIL_PROVIDERS.get((name or '').strip().lower())
    return p['label'] if p else (name or '')


def resolve_host_port(provider: str, host: str = None, port: int = None):
    """プロバイダから host/port を解決（other や上書き指定は入力値を優先）"""
    preset = MAIL_PROVIDERS.get((provider or '').strip().lower(), MAIL_PROVIDERS['other'])
    resolved_host = (host or '').strip() or preset['host']
    try:
        resolved_port = int(port) if port else preset['port']
    except Exception:
        resolved_port = preset['port']
    return resolved_host, resolved_port


class MailError(RuntimeError):
    pass


def _decode(s) -> str:
    if not s:
        return ''
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return str(s)


class ImapMailClient:
    """プロバイダ非依存のIMAP受信クライアント"""

    def __init__(self, email_address: str, app_password: str, host: str, port: int = 993):
        if not email_address or not app_password:
            raise MailError('メールアドレスとパスワードが必要です')
        if not host:
            raise MailError('IMAPサーバー（ホスト）が指定されていません')
        self.email_address = email_address.strip()
        self.app_password = app_password
        self.host = host
        self.port = int(port or 993)
        self._conn = None

    def connect(self):
        try:
            self._conn = imaplib.IMAP4_SSL(self.host, self.port)
            self._conn.login(self.email_address, self.app_password)
        except imaplib.IMAP4.error as e:
            raise MailError(f'メールログインに失敗しました: {e}')
        except Exception as e:
            raise MailError(f'メール接続エラー ({self.host}:{self.port}): {e}')
        return self

    def close(self):
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def verify(self) -> bool:
        self.connect()
        self.close()
        return True

    def fetch_new_with_attachments(self, since_uid: int = 0, mailbox: str = 'INBOX',
                                   max_messages: int = 100):
        """since_uid より後の新着メールから、添付付きを取得。
        Returns: (messages, max_uid)
          messages: [{'uid','from','subject','date','attachments':[{'filename','data'}]}]
        """
        if not self._conn:
            self.connect()
        typ, _ = self._conn.select(mailbox, readonly=True)
        if typ != 'OK':
            raise MailError(f'メールボックスを開けません: {mailbox}')

        search_from = (since_uid or 0) + 1
        typ, data = self._conn.uid('search', None, f'UID {search_from}:*')
        if typ != 'OK':
            return [], since_uid
        uids = [int(x) for x in data[0].split()] if data and data[0] else []
        uids = sorted(u for u in uids if u > (since_uid or 0))[:max_messages]

        results = []
        max_uid = since_uid or 0
        for uid in uids:
            max_uid = max(max_uid, uid)
            typ, msg_data = self._conn.uid('fetch', str(uid), '(RFC822)')
            if typ != 'OK' or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
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
                results.append({'uid': uid, 'from': from_addr, 'subject': subject,
                                'date': date, 'attachments': attachments})
        return results, max_uid
