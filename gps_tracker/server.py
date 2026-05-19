# -*- coding: utf-8 -*-
"""Teltonika車載GPS機器を受け付けるTCPサーバー

機器1台ごとに1スレッドで処理する。プロトコルの流れ:
  1. 機器がIMEIを送信 → サーバーが 0x01(受理) / 0x00(拒否) を返す
  2. 機器がAVLパケットを送信 → サーバーが受信レコード数(4バイト)を返す
  3. 2を接続が切れるまで繰り返す
"""
import logging
import os
import socket
import socketserver
import struct
from datetime import timedelta

from gps_tracker import db
from gps_tracker.codec import CodecError, crc16_ibm, parse_avl_data

logger = logging.getLogger("gps_tracker.server")

# 機器のUTCタイムスタンプを保存時に変換するオフセット（既存の地図表示は
# サーバーのローカル時刻基準で日付絞り込みを行うため）
TZ_OFFSET = timedelta(hours=float(os.environ.get("GPS_TZ_OFFSET_HOURS", "9")))
# アイドル接続を切断するまでの秒数
SOCKET_TIMEOUT = int(os.environ.get("GPS_SOCKET_TIMEOUT", "1800"))
# データ部の最大許容サイズ（異常パケット対策）
MAX_DATA_LENGTH = 200000


class TeltonikaHandler(socketserver.BaseRequestHandler):
    """1台のGPS機器との接続を処理する"""

    def _recv_exact(self, n: int):
        """nバイト受信しきるまで読む。接続が切れたら None。"""
        buf = b""
        while len(buf) < n:
            chunk = self.request.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def handle(self):
        peer = "%s:%s" % self.client_address
        self.request.settimeout(SOCKET_TIMEOUT)
        imei = self._do_imei_handshake(peer)
        if imei is None:
            return
        truck = db.get_truck_by_imei(imei)
        if truck is None:
            logger.warning("未登録のIMEI: %s (%s) — 接続を拒否", imei, peer)
            self.request.sendall(b"\x00")
            return
        self.request.sendall(b"\x01")
        logger.info("接続確立: IMEI=%s truck_id=%s (%s)", imei, truck.id, peer)

        try:
            while True:
                if self._handle_avl_packet(imei, truck) is None:
                    break
        except (CodecError, struct.error) as e:
            logger.error("AVL解析エラー IMEI=%s: %s", imei, e)
        except socket.timeout:
            logger.info("タイムアウトで切断: IMEI=%s (%s)", imei, peer)
        except OSError as e:
            logger.info("接続エラー IMEI=%s: %s", imei, e)
        logger.info("接続終了: IMEI=%s (%s)", imei, peer)

    def _do_imei_handshake(self, peer: str):
        """IMEIハンドシェイクを処理し、IMEI文字列を返す。失敗時は None。"""
        head = self._recv_exact(2)
        if not head:
            return None
        imei_len = struct.unpack(">H", head)[0]
        if imei_len == 0 or imei_len > 20:
            logger.warning("不正なIMEI長 from %s: %s", peer, imei_len)
            self.request.sendall(b"\x00")
            return None
        imei_raw = self._recv_exact(imei_len)
        if not imei_raw:
            return None
        try:
            imei = imei_raw.decode("ascii").strip()
        except UnicodeDecodeError:
            logger.warning("IMEIをデコードできません from %s", peer)
            self.request.sendall(b"\x00")
            return None
        if not imei.isdigit():
            logger.warning("IMEIが数字ではありません from %s: %r", peer, imei)
            self.request.sendall(b"\x00")
            return None
        return imei

    def _handle_avl_packet(self, imei: str, truck):
        """AVLパケットを1つ受信・解析・保存し、ACKを返す。

        戻り値: 受信レコード数。接続終了なら None。
        """
        header = self._recv_exact(8)
        if not header:
            return None
        preamble, data_len = struct.unpack(">II", header)
        if preamble != 0:
            raise CodecError(f"プリアンブルが0ではありません: {preamble}")
        if data_len == 0 or data_len > MAX_DATA_LENGTH:
            raise CodecError(f"データ長が不正です: {data_len}")
        data = self._recv_exact(data_len)
        if not data:
            return None
        crc_raw = self._recv_exact(4)
        if not crc_raw:
            return None
        expected_crc = struct.unpack(">I", crc_raw)[0] & 0xFFFF
        if crc16_ibm(data) != expected_crc:
            raise CodecError("CRCが一致しません")

        _, records = parse_avl_data(data)
        self._store(imei, truck, records)
        # ACK: 受信した全レコード数を返す（機器が送信バッファをクリアする）
        self.request.sendall(struct.pack(">I", len(records)))
        return len(records)

    def _store(self, imei: str, truck, records):
        """測位有効なレコードを T_トラック運行位置履歴 に保存する"""
        valid = [r for r in records if r.has_fix]
        if not valid:
            logger.info("IMEI=%s: %d件受信（測位有効0件）", imei, len(records))
            return
        operation = db.get_active_operation(truck.id)
        rows = []
        for r in valid:
            local_dt = (r.timestamp_utc + TZ_OFFSET).replace(tzinfo=None)
            rows.append({
                "operation_id": operation.id if operation else None,
                "driver_id": operation.driver_id if operation else None,
                "truck_id": truck.id,
                "tenant_id": (operation.tenant_id if operation else None) or truck.tenant_id,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "accuracy": None,
                "speed": float(r.speed),
                "recorded_at": local_dt,
            })
        saved = db.insert_locations(rows)
        logger.info(
            "IMEI=%s: %d件保存（受信%d件 / operation_id=%s）",
            imei, saved, len(records),
            operation.id if operation else None,
        )


class ThreadedTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve():
    """TCPサーバーを起動する"""
    host = os.environ.get("GPS_TCP_HOST", "0.0.0.0")
    port = int(os.environ.get("GPS_TCP_PORT", "5027"))
    server = ThreadedTCPServer((host, port), TeltonikaHandler)
    logger.info("GPS受信サーバーを起動します: %s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("停止要求を受信しました")
    finally:
        server.shutdown()
        server.server_close()
