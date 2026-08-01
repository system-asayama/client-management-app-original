#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
受信系連携 一括自動保存バッチ（ChatWork + Gmail）

「Gmail / ChatWork で届いた資料を、選択ストレージの指定フォルダへ自動保存」を
1コマンドで実行する。定期実行はこのスクリプトをスケジューラに1つ登録すればよい。

【Heroku Scheduler】
  Command: python batch_integrations.py
  Frequency: 10分ごと（最短）〜運用に合わせて

【cron（VPS等）】
  */10 * * * * cd /path/to/app && python batch_integrations.py >> /var/log/integrations.log 2>&1

処理内容:
  1. ChatWork連携が有効な全テナントのルームから新着ファイルを取得→保存
  2. Gmail連携が有効な全テナントの新着メール添付を取得→保存
  いずれも重複防止付き（T_受信ファイル / since_uid）。
"""
import sys
from datetime import datetime


def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 受信系連携バッチ開始")
    try:
        import app  # noqa: F401  モデル登録・テーブル作成
    except Exception as e:
        print(f"❌ 初期化エラー: {e}")
        return 1

    total_saved = 0
    total_errors = 0

    # ChatWork
    try:
        from app.services.chatwork_sync import sync_all_tenants as cw_sync
        r = cw_sync()
        total_saved += r['saved']
        total_errors += len(r['errors'])
        print(f"  💬 ChatWork: テナント{r['tenants']} / 保存{r['saved']} / "
              f"スキップ{r['skipped']} / エラー{len(r['errors'])}")
        for e in r['errors'][:10]:
            print(f"     - {e}")
    except Exception as e:
        total_errors += 1
        print(f"  ❌ ChatWork同期エラー: {e}")

    # Gmail
    try:
        from app.services.gmail_sync import sync_all_tenants as gm_sync
        r = gm_sync()
        total_saved += r['saved']
        total_errors += len(r['errors'])
        print(f"  📧 Gmail: テナント{r['tenants']} / 保存{r['saved']} / "
              f"スキップ{r['skipped']} / エラー{len(r['errors'])}")
        for e in r['errors'][:10]:
            print(f"     - {e}")
    except Exception as e:
        total_errors += 1
        print(f"  ❌ Gmail同期エラー: {e}")

    print(f"✅ 完了: 合計保存 {total_saved}件 / エラー {total_errors}件")
    return 0


if __name__ == '__main__':
    sys.exit(main())
