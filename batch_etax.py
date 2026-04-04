#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
e-Tax 納付情報登録依頼 定期自動送信バッチスクリプト

【実行方法】
  python batch_etax.py

【Heroku Schedulerの設定】
  Command: python batch_etax.py
  Frequency: Daily（毎日 AM 2:00 JST = PM 5:00 UTC）

【自前サーバー（VPS）への移行時】
  crontab に以下を追加するだけでOK:
  0 2 * * * cd /path/to/app && python batch_etax.py >> /var/log/etax_batch.log 2>&1

【処理内容】
  1. 納付期限が1ヶ月前に迫っている中間申告対象の顧問先を抽出
  2. TEtaxRequestレコードを作成
  3. 各顧問先のe-Taxに自動ログインして納付情報登録依頼を送信
  4. 納付区分番号を取得してDBに保存
"""

import os
import sys
import logging
from datetime import datetime

# アプリケーションのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("batch_etax")


def main():
    logger.info("=" * 60)
    logger.info("e-Tax 定期自動送信バッチ 開始")
    logger.info(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    try:
        from app.utils.etax.etax_service import (
            get_pending_auto_requests_for_today,
            execute_etax_request,
        )

        # Step 1: 本日実行すべきリクエストを取得（なければ新規作成）
        logger.info("\n[Step 1] 本日の送信対象を抽出...")
        request_ids = get_pending_auto_requests_for_today()

        if not request_ids:
            logger.info("本日の送信対象はありません。バッチ終了。")
            return

        logger.info(f"送信対象: {len(request_ids)} 件 (IDs: {request_ids})")

        # Step 2: 各リクエストを順番に実行
        success_count = 0
        error_count = 0

        for req_id in request_ids:
            logger.info(f"\n[Step 2] request_id={req_id} 処理開始...")
            result = execute_etax_request(req_id)

            if result["status"] == "completed":
                success_count += 1
                logger.info(f"  ✅ request_id={req_id} 完了: {result.get('message', '')}")
            elif result["status"] == "skipped":
                logger.info(f"  ⏭️  request_id={req_id} スキップ: {result.get('message', '')}")
            else:
                error_count += 1
                logger.error(f"  ❌ request_id={req_id} エラー: {result.get('message', '')}")

            # 連続送信による負荷を避けるため少し待機
            import time
            time.sleep(5)

        # Step 3: 結果サマリー
        logger.info("\n" + "=" * 60)
        logger.info("バッチ処理完了")
        logger.info(f"  成功: {success_count} 件")
        logger.info(f"  エラー: {error_count} 件")
        logger.info(f"  合計: {len(request_ids)} 件")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"バッチ処理中に予期しないエラーが発生しました: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
