"""
アプリ内スケジューラ（cron不要）

アプリ起動時に常駐スレッドを1本立ち上げ、一定間隔で
「Gmail / ChatWork の受信 → 指定ストレージへ自動保存」を実行する。

- cron / systemd を使わないため、デプロイするだけで自動取得が回る。
- 複数の gunicorn ワーカーが同時に動いても、DB(T_スケジューラ状態)への
  条件付きUPDATEで実行権を1つに絞り、重複実行を防ぐ。
  （ai-app-studio の db_backup スケジューラと同じ方式）

設定（環境変数・任意）:
  AUTO_SYNC_ENABLED           : '0' で無効化（既定: 有効）
  AUTO_SYNC_INTERVAL_MINUTES  : 実行間隔（分）。既定 5
"""
import os
import json
import time
import threading
import logging
from datetime import datetime, timedelta

from sqlalchemy import or_

from app.db import SessionLocal
from app.models_integrations import TSchedulerState

logger = logging.getLogger(__name__)

JOB_NAME = 'integrations_sync'
_CHECK_INTERVAL_SEC = 60      # 60秒ごとに「実行すべきか」を確認
_STARTUP_DELAY_SEC = 30       # 起動直後の混雑を避けて少し待つ

_started = False
_start_lock = threading.Lock()


def _enabled() -> bool:
    return os.environ.get('AUTO_SYNC_ENABLED', '1') in ('1', 'true', 'True', 'yes', 'on')


def _interval_minutes() -> int:
    try:
        return max(1, int(os.environ.get('AUTO_SYNC_INTERVAL_MINUTES', '5')))
    except Exception:
        return 5


def _ensure_row(db):
    """スケジューラ状態の行が無ければ作る（初回のみ）。"""
    row = db.query(TSchedulerState).filter(TSchedulerState.job_name == JOB_NAME).first()
    if row:
        return
    try:
        db.add(TSchedulerState(job_name=JOB_NAME, last_run_at=None))
        db.commit()
    except Exception:
        db.rollback()  # 別ワーカーが同時に作った場合など（unique制約）


def _claim(db, interval_min: int) -> bool:
    """前回実行から interval_min 経過していれば last_run_at を進めて実行権を得る。

    条件付き UPDATE の rowcount==1 になったワーカーだけが True を得る（＝実行する）。
    複数ワーカーが同時に来ても、行ロックにより1つだけが成功する。
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=interval_min)
    updated = (
        db.query(TSchedulerState)
        .filter(
            TSchedulerState.job_name == JOB_NAME,
            or_(TSchedulerState.last_run_at.is_(None),
                TSchedulerState.last_run_at <= cutoff),
        )
        .update({TSchedulerState.last_run_at: now}, synchronize_session=False)
    )
    db.commit()
    return updated == 1


def _record_result(status: str, detail: dict):
    db = SessionLocal()
    try:
        row = db.query(TSchedulerState).filter(TSchedulerState.job_name == JOB_NAME).first()
        if row:
            row.last_finished_at = datetime.utcnow()
            row.last_status = status
            try:
                row.last_detail = json.dumps(detail, ensure_ascii=False, default=str)[:2000]
            except Exception:
                row.last_detail = str(detail)[:2000]
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def run_sync_once() -> dict:
    """1回分の受信同期（ChatWork + Gmail）。手動呼び出しにも使える。"""
    detail = {}
    status = 'ok'
    try:
        from app.services.chatwork_sync import sync_all_tenants as cw_sync
        detail['chatwork'] = cw_sync()
    except Exception as e:  # noqa: BLE001
        status = 'error'
        detail['chatwork_error'] = str(e)
        logger.exception('scheduler: chatwork sync failed')
    try:
        from app.services.gmail_sync import sync_all_tenants as gm_sync
        detail['gmail'] = gm_sync()
    except Exception as e:  # noqa: BLE001
        status = 'error'
        detail['gmail_error'] = str(e)
        logger.exception('scheduler: gmail sync failed')
    _record_result(status, detail)
    return detail


def _loop():
    time.sleep(_STARTUP_DELAY_SEC)
    while True:
        try:
            if _enabled():
                interval = _interval_minutes()
                db = SessionLocal()
                try:
                    _ensure_row(db)
                    won = _claim(db, interval)
                finally:
                    db.close()
                if won:
                    logger.info('scheduler: 受信同期を実行します')
                    run_sync_once()
        except Exception:  # noqa: BLE001
            logger.exception('scheduler: ループでエラー')
        time.sleep(_CHECK_INTERVAL_SEC)


def get_state() -> dict:
    """スケジューラの稼働状況を返す（画面表示用）。"""
    info = {'enabled': _enabled(), 'interval_minutes': _interval_minutes(),
            'last_finished_at': None, 'last_status': None}
    try:
        db = SessionLocal()
        try:
            row = db.query(TSchedulerState).filter(
                TSchedulerState.job_name == JOB_NAME).first()
            if row:
                info['last_finished_at'] = row.last_finished_at
                info['last_status'] = row.last_status
        finally:
            db.close()
    except Exception:
        pass
    return info


def start_scheduler():
    """アプリ起動時に1回呼ぶ。プロセス毎に1度だけスレッドを起動する。"""
    global _started
    if not _enabled():
        logger.info('scheduler: AUTO_SYNC_ENABLED=0 のため起動しません')
        return
    with _start_lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, name='integrations-scheduler', daemon=True).start()
    logger.info('scheduler: アプリ内スケジューラを起動しました（間隔 %d分）', _interval_minutes())
