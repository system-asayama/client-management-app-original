# -*- coding: utf-8 -*-
"""gps_tracker.codec のテスト

Teltonika Codec 8 / Codec 8 Extended のパーサとCRC計算を検証する。
実行: python tests/test_gps_codec.py
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gps_tracker.codec import (  # noqa: E402
    CODEC_8,
    CODEC_8_EXT,
    crc16_ibm,
    parse_avl_data,
    parse_imei_message,
)


def test_crc16_known_answer():
    """CRC-16/IBM(ARC) の既知値: "123456789" -> 0xBB3D"""
    assert crc16_ibm(b"123456789") == 0xBB3D


def test_parse_imei_message():
    """IMEIハンドシェイクメッセージを正しく解析できる"""
    imei = "350612078123456"
    msg = struct.pack(">H", len(imei)) + imei.encode("ascii")
    assert parse_imei_message(msg) == imei


def test_codec8_official_example():
    """Teltonika公式のCodec 8サンプルパケットを検証する"""
    packet = bytes.fromhex(
        "000000000000003608010000016B40D8EA3001000000000000000000000000"
        "0000000105021503010101425E0F01F10000601A014E000000000000000001"
        "0000C7CF"
    )
    preamble, data_len = struct.unpack(">II", packet[:8])
    assert preamble == 0
    data = packet[8:8 + data_len]
    crc = struct.unpack(">I", packet[8 + data_len:8 + data_len + 4])[0] & 0xFFFF

    assert crc16_ibm(data) == crc == 0xC7CF

    codec_id, records = parse_avl_data(data)
    assert codec_id == CODEC_8
    assert len(records) == 1
    # このサンプルは測位なし（座標0,0・衛星0）のレコード
    rec = records[0]
    assert rec.latitude == 0.0
    assert rec.longitude == 0.0
    assert rec.has_fix is False


def test_codec8_extended_with_fix():
    """Codec 8 Extended のレコード（実座標あり）を解析できる"""
    timestamp_ms = 1700000000000
    lon_raw = round(139.7671 * 1e7)
    lat_raw = round(35.6812 * 1e7)
    record = (
        struct.pack(">Q", timestamp_ms)
        + struct.pack(">B", 1)              # priority
        + struct.pack(">ii", lon_raw, lat_raw)
        + struct.pack(">hH", 10, 90)        # altitude, angle
        + struct.pack(">B", 12)             # satellites
        + struct.pack(">H", 60)             # speed km/h
        + struct.pack(">H", 0)              # event IO ID (2バイト)
        + struct.pack(">H", 0)              # 全IO数 (2バイト)
        + struct.pack(">H", 0) * 5          # N1/N2/N4/N8/NX 各カウント=0
    )
    data = bytes([CODEC_8_EXT, 1]) + record + bytes([1])

    codec_id, records = parse_avl_data(data)
    assert codec_id == CODEC_8_EXT
    assert len(records) == 1
    rec = records[0]
    assert abs(rec.latitude - 35.6812) < 1e-6
    assert abs(rec.longitude - 139.7671) < 1e-6
    assert rec.speed == 60
    assert rec.satellites == 12
    assert rec.has_fix is True


def test_codec8_multiple_records():
    """複数レコード（Codec 8・IO要素なし）を解析できる"""
    def make_record(lat, lon):
        return (
            struct.pack(">Q", 1700000000000)
            + struct.pack(">B", 0)
            + struct.pack(">ii", round(lon * 1e7), round(lat * 1e7))
            + struct.pack(">hH", 0, 0)
            + struct.pack(">B", 8)
            + struct.pack(">H", 40)
            + struct.pack(">B", 0)          # event IO ID (1バイト)
            + struct.pack(">B", 0)          # 全IO数 (1バイト)
            + struct.pack(">B", 0) * 4      # N1/N2/N4/N8 各カウント=0
        )

    data = (
        bytes([CODEC_8, 2])
        + make_record(35.0, 139.0)
        + make_record(36.0, 140.0)
        + bytes([2])
    )
    codec_id, records = parse_avl_data(data)
    assert codec_id == CODEC_8
    assert len(records) == 2
    assert abs(records[0].latitude - 35.0) < 1e-6
    assert abs(records[1].longitude - 140.0) < 1e-6


def run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {test.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {test.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if run_all() else 0)
