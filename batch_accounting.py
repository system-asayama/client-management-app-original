#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会計ソフト（freee等）自動アップロードバッチ

【実行方法】
  python batch_accounting.py

【Heroku Schedulerの設定】
  Command: python batch_accounting.py
  Frequency: 10分〜1時間ごと（運用に合わせて）

【自前サーバー（VPS）のcron例】
  */30 * * * * cd /path/to/app && python batch_accounting.py >> /var/log/accounting_batch.log 2>&1

【処理内容】
  会計ソフト連携が有効な全テナントについて、ストレージ保存済みで未送信の
  受信資料を、顧問先ごとに紐づく会計ソフトのファイルボックスへアップロードする。
  アップロード済みファイルは T_会計ソフトアップロード で重複防止される。
"""
import sys
from datetime import datetime


def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 会計ソフト自動アップロードバッチ開始")
    try:
        import app  # noqa: F401  モデル登録・テーブル作成
        from app.services.accounting_upload import upload_all_tenants
    except Exception as e:
        print(f"❌ 初期化エラー: {e}")
        return 1

    try:
        summary = upload_all_tenants()
    except Exception as e:
        print(f"❌ 処理エラー: {e}")
        return 1

    print(f"✅ 完了: 対象テナント {summary['tenants']} / "
          f"アップロード {summary['uploaded']}件 / スキップ {summary['skipped']}件 / "
          f"エラー {len(summary['errors'])}件")
    for err in summary['errors'][:20]:
        print(f"   - {err}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
