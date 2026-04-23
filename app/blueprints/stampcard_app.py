# -*- coding: utf-8 -*-
"""
スタンプカード管理 Blueprint
survey-system-app から移植
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from ..utils.db import get_db_connection, _sql
from ..utils.decorators import require_roles, ROLES

bp = Blueprint('stampcard_app', __name__, url_prefix='/apps/stampcard')


def _get_admin_name():
    return session.get('user_name', '管理者')


# ===== 設定 =====
@bp.route('/store/<int:store_id>/settings', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def settings(store_id):
    """スタンプカード設定（複数特典対応）"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store = cur.fetchone()
    if not store:
        conn.close()
        flash('店舗が見つかりません', 'error')
        return redirect(url_for('admin.store_info'))
    store_name = store[0]

    if request.method == 'POST':
        card_title = request.form.get('card_title', 'スタンプカード')
        enabled = 1 if request.form.get('enabled') == 'on' else 0
        use_multi_rewards = int(request.form.get('use_multi_rewards', 0))

        try:
            cur.execute(_sql(conn, 'SELECT id FROM "T_店舗_スタンプカード設定" WHERE store_id = %s'), (store_id,))
            existing = cur.fetchone()
            if existing:
                cur.execute(_sql(conn, '''
                    UPDATE "T_店舗_スタンプカード設定"
                    SET card_title = %s, enabled = %s, use_multi_rewards = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE store_id = %s
                '''), (card_title, enabled, use_multi_rewards, store_id))
            else:
                cur.execute(_sql(conn, '''
                    INSERT INTO "T_店舗_スタンプカード設定"
                    (store_id, card_title, enabled, use_multi_rewards)
                    VALUES (%s, %s, %s, %s)
                '''), (store_id, card_title, enabled, use_multi_rewards))

            # 複数特典設定の処理
            if use_multi_rewards:
                # 既存特典を削除して再登録
                cur.execute(_sql(conn, 'DELETE FROM "T_特典設定" WHERE store_id = %s'), (store_id,))
                reward_names = request.form.getlist('reward_name[]')
                reward_stamps = request.form.getlist('reward_stamps[]')
                reward_repeatable = request.form.getlist('reward_repeatable[]')
                for i, (name, stamps) in enumerate(zip(reward_names, reward_stamps)):
                    if name.strip() and stamps:
                        repeatable = 1 if str(i) in reward_repeatable else 0
                        cur.execute(_sql(conn, '''
                            INSERT INTO "T_特典設定"
                            (store_id, required_stamps, reward_description, is_repeatable, display_order, enabled)
                            VALUES (%s, %s, %s, %s, %s, 1)
                        '''), (store_id, int(stamps), name.strip(), repeatable, i))
            else:
                required_stamps = int(request.form.get('required_stamps', 10))
                reward_description = request.form.get('reward_description', '')
                cur.execute(_sql(conn, '''
                    UPDATE "T_店舗_スタンプカード設定"
                    SET required_stamps = %s, reward_description = %s
                    WHERE store_id = %s
                '''), (required_stamps, reward_description, store_id))

            conn.commit()
            flash('スタンプカード設定を保存しました', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'設定の保存に失敗しました: {str(e)}', 'error')
        finally:
            conn.close()

        return redirect(url_for('stampcard_app.settings', store_id=store_id))

    # GET
    cur.execute(_sql(conn, '''
        SELECT card_title, required_stamps, reward_description, enabled, use_multi_rewards
        FROM "T_店舗_スタンプカード設定" WHERE store_id = %s
    '''), (store_id,))
    settings_row = cur.fetchone()

    cur.execute(_sql(conn, '''
        SELECT id, required_stamps, reward_description, is_repeatable, display_order
        FROM "T_特典設定" WHERE store_id = %s AND enabled = 1
        ORDER BY display_order
    '''), (store_id,))
    rewards = cur.fetchall()
    conn.close()

    return render_template('stampcard_app_settings.html',
                           store_id=store_id,
                           store_name=store_name,
                           settings=settings_row,
                           rewards=rewards)


# ===== 顧客一覧 =====
@bp.route('/store/<int:store_id>/customers')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def customers(store_id):
    """顧客一覧"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store = cur.fetchone()
    store_name = store[0] if store else ''

    search = request.args.get('search', '').strip()
    if search:
        cur.execute(_sql(conn, '''
            SELECT c.id, c.name, c.phone, c.email, c.created_at,
                   COALESCE(sc.current_stamps, 0), COALESCE(sc.total_stamps, 0), COALESCE(sc.rewards_used, 0)
            FROM "T_顧客" c
            LEFT JOIN "T_スタンプカード" sc ON c.id = sc.customer_id AND sc.store_id = %s
            WHERE c.store_id = %s AND (c.name LIKE %s OR c.phone LIKE %s OR c.email LIKE %s)
            ORDER BY c.created_at DESC
        '''), (store_id, store_id, f'%{search}%', f'%{search}%', f'%{search}%'))
    else:
        cur.execute(_sql(conn, '''
            SELECT c.id, c.name, c.phone, c.email, c.created_at,
                   COALESCE(sc.current_stamps, 0), COALESCE(sc.total_stamps, 0), COALESCE(sc.rewards_used, 0)
            FROM "T_顧客" c
            LEFT JOIN "T_スタンプカード" sc ON c.id = sc.customer_id AND sc.store_id = %s
            WHERE c.store_id = %s
            ORDER BY c.created_at DESC
        '''), (store_id, store_id))

    customers_data = cur.fetchall()
    conn.close()

    return render_template('stampcard_app_customers.html',
                           store_id=store_id,
                           store_name=store_name,
                           customers=customers_data,
                           search=search)


# ===== 顧客詳細 =====
@bp.route('/store/<int:store_id>/customers/<int:customer_id>')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def customer_detail(store_id, customer_id):
    """顧客詳細"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store = cur.fetchone()
    store_name = store[0] if store else ''

    cur.execute(_sql(conn, 'SELECT id, name, phone, email, created_at FROM "T_顧客" WHERE id = %s AND store_id = %s'), (customer_id, store_id))
    customer = cur.fetchone()
    if not customer:
        conn.close()
        flash('顧客が見つかりません', 'error')
        return redirect(url_for('stampcard_app.customers', store_id=store_id))

    cur.execute(_sql(conn, '''
        SELECT id, current_stamps, total_stamps, rewards_used, updated_at
        FROM "T_スタンプカード" WHERE customer_id = %s AND store_id = %s
    '''), (customer_id, store_id))
    card = cur.fetchone()

    cur.execute(_sql(conn, '''
        SELECT id, stamps_added, action_type, note, created_by, created_at
        FROM "T_スタンプ履歴" WHERE customer_id = %s AND store_id = %s
        ORDER BY created_at DESC LIMIT 50
    '''), (customer_id, store_id))
    history = cur.fetchall()

    cur.execute(_sql(conn, '''
        SELECT card_title, required_stamps, reward_description, use_multi_rewards
        FROM "T_店舗_スタンプカード設定" WHERE store_id = %s
    '''), (store_id,))
    card_settings = cur.fetchone()

    conn.close()

    return render_template('stampcard_app_customer_detail.html',
                           store_id=store_id,
                           store_name=store_name,
                           customer=customer,
                           card=card,
                           history=history,
                           card_settings=card_settings)


# ===== スタンプ追加 =====
@bp.route('/store/<int:store_id>/customers/<int:customer_id>/add_stamp', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def add_stamp(store_id, customer_id):
    """スタンプを追加"""
    stamps_to_add = int(request.form.get('stamps_to_add', 1))
    note = request.form.get('note', '')
    admin_name = _get_admin_name()

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(_sql(conn, 'SELECT id, current_stamps, total_stamps FROM "T_スタンプカード" WHERE customer_id = %s AND store_id = %s'), (customer_id, store_id))
        card = cur.fetchone()

        if card:
            card_id = card[0]
            new_current = card[1] + stamps_to_add
            new_total = card[2] + stamps_to_add

            # 必要スタンプ数を確認してリセット
            cur.execute(_sql(conn, 'SELECT required_stamps FROM "T_店舗_スタンプカード設定" WHERE store_id = %s'), (store_id,))
            settings_row = cur.fetchone()
            required = settings_row[0] if settings_row else 10

            rewards_earned = new_current // required
            if rewards_earned > 0:
                new_current = new_current % required
                cur.execute(_sql(conn, '''
                    UPDATE "T_スタンプカード"
                    SET current_stamps = %s, total_stamps = %s,
                        rewards_used = rewards_used + %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                '''), (new_current, new_total, rewards_earned, card_id))
            else:
                cur.execute(_sql(conn, '''
                    UPDATE "T_スタンプカード"
                    SET current_stamps = %s, total_stamps = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                '''), (new_current, new_total, card_id))
        else:
            cur.execute(_sql(conn, '''
                INSERT INTO "T_スタンプカード" (customer_id, store_id, current_stamps, total_stamps)
                VALUES (%s, %s, %s, %s)
            '''), (customer_id, store_id, stamps_to_add, stamps_to_add))
            card_id = cur.fetchone()[0] if False else None
            cur.execute(_sql(conn, 'SELECT id FROM "T_スタンプカード" WHERE customer_id = %s AND store_id = %s'), (customer_id, store_id))
            card_id = cur.fetchone()[0]

        cur.execute(_sql(conn, '''
            INSERT INTO "T_スタンプ履歴" (card_id, customer_id, store_id, stamps_added, action_type, note, created_by)
            VALUES (%s, %s, %s, %s, 'add', %s, %s)
        '''), (card_id, customer_id, store_id, stamps_to_add, note, admin_name))

        conn.commit()
        flash(f'スタンプを{stamps_to_add}個追加しました', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'スタンプの追加に失敗しました: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('stampcard_app.customer_detail', store_id=store_id, customer_id=customer_id))


# ===== スタンプ削除 =====
@bp.route('/store/<int:store_id>/customers/<int:customer_id>/remove_stamp', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def remove_stamp(store_id, customer_id):
    """スタンプを削除"""
    stamps_to_remove = int(request.form.get('stamps_to_remove', 1))
    note = request.form.get('note', '')
    admin_name = _get_admin_name()

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(_sql(conn, 'SELECT id, current_stamps FROM "T_スタンプカード" WHERE customer_id = %s AND store_id = %s'), (customer_id, store_id))
        card = cur.fetchone()
        if not card:
            flash('スタンプカードが見つかりません', 'error')
            conn.close()
            return redirect(url_for('stampcard_app.customer_detail', store_id=store_id, customer_id=customer_id))

        card_id = card[0]
        new_current = max(0, card[1] - stamps_to_remove)
        cur.execute(_sql(conn, '''
            UPDATE "T_スタンプカード"
            SET current_stamps = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s
        '''), (new_current, card_id))

        cur.execute(_sql(conn, '''
            INSERT INTO "T_スタンプ履歴" (card_id, customer_id, store_id, stamps_added, action_type, note, created_by)
            VALUES (%s, %s, %s, %s, 'remove', %s, %s)
        '''), (card_id, customer_id, store_id, -stamps_to_remove, note, admin_name))

        conn.commit()
        flash(f'スタンプを{stamps_to_remove}個削除しました', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'スタンプの削除に失敗しました: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('stampcard_app.customer_detail', store_id=store_id, customer_id=customer_id))


# ===== 統計 =====
@bp.route('/store/<int:store_id>/stats')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def stats(store_id):
    """統計・レポート"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store = cur.fetchone()
    if not store:
        conn.close()
        flash('店舗が見つかりません', 'error')
        return redirect(url_for('admin.store_info'))
    store_name = store[0]

    cur.execute(_sql(conn, 'SELECT COUNT(*) FROM "T_顧客" WHERE store_id = %s'), (store_id,))
    total_customers = cur.fetchone()[0]

    cur.execute(_sql(conn, '''
        SELECT COUNT(*) FROM "T_顧客"
        WHERE store_id = %s AND last_login >= CURRENT_TIMESTAMP - INTERVAL '30 days'
    '''), (store_id,))
    active_customers = cur.fetchone()[0]

    cur.execute(_sql(conn, 'SELECT COALESCE(SUM(total_stamps), 0) FROM "T_スタンプカード" WHERE store_id = %s'), (store_id,))
    total_stamps = cur.fetchone()[0]

    cur.execute(_sql(conn, 'SELECT COALESCE(SUM(rewards_used), 0) FROM "T_スタンプカード" WHERE store_id = %s'), (store_id,))
    total_rewards = cur.fetchone()[0]

    cur.execute(_sql(conn, '''
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM "T_スタンプ履歴"
        WHERE store_id = %s AND action_type = 'add'
        AND created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
        GROUP BY DATE(created_at) ORDER BY date ASC
    '''), (store_id,))
    stamp_trend = cur.fetchall()

    cur.execute(_sql(conn, '''
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM "T_特典利用履歴"
        WHERE store_id = %s AND created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
        GROUP BY DATE(created_at) ORDER BY date ASC
    '''), (store_id,))
    reward_trend = cur.fetchall()
    conn.close()

    return render_template('stampcard_app_stats.html',
                           store_id=store_id,
                           store_name=store_name,
                           stats={
                               'total_customers': total_customers,
                               'active_customers': active_customers,
                               'total_stamps': total_stamps,
                               'total_rewards': total_rewards
                           },
                           stamp_trend=stamp_trend,
                           reward_trend=reward_trend)
