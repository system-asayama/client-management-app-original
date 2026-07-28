#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gmail 受信添付 自動保存バッチ（IMAPポーリング）

【実行方法】
  python batch_gmail.py

【Heroku Schedulerの設定】
  Command: python batch_gmail.py
  Frequency: 10分〜1時間ごと（運用に合わせて）

【自前サーバー（VPS）のcron例】
  */15 * * * * cd /path/to/app && python batch_gmail.py >> /var/log/gmail_batch.log 2>&1

【処理内容】
  Gmail連携が有効な全テナントについて、前回処理以降の新着メールの添付を取得し、
  差出人から顧問先を特定して、選択ストレージへ保存する。
  処理済みメールは since_uid（T_連携設定.extra）で管理し重複取得を防ぐ。
"""
import sys
from datetime import datetime


def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Gmail同期バッチ開始")
    try:
        import app  # noqa: F401  モデル登録・テーブル作成
        from app.services.gmail_sync import sync_all_tenants
    except Exception as e:
        print(f"❌ 初期化エラー: {e}")
        return 1

    try:
        summary = sync_all_tenants()
    except Exception as e:
        print(f"❌ 同期処理エラー: {e}")
        return 1

    print(f"✅ 完了: 対象テナント {summary['tenants']} / "
          f"保存 {summary['saved']}件 / スキップ {summary['skipped']}件 / "
          f"エラー {len(summary['errors'])}件")
    for err in summary['errors'][:20]:
        print(f"   - {err}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
