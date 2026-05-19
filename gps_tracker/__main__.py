# -*- coding: utf-8 -*-
"""GPS受信サービスのエントリポイント

起動: python -m gps_tracker
環境変数:
  DATABASE_URL          接続先DB（必須・メインアプリと共通）
  GPS_TCP_HOST          待ち受けホスト（既定: 0.0.0.0）
  GPS_TCP_PORT          待ち受けポート（既定: 5027）
  GPS_TZ_OFFSET_HOURS   UTC→保存時刻のオフセット時間（既定: 9）
  GPS_SOCKET_TIMEOUT    アイドル切断までの秒数（既定: 1800）
"""
import logging

from gps_tracker.server import serve


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    serve()


if __name__ == "__main__":
    main()
