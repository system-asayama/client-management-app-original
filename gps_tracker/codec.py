# -*- coding: utf-8 -*-
"""Teltonika Codec 8 / Codec 8 Extended プロトコルのパーサ

参考: Teltonika Telematics プロトコル仕様
  - IMEIハンドシェイク: [2バイト長][IMEI ASCII]
  - AVLパケット: [4バイト プリアンブル=0][4バイト データ長][データ部][4バイト CRC-16]
  - データ部: [Codec ID][レコード数][AVLレコード...][レコード数][CRC対象]
"""
import struct
from dataclasses import dataclass
from datetime import datetime, timezone

CODEC_8 = 0x08
CODEC_8_EXT = 0x8E


class CodecError(Exception):
    """プロトコル解析エラー"""


def crc16_ibm(data: bytes) -> int:
    """CRC-16/IBM (CRC-16/ARC, 多項式0xA001) を計算する。

    Teltonika AVLパケットのCRC検証に使用する。
    """
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


@dataclass
class AvlRecord:
    """AVLレコード1件（1つの位置情報）"""
    timestamp_utc: datetime
    priority: int
    longitude: float
    latitude: float
    altitude: int
    angle: int
    satellites: int
    speed: int  # km/h

    @property
    def has_fix(self) -> bool:
        """GPS測位が有効かどうか（衛星捕捉あり・座標が0,0でない）"""
        return self.satellites > 0 and not (
            self.longitude == 0.0 and self.latitude == 0.0
        )


def parse_imei_message(data: bytes) -> str:
    """IMEIハンドシェイクメッセージ ([2バイト長][IMEI]) からIMEIを取り出す"""
    if len(data) < 2:
        raise CodecError("IMEIメッセージが短すぎます")
    length = struct.unpack_from(">H", data, 0)[0]
    if length <= 0 or len(data) < 2 + length:
        raise CodecError(f"IMEI長が不正です: {length}")
    imei = data[2:2 + length].decode("ascii", errors="ignore").strip()
    if not imei.isdigit():
        raise CodecError(f"IMEIが数字ではありません: {imei!r}")
    return imei


def parse_avl_data(data: bytes):
    """AVLデータ部（Codec ID〜2つ目のレコード数）を解析する。

    戻り値: (codec_id, [AvlRecord, ...])
    """
    if len(data) < 3:
        raise CodecError("AVLデータが短すぎます")
    codec_id = data[0]
    if codec_id not in (CODEC_8, CODEC_8_EXT):
        raise CodecError(f"非対応のCodec ID: 0x{codec_id:02X}")
    extended = codec_id == CODEC_8_EXT
    count = data[1]
    offset = 2
    records = []
    for _ in range(count):
        record, offset = _parse_record(data, offset, extended)
        records.append(record)
    if offset >= len(data):
        raise CodecError("末尾のレコード数が読み取れません")
    count2 = data[offset]
    if count2 != count:
        raise CodecError(f"レコード数が一致しません: {count} != {count2}")
    return codec_id, records


def _parse_record(data: bytes, offset: int, extended: bool):
    """AVLレコード1件を解析し、(AvlRecord, 次のオフセット) を返す"""
    o = offset
    ts_ms = struct.unpack_from(">Q", data, o)[0]
    o += 8
    priority = data[o]
    o += 1
    lon_raw, lat_raw = struct.unpack_from(">ii", data, o)
    o += 8
    altitude, angle = struct.unpack_from(">hH", data, o)
    o += 4
    satellites = data[o]
    o += 1
    speed = struct.unpack_from(">H", data, o)[0]
    o += 2

    # IO要素部はサイズ算出のため読み飛ばす（位置情報の保存には不要）
    if extended:
        o += 2  # Event IO ID (2バイト)
        o += 2  # 全IO数 (2バイト)
        for value_size in (1, 2, 4, 8):
            io_count = struct.unpack_from(">H", data, o)[0]
            o += 2
            o += io_count * (2 + value_size)
        # 可変長IO要素
        nx_count = struct.unpack_from(">H", data, o)[0]
        o += 2
        for _ in range(nx_count):
            o += 2  # IO ID
            value_len = struct.unpack_from(">H", data, o)[0]
            o += 2 + value_len
    else:
        o += 1  # Event IO ID (1バイト)
        o += 1  # 全IO数 (1バイト)
        for value_size in (1, 2, 4, 8):
            io_count = data[o]
            o += 1
            o += io_count * (1 + value_size)

    record = AvlRecord(
        timestamp_utc=datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc),
        priority=priority,
        longitude=lon_raw / 1e7,
        latitude=lat_raw / 1e7,
        altitude=altitude,
        angle=angle,
        satellites=satellites,
        speed=speed,
    )
    return record, o
