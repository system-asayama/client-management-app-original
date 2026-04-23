# -*- coding: utf-8 -*-
"""
予約管理 Blueprint
survey-system-app から移植
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime, timedelta
import calendar as cal_module
from ..utils.db import get_db_connection, _sql
from ..utils.decorators import require_roles, ROLES

bp = Blueprint('reservation_app', __name__, url_prefix='/apps/reservation')


def _get_admin_name():
    return session.get('user_name', '管理者')


# ===== 予約設定 =====
@bp.route('/store/<int:store_id>/settings', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def settings(store_id):
    """予約設定画面"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    if not store_row:
        conn.close()
        flash('店舗が見つかりません', 'error')
        return redirect(url_for('admin.store_info'))

    class StoreObj:
        def __init__(self, row):
            self.id = store_id
            self.name = row[0]

    store = StoreObj(store_row)

    if request.method == 'POST':
        data = request.form
        cur.execute(_sql(conn, 'SELECT id FROM "T_店舗_予約設定" WHERE store_id = %s'), (store_id,))
        existing = cur.fetchone()
        if existing:
            cur.execute(_sql(conn, '''
                UPDATE "T_店舗_予約設定"
                SET 営業開始時刻 = %s, 営業終了時刻 = %s, 最終入店時刻 = %s,
                    予約単位_分 = %s, 予約受付日数 = %s, 定休日 = %s,
                    予約受付可否 = %s, 特記事項 = %s, updated_at = CURRENT_TIMESTAMP
                WHERE store_id = %s
            '''), (
                data.get('営業開始時刻', '11:00'),
                data.get('営業終了時刻', '22:00'),
                data.get('最終入店時刻', '21:00'),
                int(data.get('予約単位_分', 30)),
                int(data.get('予約受付日数', 60)),
                data.get('定休日', ''),
                1 if data.get('予約受付可否') == 'on' else 0,
                data.get('特記事項', ''),
                store_id
            ))
        else:
            cur.execute(_sql(conn, '''
                INSERT INTO "T_店舗_予約設定"
                (store_id, 営業開始時刻, 営業終了時刻, 最終入店時刻,
                 予約単位_分, 予約受付日数, 定休日, 予約受付可否, 特記事項)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            '''), (
                store_id,
                data.get('営業開始時刻', '11:00'),
                data.get('営業終了時刻', '22:00'),
                data.get('最終入店時刻', '21:00'),
                int(data.get('予約単位_分', 30)),
                int(data.get('予約受付日数', 60)),
                data.get('定休日', ''),
                1 if data.get('予約受付可否') == 'on' else 0,
                data.get('特記事項', '')
            ))
        conn.commit()
        conn.close()
        flash('予約設定を保存しました', 'success')
        return redirect(url_for('reservation_app.settings', store_id=store_id))

    cur.execute(_sql(conn, 'SELECT * FROM "T_店舗_予約設定" WHERE store_id = %s'), (store_id,))
    settings_row = cur.fetchone()

    cur.execute(_sql(conn, '''
        SELECT id, テーブル名, 座席数, テーブル数, 表示順序
        FROM "T_テーブル設定" WHERE store_id = %s ORDER BY 表示順序, 座席数
    '''), (store_id,))
    tables = cur.fetchall()
    conn.close()

    return render_template('reservation_app_settings.html',
                           store=store,
                           settings=settings_row,
                           tables=tables)


# ===== テーブル追加 =====
@bp.route('/store/<int:store_id>/tables/add', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def add_table(store_id):
    data = request.form
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(_sql(conn, '''
            INSERT INTO "T_テーブル設定" (store_id, テーブル名, 座席数, テーブル数, 表示順序, 有効)
            VALUES (%s, %s, %s, %s, %s, 1)
        '''), (
            store_id,
            data.get('テーブル名'),
            int(data.get('座席数', 2)),
            int(data.get('テーブル数', 1)),
            int(data.get('表示順序', 0))
        ))
        conn.commit()
        flash('テーブル設定を追加しました', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'追加に失敗しました: {str(e)}', 'error')
    finally:
        conn.close()
    return redirect(url_for('reservation_app.settings', store_id=store_id))


# ===== テーブル削除 =====
@bp.route('/store/<int:store_id>/tables/<int:table_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def delete_table(store_id, table_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(_sql(conn, 'DELETE FROM "T_テーブル設定" WHERE id = %s AND store_id = %s'), (table_id, store_id))
        conn.commit()
        flash('テーブル設定を削除しました', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'削除に失敗しました: {str(e)}', 'error')
    finally:
        conn.close()
    return redirect(url_for('reservation_app.settings', store_id=store_id))


# ===== 予約一覧 =====
@bp.route('/store/<int:store_id>/list')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def reservation_list(store_id):
    """予約一覧"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    store_name = store_row[0] if store_row else ''

    class StoreObj:
        def __init__(self, name, sid):
            self.id = sid
            self.name = name

    store = StoreObj(store_name, store_id)

    filter_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))

    cur.execute(_sql(conn, '''
        SELECT id, 予約者名, 人数, 予約日, 予約時刻, ステータス, 電話番号, メモ, created_at
        FROM "T_予約" WHERE store_id = %s AND 予約日 = %s ORDER BY 予約時刻
    '''), (store_id, filter_date))
    reservations = cur.fetchall()

    cur.execute(_sql(conn, '''
        SELECT COUNT(*) as total_count,
               COALESCE(SUM(人数), 0) as total_guests,
               COUNT(CASE WHEN ステータス = 'confirmed' THEN 1 END) as confirmed_count,
               COUNT(CASE WHEN ステータス = 'cancelled' THEN 1 END) as cancelled_count
        FROM "T_予約" WHERE store_id = %s AND 予約日 = %s
    '''), (store_id, filter_date))
    stats = cur.fetchone()
    conn.close()

    return render_template('reservation_app_list.html',
                           store=store,
                           reservations=reservations,
                           stats=stats,
                           filter_date=filter_date)


# ===== 予約キャンセル =====
@bp.route('/store/<int:store_id>/<int:reservation_id>/cancel', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def cancel_reservation(store_id, reservation_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(_sql(conn, '''
            UPDATE "T_予約"
            SET ステータス = 'cancelled', cancelled_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND store_id = %s
        '''), (reservation_id, store_id))
        conn.commit()
        flash('予約をキャンセルしました', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'キャンセルに失敗しました: {str(e)}', 'error')
    finally:
        conn.close()

    filter_date = request.form.get('date', datetime.now().strftime('%Y-%m-%d'))
    return redirect(url_for('reservation_app.reservation_list', store_id=store_id, date=filter_date))


# ===== 予約編集 =====
@bp.route('/store/<int:store_id>/<int:reservation_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def edit_reservation(store_id, reservation_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    store_name = store_row[0] if store_row else ''

    class StoreObj:
        def __init__(self, name, sid):
            self.id = sid
            self.name = name

    store = StoreObj(store_name, store_id)

    if request.method == 'POST':
        data = request.form
        try:
            cur.execute(_sql(conn, '''
                UPDATE "T_予約"
                SET 予約者名 = %s, 人数 = %s, 予約日 = %s, 予約時刻 = %s,
                    電話番号 = %s, メモ = %s, ステータス = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND store_id = %s
            '''), (
                data.get('予約者名'),
                int(data.get('人数', 1)),
                data.get('予約日'),
                data.get('予約時刻'),
                data.get('電話番号', ''),
                data.get('メモ', ''),
                data.get('ステータス', 'confirmed'),
                reservation_id,
                store_id
            ))
            conn.commit()
            flash('予約を更新しました', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'更新に失敗しました: {str(e)}', 'error')
        finally:
            conn.close()
        return redirect(url_for('reservation_app.reservation_list',
                                store_id=store_id,
                                date=data.get('予約日', datetime.now().strftime('%Y-%m-%d'))))

    cur.execute(_sql(conn, '''
        SELECT id, 予約者名, 人数, 予約日, 予約時刻, ステータス, 電話番号, メモ
        FROM "T_予約" WHERE id = %s AND store_id = %s
    '''), (reservation_id, store_id))
    reservation = cur.fetchone()
    conn.close()

    if not reservation:
        flash('予約が見つかりません', 'error')
        return redirect(url_for('reservation_app.reservation_list', store_id=store_id))

    return render_template('reservation_app_edit.html',
                           store=store,
                           reservation=reservation)


# ===== カレンダー =====
@bp.route('/store/<int:store_id>/calendar')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def calendar(store_id):
    """予約カレンダー"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    store_name = store_row[0] if store_row else ''

    class StoreObj:
        def __init__(self, name, sid):
            self.id = sid
            self.name = name

    store = StoreObj(store_name, store_id)

    try:
        year = int(request.args.get('year', datetime.now().year))
        month = int(request.args.get('month', datetime.now().month))
    except (ValueError, TypeError):
        year = datetime.now().year
        month = datetime.now().month

    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)

    cur.execute(_sql(conn, '''
        SELECT 予約日, COUNT(*) as count, COALESCE(SUM(人数), 0) as total_guests
        FROM "T_予約"
        WHERE store_id = %s AND 予約日 >= %s AND 予約日 <= %s AND ステータス != 'cancelled'
        GROUP BY 予約日
    '''), (store_id, first_day.strftime('%Y-%m-%d'), last_day.strftime('%Y-%m-%d')))

    reservations_by_date = {}
    for row in cur.fetchall():
        reservations_by_date[str(row[0])] = {'count': row[1], 'total_guests': row[2]}
    conn.close()

    cal = cal_module.monthcalendar(year, month)
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return render_template('reservation_app_calendar.html',
                           store=store,
                           year=year,
                           month=month,
                           calendar=cal,
                           reservations_by_date=reservations_by_date,
                           prev_year=prev_year,
                           prev_month=prev_month,
                           next_year=next_year,
                           next_month=next_month)


# ===== 予約フォーム（顧客向け） =====
@bp.route('/store/<int:store_id>/book', methods=['GET', 'POST'])
def book(store_id):
    """予約フォーム（顧客向け）"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    if not store_row:
        conn.close()
        return '店舗が見つかりません', 404
    store_name = store_row[0]

    cur.execute(_sql(conn, '''
        SELECT 営業開始時刻, 営業終了時刻, 最終入店時刻, 予約単位_分, 予約受付日数, 定休日, 予約受付可否, 特記事項
        FROM "T_店舗_予約設定" WHERE store_id = %s
    '''), (store_id,))
    settings_row = cur.fetchone()

    if request.method == 'POST':
        data = request.form
        try:
            cur.execute(_sql(conn, '''
                INSERT INTO "T_予約"
                (store_id, 予約者名, 人数, 予約日, 予約時刻, 電話番号, メモ, ステータス)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmed')
            '''), (
                store_id,
                data.get('予約者名'),
                int(data.get('人数', 1)),
                data.get('予約日'),
                data.get('予約時刻'),
                data.get('電話番号', ''),
                data.get('メモ', '')
            ))
            conn.commit()
            conn.close()
            return render_template('reservation_app_confirmation.html',
                                   store_name=store_name,
                                   reservation_data=data)
        except Exception as e:
            conn.rollback()
            conn.close()
            flash(f'予約に失敗しました: {str(e)}', 'error')
            return redirect(url_for('reservation_app.book', store_id=store_id))

    conn.close()
    return render_template('reservation_app_form.html',
                           store_id=store_id,
                           store_name=store_name,
                           settings=settings_row)
