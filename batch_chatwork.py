#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChatWork 受信ファイル 自動保存バッチ

【実行方法】
  python batch_chatwork.py

【Heroku Schedulerの設定】
  Command: python batch_chatwork.py
  Frequency: 10分ごと / 1時間ごと 等（運用に合わせて）

【自前サーバー（VPS）のcron例】
  */15 * * * * cd /path/to/app && python batch_chatwork.py >> /var/log/chatwork_batch.log 2>&1

【処理内容】
  ChatWork連携が有効な全テナントについて、紐付け済みルームの新着ファイルを
  取得し、テナントが選択したストレージ（Dropbox/GCS/Cloudinary 等）へ保存する。
  受信済みファイルは T_受信ファイル で重複防止される。
"""
import sys
from datetime import datetime


def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] ChatWork同期バッチ開始")
    try:
        # モデル登録・テーブル作成を走らせるため app を import
        import app  # noqa: F401
        from app.services.chatwork_sync import sync_all_tenants
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
