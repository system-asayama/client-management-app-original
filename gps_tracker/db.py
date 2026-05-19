# -*- coding: utf-8 -*-
"""GPS受信サービス用のDBアクセス

メインのFlaskアプリとは独立して動くため、DATABASE_URL から専用の
SQLAlchemyエンジンを生成する（Flaskアプリのimportを避ける）。
"""
import os

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 環境変数が設定されていません")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    future=True,
)


def get_truck_by_imei(imei: str):
    """IMEIに紐づくトラックを返す（id, tenant_id）。無ければ None。"""
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT id, tenant_id FROM trucks WHERE gps_imei = :imei LIMIT 1"),
            {"imei": imei},
        ).fetchone()


def get_active_operation(truck_id: int):
    """トラックの進行中の運行を返す（id, driver_id, tenant_id）。無ければ None。

    status が finished / off 以外で、最も新しく開始された運行を採用する。
    """
    with engine.connect() as conn:
        return conn.execute(
            text(
                """
                SELECT id, driver_id, tenant_id
                FROM truck_operations
                WHERE truck_id = :truck_id
                  AND status NOT IN ('finished', 'off')
                ORDER BY start_time DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"truck_id": truck_id},
        ).fetchone()


def insert_locations(rows: list) -> int:
    """位置情報をまとめて T_トラック運行位置履歴 に保存する。

    rows は dict のリスト。source は 'device' 固定。
    """
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO "T_トラック運行位置履歴"
                    (operation_id, driver_id, truck_id, tenant_id,
                     latitude, longitude, accuracy, speed, source, recorded_at)
                VALUES
                    (:operation_id, :driver_id, :truck_id, :tenant_id,
                     :latitude, :longitude, :accuracy, :speed, 'device', :recorded_at)
                """
            ),
            rows,
        )
    return len(rows)
