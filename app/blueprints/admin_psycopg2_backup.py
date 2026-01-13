# -*- coding: utf-8 -*-
"""
管理者ダッシュボード
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from ..utils import require_roles, ROLES, get_db_connection
from ..utils.db import _sql
from werkzeug.security import generate_password_hash

bp = Blueprint('admin', __name__, url_prefix='/admin')

# 利用可能なアプリの定義
AVAILABLE_APPS = []


@bp.route('/')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def dashboard():
    """管理者ダッシュボード"""
    # 店舗で有効なアプリを取得
    store_id = session.get('store_id')
    tenant_id = session.get('tenant_id')
    enabled_apps = []
    
    if store_id:
        conn = get_db_connection()
        cur = conn.cursor()
        
        for app in AVAILABLE_APPS:
            if app['scope'] == 'store':
                cur.execute(_sql(conn, '''
                    SELECT enabled FROM "T_店舗アプリ設定"
                    WHERE store_id = %s AND app_name = %s
                '''), (store_id, app['name']))
                row = cur.fetchone()
                enabled = row[0] if row else 1
                
                if enabled:
                    enabled_apps.append(app)
        
        conn.close()
    
    return render_template('admin_dashboard.html', tenant_id=tenant_id, apps=enabled_apps)


@bp.route('/store_info')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_info():
    """店舗情報表示"""
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # セッションにtenant_idがない場合、管理者情報から取得
    if not tenant_id:
        cur.execute(_sql(conn, 'SELECT tenant_id FROM "T_管理者" WHERE id = %s'), (user_id,))
        admin_row = cur.fetchone()
        
        if not admin_row or not admin_row[0]:
            flash('テナント情報が見つかりません', 'error')
            conn.close()
            return redirect(url_for('admin.dashboard'))
        
        tenant_id = admin_row[0]
    
    # テナント情報を取得
    cur.execute(_sql(conn, 'SELECT id, 名称, slug, created_at FROM "T_テナント" WHERE id = %s'), (tenant_id,))
    tenant_row = cur.fetchone()
    
    if not tenant_row:
        flash('テナント情報が見つかりません', 'error')
        conn.close()
        return redirect(url_for('admin.dashboard'))
    
    tenant = {
        'id': tenant_row[0],
        '名称': tenant_row[1],
        'slug': tenant_row[2],
        'created_at': tenant_row[3]
    }
    
    # 店舗一覧を取得
    cur.execute(_sql(conn, 'SELECT id, 名称, slug, created_at FROM "T_店舗" WHERE tenant_id = %s ORDER BY id'), (tenant_id,))
    stores = []
    for row in cur.fetchall():
        stores.append({
            'id': row[0],
            '名称': row[1],
            'slug': row[2],
            'created_at': row[3]
        })
    
    conn.close()
    
    return render_template('admin_store_info.html', tenant=tenant, stores=stores)


@bp.route('/store/<int:store_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_edit(store_id):
    """店舗編集"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        name = request.form.get('名称', '').strip()
        slug = request.form.get('slug', '').strip()
        openai_api_key = request.form.get('openai_api_key', '').strip()
        
        if not name or not slug:
            flash('名称とslugは必須です', 'error')
        else:
            # 重複チェック（自分以外）
            cur.execute(_sql(conn, 'SELECT id FROM "T_店舗" WHERE tenant_id = %s AND slug = %s AND id != %s'), 
                       (tenant_id, slug, store_id))
            if cur.fetchone():
                flash(f'slug "{slug}" は既に使用されています', 'error')
            else:
                cur.execute(_sql(conn, '''
                    UPDATE "T_店舗"
                    SET 名称 = %s, slug = %s, openai_api_key = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND tenant_id = %s
                '''), (name, slug, openai_api_key if openai_api_key else None, store_id, tenant_id))
                conn.commit()
                flash('店舗情報を更新しました', 'success')
                conn.close()
                return redirect(url_for('admin.store_info'))
    
    # GETリクエスト：店舗情報を取得
    cur.execute(_sql(conn, '''
        SELECT id, 名称, slug, openai_api_key
        FROM "T_店舗"
        WHERE id = %s AND tenant_id = %s
    '''), (store_id, tenant_id))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        flash('店舗が見つかりません', 'error')
        return redirect(url_for('admin.store_info'))
    
    store = {'id': row[0], '名称': row[1], 'slug': row[2], 'openai_api_key': row[3] if len(row) > 3 else None}
    return render_template('admin_store_edit.html', store=store, back_url=url_for('admin.store_info'))


@bp.route('/store/<int:store_id>/delete', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_delete(store_id):
    """店舗削除"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 店舗情報を取得
    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s AND tenant_id = %s'),
               (store_id, tenant_id))
    row = cur.fetchone()
    
    if not row:
        flash('店舗が見つかりません', 'error')
    else:
        cur.execute(_sql(conn, 'DELETE FROM "T_店舗" WHERE id = %s'), (store_id,))
        conn.commit()
        flash(f'{row[0]} を削除しました', 'success')
    
    conn.close()
    return redirect(url_for('admin.store_info'))


@bp.route('/console')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def console():
    """管理者コンソール"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 従業員数を取得
    cur.execute(_sql(conn, 'SELECT COUNT(*) FROM "T_従業員" WHERE tenant_id = %s'),
               (tenant_id,))
    employee_count = cur.fetchone()[0]
    
    conn.close()
    
    return render_template('admin_console.html', employee_count=employee_count)


# ========================================
# 管理者管理
# ========================================

@bp.route('/admins')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admins():
    """管理者一覧"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # オーナー権限チェック
    cur.execute(_sql(conn, 'SELECT is_owner, can_manage_admins FROM "T_管理者" WHERE id = %s'), (user_id,))
    row = cur.fetchone()
    if not row or (row[0] != 1 and row[1] != 1):
        flash('管理者を管理する権限がありません', 'error')
        conn.close()
        return redirect(url_for('admin.dashboard'))
    
    is_owner = row[0] == 1
    
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, is_owner, can_manage_admins, active, created_at 
        FROM "T_管理者" 
        WHERE tenant_id = %s AND role = %s
        ORDER BY id
    '''), (tenant_id, ROLES["ADMIN"]))
    
    admins_list = []
    for row in cur.fetchall():
        admins_list.append({
            'id': row[0],
            'login_id': row[1],
            'name': row[2],
            'is_owner': row[3] == 1,
            'can_manage_admins': row[4] == 1,
            'active': row[5] == 1,
            'created_at': row[6]
        })
    conn.close()
    
    return render_template('admin_admins.html', admins=admins_list, is_owner=is_owner, current_user_id=user_id)


@bp.route('/admins/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_new():
    """管理者新規作成"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    
    # オーナー権限チェック
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT is_owner, can_manage_admins FROM "T_管理者" WHERE id = %s'), (user_id,))
    row = cur.fetchone()
    if not row or (row[0] != 1 and row[1] != 1):
        flash('管理者を管理する権限がありません', 'error')
        conn.close()
        return redirect(url_for('admin.dashboard'))
    conn.close()
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        is_owner = 1 if request.form.get('is_owner') else 0
        store_ids = request.form.getlist('store_ids')
        
        if not login_id or not name or not password:
            flash('全ての項目を入力してください', 'error')
        elif password != password_confirm:
            flash('パスワードが一致しません', 'error')
        elif not store_ids:
            flash('少なくとも1つの店舗を選択してください', 'error')
        else:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # 重複チェック
            cur.execute(_sql(conn, 'SELECT id FROM "T_管理者" WHERE login_id = %s'), (login_id,))
            if cur.fetchone():
                flash('このログインIDは既に使用されています', 'error')
                conn.close()
            else:
                ph = generate_password_hash(password)
                cur.execute(_sql(conn, '''
                    INSERT INTO "T_管理者" (login_id, name, email, password_hash, role, tenant_id, active, is_owner, can_manage_admins)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                '''), (login_id, name, email, ph, ROLES['ADMIN'], tenant_id, 1, is_owner, is_owner))
                admin_id = cur.fetchone()[0]
                
                # 店舗との関連付け
                for store_id in store_ids:
                    cur.execute(_sql(conn, '''
                        INSERT INTO "T_管理者_店舗" (admin_id, store_id)
                        VALUES (%s, %s)
                    '''), (admin_id, int(store_id)))
                
                conn.commit()
                conn.close()
                flash('管理者を作成しました', 'success')
                return redirect(url_for('admin.admins'))
    
    # 店舗一覧を取得
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT id, "名称" FROM "T_店舗" WHERE "テナントid" = %s AND "有効" = 1 ORDER BY id'), (tenant_id,))
    stores = [dict(zip(['id', '名称'], row)) for row in cur.fetchall()]
    conn.close()
    
    return render_template('admin_admin_new.html', back_url=url_for('admin.admins'), stores=stores)


@bp.route('/admins/<int:admin_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_delete(admin_id):
    """管理者削除"""
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # オーナー権限チェック
    cur.execute(_sql(conn, 'SELECT is_owner, can_manage_admins FROM "T_管理者" WHERE id = %s'), (user_id,))
    row = cur.fetchone()
    if not row or (row[0] != 1 and row[1] != 1):
        flash('管理者を管理する権限がありません', 'error')
        conn.close()
        return redirect(url_for('admin.dashboard'))
    
    # 自分自身の削除を防止
    if admin_id == user_id:
        flash('自分自身を削除することはできません', 'error')
        conn.close()
        return redirect(url_for('admin.admins'))
    
    # テナントIDの確認
    cur.execute(_sql(conn, 'SELECT name FROM "T_管理者" WHERE id = %s AND tenant_id = %s AND role = %s'),
               (admin_id, tenant_id, ROLES["ADMIN"]))
    row = cur.fetchone()
    
    if not row:
        flash('管理者が見つかりません', 'error')
    else:
        cur.execute(_sql(conn, 'DELETE FROM "T_管理者" WHERE id = %s'), (admin_id,))
        conn.commit()
        flash(f'{row[0]} を削除しました', 'success')
    
    conn.close()
    return redirect(url_for('admin.admins'))


@bp.route('/admins/<int:admin_id>/toggle_active', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_toggle_active(admin_id):
    """管理者の有効/無効を切り替え"""
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # オーナー権限チェック
    cur.execute(_sql(conn, 'SELECT is_owner, can_manage_admins FROM "T_管理者" WHERE id = %s'), (user_id,))
    row = cur.fetchone()
    if not row or (row[0] != 1 and row[1] != 1):
        flash('管理者を管理する権限がありません', 'error')
        conn.close()
        return redirect(url_for('admin.admins'))
    
    # 自分自身の切り替えを防止
    if admin_id == user_id:
        flash('自分自身の有効/無効を切り替えることはできません', 'error')
        conn.close()
        return redirect(url_for('admin.admins'))
    
    # 管理者が存在するか確認
    cur.execute(_sql(conn, 'SELECT name, active FROM "T_管理者" WHERE id = %s AND tenant_id = %s AND role = %s'), 
               (admin_id, tenant_id, ROLES["ADMIN"]))
    row = cur.fetchone()
    
    if not row:
        flash('管理者が見つかりません', 'error')
    else:
        name = row[0]
        current_active = row[1]
        new_active = 0 if current_active == 1 else 1
        
        cur.execute(_sql(conn, 'UPDATE "T_管理者" SET active = %s WHERE id = %s'), 
                   (new_active, admin_id))
        conn.commit()
        
        status_text = '有効' if new_active == 1 else '無効'
        flash(f'管理者 "{name}" を{status_text}にしました', 'success')
    
    conn.close()
    return redirect(url_for('admin.admins'))


@bp.route('/admins/<int:admin_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_edit(admin_id):
    """管理者編集"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # オーナー権限チェック
    cur.execute(_sql(conn, 'SELECT is_owner, can_manage_admins FROM "T_管理者" WHERE id = %s'), (user_id,))
    row = cur.fetchone()
    if not row or (row[0] != 1 and row[1] != 1):
        flash('管理者を編集する権限がありません', 'error')
        conn.close()
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        active = int(request.form.get('active', 1))
        
        if not login_id or not name:
            flash('ログインIDと氏名は必須です', 'error')
        elif password and password != password_confirm:
            flash('パスワードが一致しません', 'error')
        else:
            # 重複チェック（自分以外）
            cur.execute(_sql(conn, 'SELECT id FROM "T_管理者" WHERE login_id = %s AND id != %s'), (login_id, admin_id))
            if cur.fetchone():
                flash(f'ログインID "{login_id}" は既に使用されています', 'error')
            else:
                if password:
                    # パスワード変更あり
                    ph = generate_password_hash(password)
                    cur.execute(_sql(conn, '''
                        UPDATE "T_管理者"
                        SET login_id = %s, name = %s, email = %s, password_hash = %s, active = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND tenant_id = %s AND role = %s
                    '''), (login_id, name, email, ph, active, admin_id, tenant_id, ROLES["ADMIN"]))
                else:
                    # パスワード変更なし
                    cur.execute(_sql(conn, '''
                        UPDATE "T_管理者"
                        SET login_id = %s, name = %s, email = %s, active = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND tenant_id = %s AND role = %s
                    '''), (login_id, name, email, active, admin_id, tenant_id, ROLES["ADMIN"]))
                
                conn.commit()
                flash('管理者情報を更新しました', 'success')
                conn.close()
                return redirect(url_for('admin.admins'))
    
    # GETリクエスト：管理者情報を取得
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, email, active, is_owner, can_manage_admins
        FROM "T_管理者"
        WHERE id = %s AND tenant_id = %s AND role = %s
    '''), (admin_id, tenant_id, ROLES["ADMIN"]))
    row = cur.fetchone()
    
    if not row:
        conn.close()
        flash('管理者が見つかりません', 'error')
        return redirect(url_for('admin.admins'))
    
    admin = {
        'id': row[0],
        'login_id': row[1],
        'name': row[2],
        'email': row[3],
        'active': row[4],
        'is_owner': row[5],
        'can_manage_admins': row[6]
    }
    conn.close()
    
    return render_template('admin_admin_edit.html', admin=admin, back_url=url_for('admin.admins'))


@bp.route('/admins/<int:admin_id>/transfer_owner', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_transfer_owner(admin_id):
    """オーナー権限移譲"""
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 現在のユーザーがオーナーか確認
    cur.execute(_sql(conn, 'SELECT is_owner FROM "T_管理者" WHERE id = %s'), (user_id,))
    row = cur.fetchone()
    if not row or row[0] != 1:
        flash('オーナー権限を移譲する権限がありません', 'error')
        conn.close()
        return redirect(url_for('admin.admins'))
    
    # 自分自身への移譲を防止
    if admin_id == user_id:
        flash('自分自身にオーナー権限を移譲することはできません', 'error')
        conn.close()
        return redirect(url_for('admin.admins'))
    
    # 移譲先の管理者が同じテナントか確認
    cur.execute(_sql(conn, 'SELECT name FROM "T_管理者" WHERE id = %s AND tenant_id = %s AND role = %s'),
               (admin_id, tenant_id, ROLES["ADMIN"]))
    row = cur.fetchone()
    
    if not row:
        flash('管理者が見つかりません', 'error')
    else:
        # 現在のオーナーの権限を解除（can_manage_adminsも解除）
        cur.execute(_sql(conn, 'UPDATE "T_管理者" SET is_owner = 0, can_manage_admins = 0 WHERE id = %s'), (user_id,))
        # 新しいオーナーに権限を付与
        cur.execute(_sql(conn, 'UPDATE "T_管理者" SET is_owner = 1, can_manage_admins = 1 WHERE id = %s'), (admin_id,))
        conn.commit()
        flash(f'{row[0]} にオーナー権限を移譲しました', 'success')
    
    conn.close()
    return redirect(url_for('admin.admins'))


# ========================================
# 従業員管理
# ========================================

@bp.route('/employees')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employees():
    """従業員一覧（自分が所属する店舗のみ）"""
    admin_id = session.get('user_id')
    store_id = session.get('store_id')
    
    if not store_id:
        flash('店舗が選択されていません', 'error')
        return redirect(url_for('admin.dashboard'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 選択中の店舗に所属する従業員を取得
    cur.execute(_sql(conn, '''
        SELECT DISTINCT e.id, e.login_id, e.name, e.email, e.created_at
        FROM "T_従業員" e
        INNER JOIN "T_従業員_店舗" es ON e.id = es.employee_id
        WHERE es.store_id = %s
        ORDER BY e.created_at DESC
    '''), (store_id,))
    
    employees_list = []
    for row in cur.fetchall():
        emp_id = row[0]
        
        # この従業員が所属する店舗を取得
        cur.execute(_sql(conn, '''
            SELECT s.名称
            FROM "T_店舗" s
            INNER JOIN "T_従業員_店舗" es ON s.id = es.store_id
            WHERE es.employee_id = %s
            ORDER BY s.名称
        '''), (emp_id,))
        stores = [r[0] for r in cur.fetchall()]
        
        employees_list.append({
            'id': emp_id,
            'login_id': row[1],
            'name': row[2],
            'email': row[3],
            'created_at': row[4],
            'stores': stores
        })
    
    # 現在の店舗名を取得
    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    store_name = store_row[0] if store_row else '不明'
    
    conn.close()
    
    return render_template('admin_employees.html', employees=employees_list, store_name=store_name)


@bp.route('/employees/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_new():
    """従業員新規作成（自分が所属する店舗のみ選択可能）"""
    admin_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    
    if not store_id:
        flash('店舗が選択されていません', 'error')
        return redirect(url_for('admin.dashboard'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 管理者が所属する店舗一覧を取得
    cur.execute(_sql(conn, '''
        SELECT s.id, s.名称
        FROM "T_店舗" s
        INNER JOIN "T_管理者_店舗" admin_store ON s.id = admin_store.store_id
        WHERE admin_store.admin_id = %s AND s.有効 = 1
        ORDER BY s.名称
    '''), (admin_id,))
    stores = [{'id': row[0], '名称': row[1]} for row in cur.fetchall()]
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        store_ids = request.form.getlist('store_ids')  # 複数選択
        
        if not login_id or not name or not email or not password:
            flash('ログインID、氏名、メールアドレス、パスワードは必須です', 'error')
        elif password != password_confirm:
            flash('パスワードが一致しません', 'error')
        elif not store_ids:
            flash('少なくとも1つの店舗を選択してください', 'error')
        else:
            # 選択された店舗が全て管理者の所属店舗か確認
            cur.execute(_sql(conn, '''
                SELECT store_id FROM "T_管理者_店舗" WHERE admin_id = %s
            '''), (admin_id,))
            admin_store_ids = [str(row[0]) for row in cur.fetchall()]
            
            if not all(sid in admin_store_ids for sid in store_ids):
                flash('選択された店舗に権限がありません', 'error')
            else:
                # 重複チェック
                cur.execute(_sql(conn, 'SELECT id FROM "T_従業員" WHERE login_id = %s OR email = %s'), (login_id, email))
                if cur.fetchone():
                    flash('このログインIDまたはメールアドレスは既に使用されています', 'error')
                else:
                    ph = generate_password_hash(password)
                    cur.execute(_sql(conn, '''
                        INSERT INTO "T_従業員" (login_id, name, email, password_hash, tenant_id, role)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    '''), (login_id, name, email, ph, tenant_id, ROLES['EMPLOYEE']))
                    
                    # 新しく作成した従業員のIDを取得
                    cur.execute(_sql(conn, 'SELECT id FROM "T_従業員" WHERE login_id = %s'), (login_id,))
                    new_employee_id = cur.fetchone()[0]
                    
                    # 中間テーブルに店舗を紐付け
                    for sid in store_ids:
                        cur.execute(_sql(conn, '''
                            INSERT INTO "T_従業員_店舗" (employee_id, store_id)
                            VALUES (%s, %s)
                        '''), (new_employee_id, int(sid)))
                    
                    conn.commit()
                    flash('従業員を作成しました', 'success')
                    conn.close()
                    return redirect(url_for('admin.employees'))
    
    conn.close()
    return render_template('admin_employee_new.html', stores=stores, back_url=url_for('admin.employees'))


@bp.route('/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_edit(employee_id):
    """従業員編集（自分が所属する店舗のみ選択可能）"""
    admin_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    
    if not store_id:
        flash('店舗が選択されていません', 'error')
        return redirect(url_for('admin.dashboard'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 管理者が所属する店舗一覧を取得
    cur.execute(_sql(conn, '''
        SELECT s.id, s.名称
        FROM "T_店舗" s
        INNER JOIN "T_管理者_店舗" admin_store ON s.id = admin_store.store_id
        WHERE admin_store.admin_id = %s AND s.有効 = 1
        ORDER BY s.名称
    '''), (admin_id,))
    stores = [{'id': row[0], '名称': row[1]} for row in cur.fetchall()]
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        store_ids = request.form.getlist('store_ids')
        
        if not login_id or not name or not email:
            flash('ログインID、氏名、メールアドレスは必須です', 'error')
        elif not store_ids:
            flash('少なくとも1つの店舗を選択してください', 'error')
        else:
            # 選択された店舗が全て管理者の所属店舗か確認
            cur.execute(_sql(conn, '''
                SELECT store_id FROM "T_管理者_店舗" WHERE admin_id = %s
            '''), (admin_id,))
            admin_store_ids = [str(row[0]) for row in cur.fetchall()]
            
            if not all(sid in admin_store_ids for sid in store_ids):
                flash('選択された店舗に権限がありません', 'error')
            else:
                # 重複チェック（自分以外）
                cur.execute(_sql(conn, 'SELECT id FROM "T_従業員" WHERE (login_id = %s OR email = %s) AND id != %s'),
                           (login_id, email, employee_id))
                if cur.fetchone():
                    flash('このログインIDまたはメールアドレスは既に使用されています', 'error')
                else:
                    # 従業員情報を更新
                    if password:
                        ph = generate_password_hash(password)
                        cur.execute(_sql(conn, '''
                            UPDATE "T_従業員"
                            SET login_id = %s, name = %s, email = %s, password_hash = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s AND tenant_id = %s
                        '''), (login_id, name, email, ph, employee_id, tenant_id))
                    else:
                        cur.execute(_sql(conn, '''
                            UPDATE "T_従業員"
                            SET login_id = %s, name = %s, email = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s AND tenant_id = %s
                        '''), (login_id, name, email, employee_id, tenant_id))
                    
                    # 店舗の紐付けを更新
                    cur.execute(_sql(conn, 'DELETE FROM "T_従業員_店舗" WHERE employee_id = %s'), (employee_id,))
                    for sid in store_ids:
                        cur.execute(_sql(conn, '''
                            INSERT INTO "T_従業員_店舗" (employee_id, store_id)
                            VALUES (%s, %s)
                        '''), (employee_id, int(sid)))
                    
                    conn.commit()
                    flash('従業員情報を更新しました', 'success')
                    conn.close()
                    return redirect(url_for('admin.employees'))
    
    # 従業員情報を取得
    cur.execute(_sql(conn, '''
        SELECT login_id, name, email FROM "T_従業員" WHERE id = %s AND tenant_id = %s
    '''), (employee_id, tenant_id))
    row = cur.fetchone()
    
    if not row:
        flash('従業員が見つかりません', 'error')
        conn.close()
        return redirect(url_for('admin.employees'))
    
    employee = {
        'id': employee_id,
        'login_id': row[0],
        'name': row[1],
        'email': row[2]
    }
    
    # 現在の店舗割り当てを取得
    cur.execute(_sql(conn, 'SELECT store_id FROM "T_従業員_店舗" WHERE employee_id = %s'), (employee_id,))
    assigned_store_ids = [row[0] for row in cur.fetchall()]
    
    conn.close()
    
    return render_template('admin_employee_edit.html',
                          employee=employee,
                          stores=stores,
                          assigned_store_ids=assigned_store_ids,
                          back_url=url_for('admin.employees'))


@bp.route('/employees/<int:employee_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_delete(employee_id):
    """従業員削除（自分が所属する店舗の従業員のみ）"""
    admin_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    
    if not store_id:
        flash('店舗が選択されていません', 'error')
        return redirect(url_for('admin.dashboard'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 従業員が現在の店舗に所属しているか確認
    cur.execute(_sql(conn, '''
        SELECT e.name
        FROM "T_従業員" e
        INNER JOIN "T_従業員_店舗" es ON e.id = es.employee_id
        WHERE e.id = %s AND e.tenant_id = %s AND es.store_id = %s
    '''), (employee_id, tenant_id, store_id))
    row = cur.fetchone()
    
    if not row:
        flash('従業員が見つかりません、または削除権限がありません', 'error')
    else:
        name = row[0]
        # 中間テーブルのデータも削除
        cur.execute(_sql(conn, 'DELETE FROM "T_従業員_店舗" WHERE employee_id = %s'), (employee_id,))
        cur.execute(_sql(conn, 'DELETE FROM "T_従業員" WHERE id = %s AND tenant_id = %s'), (employee_id, tenant_id))
        conn.commit()
        flash(f'従業員 "{name}" を削除しました', 'success')
    
    conn.close()
    return redirect(url_for('admin.employees'))


# ========================================
# 管理者マイページ
# ========================================

@bp.route('/mypage', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def mypage():
    """管理者マイページ"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # ユーザー情報を取得
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, email, can_manage_admins, created_at, updated_at
        FROM "T_管理者"
        WHERE id = %s AND role = %s
    '''), (user_id, ROLES["ADMIN"]))
    
    row = cur.fetchone()
    
    if not row:
        flash('ユーザー情報が見つかりません', 'error')
        conn.close()
        return redirect(url_for('admin.dashboard'))
    
    user = {
        'id': row[0],
        'login_id': row[1],
        'name': row[2],
        'email': row[3],
        'can_manage_admins': row[4],
        'created_at': row[5],
        'updated_at': row[6]
    }
    
    # テナント名を取得
    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_テナント" WHERE id = %s'), (tenant_id,))
    tenant_row = cur.fetchone()
    tenant_name = tenant_row[0] if tenant_row else '不明'
    
    # 所属店舗を取得（表示用）
    cur.execute(_sql(conn, '''
        SELECT s.名称
        FROM "T_店舗" s
        INNER JOIN "T_管理者_店舗" admin_store ON s.id = admin_store.store_id
        WHERE admin_store.admin_id = %s
    '''), (user_id,))
    stores = [row[0] for row in cur.fetchall()]
    
    # 所属店舗を取得（選択用）
    cur.execute(_sql(conn, '''
        SELECT s.id, s.名称
        FROM "T_店舗" s
        INNER JOIN "T_管理者_店舗" admin_store ON s.id = admin_store.store_id
        WHERE admin_store.admin_id = %s
    '''), (user_id,))
    store_list = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    
    # POSTリクエスト（プロフィール編集またはパスワード変更）
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        if action == 'update_profile':
            # プロフィール編集
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            
            if not login_id or not name:
                conn.close()
                flash('ログインIDと氏名は必須です', 'error')
                return render_template('admin_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
            
            # ログインID重複チェック（自分以外）
            cur.execute(_sql(conn, 'SELECT id FROM "T_管理者" WHERE login_id = %s AND id != %s'), (login_id, user_id))
            if cur.fetchone():
                conn.close()
                flash('このログインIDは既に使用されています', 'error')
                return render_template('admin_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
            
            # プロフィール更新
            cur.execute(_sql(conn, '''
                UPDATE "T_管理者"
                SET login_id = %s, name = %s, email = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            '''), (login_id, name, email, user_id))
            conn.commit()
            conn.close()
            
            flash('プロフィール情報を更新しました', 'success')
            return redirect(url_for('admin.mypage'))
        
        elif action == 'change_password':
            # パスワード変更
            current_password = request.form.get('current_password', '').strip()
            new_password = request.form.get('new_password', '').strip()
            new_password_confirm = request.form.get('new_password_confirm', '').strip()
            
            # パスワード一致チェック
            if new_password != new_password_confirm:
                flash('パスワードが一致しません', 'error')
                conn.close()
                return render_template('admin_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
            
            # 現在のパスワードを確認
            cur.execute(_sql(conn, 'SELECT password_hash FROM "T_管理者" WHERE id = %s'), (user_id,))
            row = cur.fetchone()
            if not row or not check_password_hash(row[0], current_password):
                conn.close()
                flash('現在のパスワードが正しくありません', 'error')
                return render_template('admin_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
            
            # パスワードを更新
            password_hash = generate_password_hash(new_password)
            cur.execute(_sql(conn, '''
                UPDATE "T_管理者"
                SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            '''), (password_hash, user_id))
            conn.commit()
            conn.close()
            
            flash('パスワードを変更しました', 'success')
            return redirect(url_for('admin.mypage'))
    
    conn.close()
    return render_template('admin_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)


@bp.route('/select_store_from_mypage', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def select_store_from_mypage():
    """マイページから店舗を選択してダッシュボードに進む"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    store_id = request.form.get('store_id')
    
    if not store_id:
        flash('店舗を選択してください', 'error')
        return redirect(url_for('admin.mypage'))
    
    # 管理者が選択した店舗に所属しているか確認
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(_sql(conn, '''
        SELECT COUNT(*) FROM "T_管理者_店舗"
        WHERE admin_id = %s AND store_id = %s
    '''), (user_id, store_id))
    
    count = cur.fetchone()[0]
    conn.close()
    
    if count == 0:
        flash('選択した店舗にアクセスする権限がありません', 'error')
        return redirect(url_for('admin.mypage'))
    
    # セッションに店舗IDを保存
    session['store_id'] = int(store_id)
    
    flash('店舗を選択しました', 'success')
    return redirect(url_for('admin.dashboard'))


# ========================================
# 店舗アプリ管理
# ========================================

@bp.route('/store/<int:store_id>/apps')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_apps(store_id):
    """店舗アプリ一覧ページ"""
    tenant_id = session.get('tenant_id')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 店舗情報を取得
    cur.execute(_sql(conn, '''
        SELECT id, 名称, slug
        FROM "T_店舗"
        WHERE id = %s
    '''), (store_id,))
    
    store_row = cur.fetchone()
    conn.close()
    
    if not store_row:
        flash('店舗が見つかりません', 'error')
        return redirect(url_for('admin.store_info'))
    
    store = {
        'id': store_row[0],
        'store_name': store_row[1],
        'slug': store_row[2]
    }
    
    # セッションにstore_idを設定
    session['store_id'] = store_id
    session['store_name'] = store_row[1]
    
    # 店舗で有効なアプリを取得
    conn = get_db_connection()
    cur = conn.cursor()
    
    enabled_apps = []
    for app in AVAILABLE_APPS:
        if app['scope'] == 'store':
            # データベースから有効/無効を確認
            cur.execute(_sql(conn, '''
                SELECT enabled FROM "T_店舗アプリ設定"
                WHERE store_id = %s AND app_name = %s
            '''), (store_id, app['name']))
            row = cur.fetchone()
            enabled = row[0] if row else 1  # デフォルトは有効
            
            if enabled:
                enabled_apps.append(app)
    
    conn.close()
    
    return render_template('admin_store_apps.html', store=store, apps=enabled_apps)
