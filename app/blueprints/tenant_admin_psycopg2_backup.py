# -*- coding: utf-8 -*-
"""
テナント管理者ダッシュボード
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from ..utils import require_roles, ROLES, get_db_connection, is_tenant_owner, can_manage_tenant_admins
from ..utils.db import _sql
from werkzeug.security import generate_password_hash, check_password_hash

bp = Blueprint('tenant_admin', __name__, url_prefix='/tenant_admin')


@bp.route('/')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def dashboard():
    """テナント管理者ダッシュボード"""
    return render_template('tenant_admin_dashboard.html', tenant_id=session.get('tenant_id'))


# ========================================
# テナント情報管理
# ========================================

@bp.route('/tenant_info')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_info():
    """テナント情報表示"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントIDが取得できません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(_sql(conn, 'SELECT id, 名称, slug, created_at FROM "T_テナント" WHERE id = %s'), (tenant_id,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        flash('テナント情報が見つかりません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    tenant = {
        'id': row[0],
        '名称': row[1],
        'slug': row[2],
        'created_at': row[3]
    }
    return render_template('tenant_info.html', tenant=tenant)


@bp.route('/me/edit', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def me_edit():
    """テナント情報編集"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントIDが取得できません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        name = request.form.get('名称', '').strip()
        slug = request.form.get('slug', '').strip()
        openai_api_key = request.form.get('openai_api_key', '').strip()
        
        if not name or not slug:
            flash('名称とslugは必須です', 'error')
        else:
            cur.execute(_sql(conn, 'UPDATE "T_テナント" SET 名称 = %s, slug = %s, openai_api_key = %s WHERE id = %s'),
                       (name, slug, openai_api_key if openai_api_key else None, tenant_id))
            conn.commit()
            flash('テナント情報を更新しました', 'success')
            conn.close()
            return redirect(url_for('tenant_admin.dashboard'))
    
    cur.execute(_sql(conn, 'SELECT id, 名称, slug, openai_api_key FROM "T_テナント" WHERE id = %s'), (tenant_id,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        flash('テナント情報が見つかりません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    tenant = {'id': row[0], '名称': row[1], 'slug': row[2], 'openai_api_key': row[3] if len(row) > 3 else None}
    return render_template('tenant_me_edit.html', t=tenant, back_url=url_for('tenant_admin.dashboard'))


@bp.route('/portal')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def portal():
    """テナントポータル"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # テナント情報を取得
    cur.execute(_sql(conn, 'SELECT id, "名称", slug FROM "T_テナント" WHERE id = %s'), (tenant_id,))
    tenant_row = cur.fetchone()
    tenant = None
    if tenant_row:
        tenant = {'id': tenant_row[0], '名称': tenant_row[1], 'slug': tenant_row[2]}
    
    # 管理者数を取得
    cur.execute(_sql(conn, 'SELECT COUNT(*) FROM "T_管理者" WHERE tenant_id = %s AND role = %s'),
               (tenant_id, ROLES["ADMIN"]))
    admin_count = cur.fetchone()[0]
    
    # 従業員数を取得
    cur.execute(_sql(conn, 'SELECT COUNT(*) FROM "T_従業員" WHERE tenant_id = %s'),
               (tenant_id,))
    employee_count = cur.fetchone()[0]
    
    conn.close()
    
    return render_template('tenant_portal.html', 
                         tenant=tenant,
                         admin_count=admin_count,
                         employee_count=employee_count,
                         stores=[])


# ========================================
# 店舗管理
# ========================================

@bp.route('/stores')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def stores():
    """店舗一覧"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(_sql(conn, '''
        SELECT id, 名称, slug, created_at, updated_at
        FROM "T_店舗"
        WHERE tenant_id = %s
        ORDER BY id
    '''), (tenant_id,))
    
    stores_list = []
    for row in cur.fetchall():
        stores_list.append({
            'id': row[0],
            '名称': row[1],
            'slug': row[2],
            'created_at': row[3],
            'updated_at': row[4]
        })
    conn.close()
    
    return render_template('tenant_stores.html', stores=stores_list)


@bp.route('/stores/<int:store_id>')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_detail(store_id):
    """店舗詳細"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 店舗情報を取得
    cur.execute(_sql(conn, '''
        SELECT id, 名称, slug, created_at, updated_at
        FROM "T_店舗"
        WHERE id = %s AND tenant_id = %s
    '''), (store_id, tenant_id))
    row = cur.fetchone()
    
    if not row:
        flash('店舗が見つかりません', 'error')
        conn.close()
        return redirect(url_for('tenant_admin.stores'))
    
    store = {
        'id': row[0],
        '名称': row[1],
        'slug': row[2],
        'created_at': row[3],
        'updated_at': row[4]
    }
    
    # 店舗管理者数を取得
    cur.execute(_sql(conn, 'SELECT COUNT(*) FROM "T_管理者" WHERE tenant_id = %s AND role = %s'),
               (tenant_id, ROLES["ADMIN"]))
    admin_count = cur.fetchone()[0]
    
    # 従業員数を取得
    cur.execute(_sql(conn, 'SELECT COUNT(*) FROM "T_従業員" WHERE tenant_id = %s'),
               (tenant_id,))
    employee_count = cur.fetchone()[0]
    
    conn.close()
    
    return render_template('tenant_store_detail.html', 
                         store=store,
                         admin_count=admin_count,
                         employee_count=employee_count)


@bp.route('/stores/new', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_new():
    """店舗新規作成"""
    tenant_id = session.get('tenant_id')
    
    if request.method == 'POST':
        name = request.form.get('名称', '').strip()
        slug = request.form.get('slug', '').strip()
        
        if not name or not slug:
            flash('名称とslugは必須です', 'error')
        else:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # 重複チェック
            cur.execute(_sql(conn, 'SELECT id FROM "T_店舗" WHERE tenant_id = %s AND slug = %s'), (tenant_id, slug))
            if cur.fetchone():
                flash('このslugは既に使用されています', 'error')
                conn.close()
            else:
                cur.execute(_sql(conn, '''
                    INSERT INTO "T_店舗" (tenant_id, 名称, slug)
                    VALUES (%s, %s, %s)
                '''), (tenant_id, name, slug))
                conn.commit()
                conn.close()
                flash('店舗を作成しました', 'success')
                return redirect(url_for('tenant_admin.stores'))
    
    return render_template('tenant_store_new.html', back_url=url_for('tenant_admin.stores'))


@bp.route('/stores/<int:store_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_edit(store_id):
    """店舗編集"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        name = request.form.get('名称', '').strip()
        slug = request.form.get('slug', '').strip()
        
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
                    SET 名称 = %s, slug = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND tenant_id = %s
                '''), (name, slug, store_id, tenant_id))
                conn.commit()
                flash('店舗情報を更新しました', 'success')
                conn.close()
                return redirect(url_for('tenant_admin.store_detail', store_id=store_id))
    
    # GETリクエスト：店舗情報を取得
    cur.execute(_sql(conn, '''
        SELECT id, 名称, slug
        FROM "T_店舗"
        WHERE id = %s AND tenant_id = %s
    '''), (store_id, tenant_id))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        flash('店舗が見つかりません', 'error')
        return redirect(url_for('tenant_admin.stores'))
    
    store = {'id': row[0], '名称': row[1], 'slug': row[2]}
    return render_template('tenant_store_edit.html', store=store)


@bp.route('/stores/<int:store_id>/delete', methods=['POST'])
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
    return redirect(url_for('tenant_admin.stores'))


# ========================================
# 管理者管理
# ========================================

@bp.route('/admins')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admins():
    """管理者一覧"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, active, created_at, can_manage_admins, is_owner 
        FROM "T_管理者" 
        WHERE tenant_id = %s AND role = %s 
        ORDER BY can_manage_admins DESC, id
    '''), (tenant_id, ROLES["ADMIN"]))
    
    admins_list = []
    for row in cur.fetchall():
        admins_list.append({
            'id': row[0],
            'login_id': row[1],
            'name': row[2],
            'active': row[3],
            'created_at': row[4],
            'can_manage_admins': row[5],
            'is_owner': row[6]
        })
    conn.close()
    
    user_id = session.get('user_id')
    role = session.get('role')
    is_system_admin = role == 'system_admin'
    is_tenant_admin = role == 'tenant_admin'
    return render_template('tenant_admins.html', admins=admins_list, current_user_id=user_id, is_owner=True, is_system_admin=is_system_admin, is_tenant_admin=is_tenant_admin)


@bp.route('/admins/new', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_new():
    """管理者新規作成（管理者管理権限が必要）"""
    # 管理者管理権限チェック
    if not can_manage_tenant_admins():
        flash('管理者を作成する権限がありません', 'error')
        return redirect(url_for('tenant_admin.admins'))
    
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 店舗一覧を取得
    cur.execute(_sql(conn, 'SELECT id, 名称 FROM "T_店舗" WHERE tenant_id = %s AND 有効 = 1 ORDER BY 名称'), (tenant_id,))
    stores = [{'id': row[0], '名称': row[1]} for row in cur.fetchall()]
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        store_ids = request.form.getlist('store_ids')  # 複数選択
        
        if not login_id or not name or not password:
            flash('ログインID、氏名、パスワードは必須です', 'error')
        elif password != password_confirm:
            flash('パスワードが一致しません', 'error')
        elif not store_ids:
            flash('少なくとも1つの店舗を選択してください', 'error')
        else:
            # 重複チェック
            cur.execute(_sql(conn, 'SELECT id FROM "T_管理者" WHERE login_id = %s'), (login_id,))
            if cur.fetchone():
                flash('このログインIDは既に使用されています', 'error')
            else:
                ph = generate_password_hash(password)
                cur.execute(_sql(conn, '''
                    INSERT INTO "T_管理者" (login_id, name, password_hash, role, tenant_id, active)
                    VALUES (%s, %s, %s, %s, %s, 1)
                '''), (login_id, name, ph, ROLES["ADMIN"], tenant_id))
                
                # 新しく作成した管理者のIDを取得
                cur.execute(_sql(conn, 'SELECT id FROM "T_管理者" WHERE login_id = %s'), (login_id,))
                new_admin_id = cur.fetchone()[0]
                
                # 中間テーブルに店舗を紐付け
                for store_id in store_ids:
                    cur.execute(_sql(conn, '''
                        INSERT INTO "T_管理者_店舗" (admin_id, store_id)
                        VALUES (%s, %s)
                    '''), (new_admin_id, int(store_id)))
                
                conn.commit()
                flash('管理者を作成しました', 'success')
                conn.close()
                return redirect(url_for('tenant_admin.admins'))
    
    conn.close()
    return render_template('admin_new.html', stores=stores, back_url=url_for('tenant_admin.admins'))
@bp.route('/admins/<int:admin_id>/toggle_active', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_toggle_active(admin_id):
    """管理者の有効/無効を切り替える"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 管理者の情報を取得
    cur.execute(_sql(conn, 'SELECT name, active FROM "T_管理者" WHERE id = %s AND tenant_id = %s AND role = %s'),
               (admin_id, tenant_id, ROLES["ADMIN"]))
    row = cur.fetchone()
    
    if not row:
        flash('管理者が見つかりません', 'error')
    else:
        name = row[0]
        current_active = row[1]
        new_active = 0 if current_active == 1 else 1
        
        # 有効/無効を切り替える
        cur.execute(_sql(conn, 'UPDATE "T_管理者" SET active = %s WHERE id = %s'),
                   (new_active, admin_id))
        conn.commit()
        
        status_text = '有効' if new_active == 1 else '無効'
        flash(f'管理者『{name}』を{status_text}にしました', 'success')
    
    conn.close()
    return redirect(url_for('tenant_admin.admins'))


@bp.route('/admins/<int:admin_id>/delete', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_delete(admin_id):
    """管理者削除（管理者管理権限が必要）"""
    # 管理者管理権限チェック
    if not can_manage_tenant_admins():
        flash('管理者を削除する権限がありません', 'error')
        return redirect(url_for('tenant_admin.admins'))
    
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
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
    return redirect(url_for('tenant_admin.admins'))


@bp.route('/admins/<int:admin_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_edit(admin_id):
    """管理者編集（管理者管理権限が必要）"""
    # 管理者管理権限チェック
    if not can_manage_tenant_admins():
        flash('管理者を編集する権限がありません', 'error')
        return redirect(url_for('tenant_admin.admins'))
    
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 店舗一覧を取得
    cur.execute(_sql(conn, 'SELECT id, 名称 FROM "T_店舗" WHERE tenant_id = %s AND 有効 = 1 ORDER BY 名称'), (tenant_id,))
    stores = [{'id': row[0], '名称': row[1]} for row in cur.fetchall()]
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '').strip()
        active = int(request.form.get('active', 1))
        store_ids = request.form.getlist('store_ids')  # 複数選択
        
        if not login_id or not name:
            flash('ログインIDと氏名は必須です', 'error')
        elif not store_ids:
            flash('少なくとも1つの店舗を選択してください', 'error')
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
                        SET login_id = %s, name = %s, password_hash = %s, active = %s
                        WHERE id = %s AND tenant_id = %s AND role = %s
                    '''), (login_id, name, ph, active, admin_id, tenant_id, ROLES["ADMIN"]))
                else:
                    # パスワード変更なし
                    cur.execute(_sql(conn, '''
                        UPDATE "T_管理者"
                        SET login_id = %s, name = %s, active = %s
                        WHERE id = %s AND tenant_id = %s AND role = %s
                    '''), (login_id, name, active, admin_id, tenant_id, ROLES["ADMIN"]))
                
                # 所属店舗を更新（既存を削除して新しく追加）
                cur.execute(_sql(conn, 'DELETE FROM "T_管理者_店舗" WHERE admin_id = %s'), (admin_id,))
                for store_id in store_ids:
                    cur.execute(_sql(conn, '''
                        INSERT INTO "T_管理者_店舗" (admin_id, store_id)
                        VALUES (%s, %s)
                    '''), (admin_id, int(store_id)))
                
                conn.commit()
                flash('管理者情報を更新しました', 'success')
                conn.close()
                return redirect(url_for('tenant_admin.admins'))
    
    # GETリクエスト：管理者情報を取得
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, active, can_manage_admins
        FROM "T_管理者"
        WHERE id = %s AND tenant_id = %s AND role = %s
    '''), (admin_id, tenant_id, ROLES["ADMIN"]))
    row = cur.fetchone()
    
    if not row:
        conn.close()
        flash('管理者が見つかりません', 'error')
        return redirect(url_for('tenant_admin.admins'))
    
    admin = {
        'id': row[0],
        'login_id': row[1],
        'name': row[2],
        'active': row[3],
        'can_manage_admins': row[4]
    }
    
    # 現在の所属店舗を取得
    cur.execute(_sql(conn, 'SELECT store_id FROM "T_管理者_店舗" WHERE admin_id = %s'), (admin_id,))
    admin_store_ids = [row[0] for row in cur.fetchall()]
    conn.close()
    
    return render_template('tenant_admin_edit.html', admin=admin, stores=stores, admin_store_ids=admin_store_ids)
@bp.route('/admins/<int:admin_id>/toggle_manage_permission', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def toggle_admin_manage_permission(admin_id):
    """管理者管理権限の付与・剝奪（管理者管理権限が必要）"""
    # 管理者管理権限チェック
    if not can_manage_tenant_admins():
        flash('管理者管理権限を変更する権限がありません', 'error')
        return redirect(url_for('tenant_admin.admins'))
    
    # 自分自身の権限は変更できない
    if admin_id == session.get('user_id'):
        flash('自分自身の権限は変更できません', 'error')
        return redirect(url_for('tenant_admin.admins'))
    
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 現在の状態を取得
    cur.execute(_sql(conn, '''
        SELECT can_manage_admins, name 
        FROM "T_管理者" 
        WHERE id = %s AND tenant_id = %s AND role = %s
    '''), (admin_id, tenant_id, ROLES["ADMIN"]))
    row = cur.fetchone()
    
    if not row:
        flash('管理者が見つかりません', 'error')
        conn.close()
        return redirect(url_for('tenant_admin.admins'))
    
    current_permission = row[0]
    admin_name = row[1]
    new_permission = 0 if current_permission == 1 else 1
    
    # 権限を切り替え
    cur.execute(_sql(conn, '''
        UPDATE "T_管理者"
        SET can_manage_admins = %s
        WHERE id = %s
    '''), (new_permission, admin_id))
    conn.commit()
    conn.close()
    
    if new_permission == 1:
        flash(f'{admin_name} に管理者管理権限を付与しました', 'success')
    else:
        flash(f'{admin_name} から管理者管理権限を剝奪しました', 'success')
    
    return redirect(url_for('tenant_admin.admins'))


# ========================================
# 従業員管理
# ========================================

@bp.route('/employees')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employees():
    """従業員一覧"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, email, active, created_at 
        FROM "T_従業員" 
        WHERE tenant_id = %s 
        ORDER BY id
    '''), (tenant_id,))
    
    employees_list = []
    for row in cur.fetchall():
        employees_list.append({
            'id': row[0],
            'login_id': row[1],
            'name': row[2],
            'email': row[3],
            'active': row[4],
            'created_at': row[5]
        })
    conn.close()
    
    return render_template('tenant_employees.html', employees=employees_list)


@bp.route('/employees/new', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_new():
    """従業員新規作成"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 店舗一覧を取得
    cur.execute(_sql(conn, 'SELECT id, 名称 FROM "T_店舗" WHERE tenant_id = %s AND 有効 = 1 ORDER BY 名称'), (tenant_id,))
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
            # 重複チェック
            cur.execute(_sql(conn, 'SELECT id FROM "T_従業員" WHERE login_id = %s OR email = %s'), (login_id, email))
            if cur.fetchone():
                flash('このログインIDまたはメールアドレスは既に使用されています', 'error')
            else:
                ph = generate_password_hash(password)
                cur.execute(_sql(conn, '''
                    INSERT INTO "T_従業員" (login_id, name, email, password_hash, tenant_id, role, active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                '''), (login_id, name, email, ph, tenant_id, ROLES['EMPLOYEE'], 1))
                
                # 新しく作成した従業員のIDを取得
                cur.execute(_sql(conn, 'SELECT id FROM "T_従業員" WHERE login_id = %s'), (login_id,))
                new_employee_id = cur.fetchone()[0]
                
                # 中間テーブルに店舗を紐付け
                for store_id in store_ids:
                    cur.execute(_sql(conn, '''
                        INSERT INTO "T_従業員_店舗" (employee_id, store_id)
                        VALUES (%s, %s)
                    '''), (new_employee_id, int(store_id)))
                
                conn.commit()
                flash('従業員を作成しました', 'success')
                conn.close()
                return redirect(url_for('tenant_admin.employees'))
    
    conn.close()
    return render_template('tenant_employee_new.html', stores=stores, back_url=url_for('tenant_admin.employees'))

@bp.route('/employees/<int:employee_id>/toggle_active', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_toggle_active(employee_id):
    """従業員の有効/無効を切り替え"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 従業員が存在するか確認
    cur.execute(_sql(conn, 'SELECT name, active FROM "T_従業員" WHERE id = %s AND tenant_id = %s'), (employee_id, tenant_id))
    row = cur.fetchone()
    
    if not row:
        flash('従業員が見つかりません', 'error')
    else:
        name = row[0]
        current_active = row[1]
        new_active = 0 if current_active == 1 else 1
        
        cur.execute(_sql(conn, 'UPDATE "T_従業員" SET active = %s WHERE id = %s AND tenant_id = %s'), 
                   (new_active, employee_id, tenant_id))
        conn.commit()
        
        status_text = '有効' if new_active == 1 else '無効'
        flash(f'従業員 "{name}" を{status_text}にしました', 'success')
    
    conn.close()
    return redirect(url_for('tenant_admin.employees'))

@bp.route('/employees/<int:employee_id>/delete', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_delete(employee_id):
    """従業員削除"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 従業員が存在するか確認
    cur.execute(_sql(conn, 'SELECT name FROM "T_従業員" WHERE id = %s AND tenant_id = %s'), (employee_id, tenant_id))
    row = cur.fetchone()
    
    if not row:
        flash('従業員が見つかりません', 'error')
    else:
        name = row[0]
        # 中間テーブルのデータも削除
        cur.execute(_sql(conn, 'DELETE FROM "T_従業員_店舗" WHERE employee_id = %s'), (employee_id,))
        cur.execute(_sql(conn, 'DELETE FROM "T_従業員" WHERE id = %s AND tenant_id = %s'), (employee_id, tenant_id))
        conn.commit()
        flash(f'従業員 "{name}" を削除しました', 'success')
    
    conn.close()
    return redirect(url_for('tenant_admin.employees'))

@bp.route('/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_edit(employee_id):
    """従業員編集"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 店舗一覧を取得
    cur.execute(_sql(conn, 'SELECT id, 名称 FROM "T_店舗" WHERE tenant_id = %s AND 有効 = 1 ORDER BY 名称'), (tenant_id,))
    stores = [{'id': row[0], '名称': row[1]} for row in cur.fetchall()]
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        active = 1 if request.form.get('active') == 'on' else 0
        store_ids = request.form.getlist('store_ids')  # 複数選択
        
        if not login_id or not name or not email:
            flash('ログインID、氏名、メールアドレスは必須です', 'error')
        elif not store_ids:
            flash('少なくとも1つの店舗を選択してください', 'error')
        else:
            # 重複チェック（自分以外）
            cur.execute(_sql(conn, 'SELECT id FROM "T_従業員" WHERE (login_id = %s OR email = %s) AND id != %s'), (login_id, email, employee_id))
            if cur.fetchone():
                flash('このログインIDまたはメールアドレスは既に使用されています', 'error')
            else:
                if password:
                    # パスワード変更あり
                    ph = generate_password_hash(password)
                    cur.execute(_sql(conn, '''
                        UPDATE "T_従業員"
                        SET login_id = %s, name = %s, email = %s, password_hash = %s, active = %s
                        WHERE id = %s AND tenant_id = %s
                    '''), (login_id, name, email, ph, active, employee_id, tenant_id))
                else:
                    # パスワード変更なし
                    cur.execute(_sql(conn, '''
                        UPDATE "T_従業員"
                        SET login_id = %s, name = %s, email = %s, active = %s
                        WHERE id = %s AND tenant_id = %s
                    '''), (login_id, name, email, active, employee_id, tenant_id))
                
                # 所属店舗を更新（既存を削除して新しく追加）
                cur.execute(_sql(conn, 'DELETE FROM "T_従業員_店舗" WHERE employee_id = %s'), (employee_id,))
                for store_id in store_ids:
                    cur.execute(_sql(conn, '''
                        INSERT INTO "T_従業員_店舗" (employee_id, store_id)
                        VALUES (%s, %s)
                    '''), (employee_id, int(store_id)))
                
                conn.commit()
                flash('従業員情報を更新しました', 'success')
                conn.close()
                return redirect(url_for('tenant_admin.employees'))
    
    # GETリクエスト：従業員情報を取得
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, email, active
        FROM "T_従業員"
        WHERE id = %s AND tenant_id = %s
    '''), (employee_id, tenant_id))
    row = cur.fetchone()
    
    if not row:
        conn.close()
        flash('従業員が見つかりません', 'error')
        return redirect(url_for('tenant_admin.employees'))
    
    employee = {
        'id': row[0],
        'login_id': row[1],
        'name': row[2],
        'email': row[3],
        'active': row[4]
    }
    
    # 現在の所属店舗を取得
    cur.execute(_sql(conn, 'SELECT store_id FROM "T_従業員_店舗" WHERE employee_id = %s'), (employee_id,))
    employee_store_ids = [row[0] for row in cur.fetchall()]
    conn.close()
    
    return render_template('tenant_employee_edit.html', employee=employee, stores=stores, employee_store_ids=employee_store_ids)

def employee_delete(employee_id):
    """従業員削除"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # テナントIDの確認
    cur.execute(_sql(conn, 'SELECT name FROM "T_従業員" WHERE id = %s AND tenant_id = %s'),
               (employee_id, tenant_id))
    row = cur.fetchone()
    
    if not row:
        flash('従業員が見つかりません', 'error')
    else:
        cur.execute(_sql(conn, 'DELETE FROM "T_従業員" WHERE id = %s'), (employee_id,))
        conn.commit()
        flash(f'{row[0]} を削除しました', 'success')
    
    conn.close()
    return redirect(url_for('tenant_admin.employees'))


# ========================================
# テナント管理者管理
# ========================================

@bp.route('/tenant_admins')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_admins():
    """テナント管理者一覧"""
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, active, created_at, is_owner, can_manage_admins 
        FROM "T_管理者" 
        WHERE tenant_id = %s AND role = %s 
        ORDER BY is_owner DESC, can_manage_admins DESC, id
    '''), (tenant_id, ROLES["TENANT_ADMIN"]))
    
    tenant_admins_list = []
    for row in cur.fetchall():
        tenant_admins_list.append({
            'id': row[0],
            'login_id': row[1],
            'name': row[2],
            'active': row[3],
            'created_at': row[4],
            'is_owner': row[5],
            'can_manage_admins': row[6]
        })
    conn.close()
    
    return render_template('tenant_tenant_admins.html', tenant_admins=tenant_admins_list)


@bp.route('/tenant_admins/new', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_admin_new():
    """テナント管理者新規作成（管理者管理権限が必要）"""
    # 管理者管理権限チェック
    if not can_manage_tenant_admins():
        flash('テナント管理者を作成する権限がありません', 'error')
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    tenant_id = session.get('tenant_id')
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '').strip()
        
        if not login_id or not name or not password:
            flash('全ての項目を入力してください', 'error')
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
                    INSERT INTO "T_管理者" (login_id, name, password_hash, role, tenant_id, active, can_manage_admins)
                    VALUES (%s, %s, %s, %s, %s, 1, 0)
                '''), (login_id, name, ph, ROLES["TENANT_ADMIN"], tenant_id))
                conn.commit()
                conn.close()
                flash('テナント管理者を作成しました', 'success')
                return redirect(url_for('tenant_admin.tenant_admins'))
    
    return render_template('tenant_tenant_admin_new.html', back_url=url_for('tenant_admin.tenant_admins'))


@bp.route('/tenant_admins/<int:tadmin_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_admin_edit(tadmin_id):
    """テナント管理者編集（管理者管理権限が必要）"""
    # 管理者管理権限チェック
    if not can_manage_tenant_admins():
        flash('テナント管理者を編集する権限がありません', 'error')
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        active = int(request.form.get('active', 1))
        
        if not login_id or not name:
            flash('ログインIDと氏名は必須です', 'error')
        else:
            # 重複チェック（自分以外）
            cur.execute(_sql(conn, 'SELECT id FROM "T_管理者" WHERE login_id = %s AND id != %s'), (login_id, tadmin_id))
            if cur.fetchone():
                flash(f'ログインID "{login_id}" は既に使用されています', 'error')
            else:
                if password:
                    # パスワード変更あり
                    ph = generate_password_hash(password)
                    cur.execute(_sql(conn, '''
                        UPDATE "T_管理者"
                        SET login_id = %s, name = %s, email = %s, password_hash = %s, active = %s
                        WHERE id = %s AND tenant_id = %s AND role = %s
                    '''), (login_id, name, email, ph, active, tadmin_id, tenant_id, ROLES["TENANT_ADMIN"]))
                else:
                    # パスワード変更なし
                    cur.execute(_sql(conn, '''
                        UPDATE "T_管理者"
                        SET login_id = %s, name = %s, email = %s, active = %s
                        WHERE id = %s AND tenant_id = %s AND role = %s
                    '''), (login_id, name, email, active, tadmin_id, tenant_id, ROLES["TENANT_ADMIN"]))
                
                conn.commit()
                flash('テナント管理者情報を更新しました', 'success')
                conn.close()
                return redirect(url_for('tenant_admin.tenant_admins'))
    
    # GETリクエスト：テナント管理者情報を取得
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, email, active, can_manage_admins
        FROM "T_管理者"
        WHERE id = %s AND tenant_id = %s AND role = %s
    '''), (tadmin_id, tenant_id, ROLES["TENANT_ADMIN"]))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        flash('テナント管理者が見つかりません', 'error')
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    tadmin = {
        'id': row[0],
        'login_id': row[1],
        'name': row[2],
        'email': row[3],
        'active': row[4],
        'can_manage_admins': row[5]
    }
    
    return render_template('tenant_tenant_admin_edit.html', tadmin=tadmin)


@bp.route('/tenant_admins/<int:tadmin_id>/delete', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_admin_delete(tadmin_id):
    """テナント管理者削除（管理者管理権限が必要）"""
    # 管理者管理権限チェック
    if not can_manage_tenant_admins():
        flash('テナント管理者を削除する権限がありません', 'error')
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    # 自分自身は削除できない
    if tadmin_id == session.get('user_id'):
        flash('自分自身は削除できません', 'error')
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # テナントIDとオーナーフラグの確認
    cur.execute(_sql(conn, 'SELECT name, is_owner FROM "T_管理者" WHERE id = %s AND tenant_id = %s AND role = %s'),
               (tadmin_id, tenant_id, ROLES["TENANT_ADMIN"]))
    row = cur.fetchone()
    
    if not row:
        flash('テナント管理者が見つかりません', 'error')
    elif row[1] == 1:
        flash('オーナーは削除できません。先にオーナー権限を移譲してください。', 'error')
    else:
        cur.execute(_sql(conn, 'DELETE FROM "T_管理者" WHERE id = %s'), (tadmin_id,))
        conn.commit()
        flash(f'{row[0]} を削除しました', 'success')
    
    conn.close()
    return redirect(url_for('tenant_admin.tenant_admins'))


@bp.route('/tenant_admins/<int:tadmin_id>/toggle_manage_permission', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def toggle_tenant_admin_manage_permission(tadmin_id):
    """テナント管理者管理権限の付与・剝奪（管理者管理権限が必要）"""
    # 管理者管理権限チェック
    if not can_manage_tenant_admins():
        flash('管理者管理権限を変更する権限がありません', 'error')
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    # 自分自身の権限は変更できない
    if tadmin_id == session.get('user_id'):
        flash('自分自身の権限は変更できません', 'error')
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 現在の状態を取得
    cur.execute(_sql(conn, '''
        SELECT can_manage_admins, name, is_owner 
        FROM "T_管理者" 
        WHERE id = %s AND tenant_id = %s AND role = %s
    '''), (tadmin_id, tenant_id, ROLES["TENANT_ADMIN"]))
    row = cur.fetchone()
    
    if not row:
        flash('テナント管理者が見つかりません', 'error')
        conn.close()
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    current_permission = row[0]
    tadmin_name = row[1]
    is_owner = row[2]
    
    # オーナーの権限は変更できない
    if is_owner == 1:
        flash('オーナーの管理権限は変更できません', 'error')
        conn.close()
        return redirect(url_for('tenant_admin.tenant_admins'))
    new_permission = 0 if current_permission == 1 else 1
    
    # 権限を切り替え
    cur.execute(_sql(conn, '''
        UPDATE "T_管理者"
        SET can_manage_admins = %s
        WHERE id = %s
    '''), (new_permission, tadmin_id))
    conn.commit()
    conn.close()
    
    if new_permission == 1:
        flash(f'{tadmin_name} に管理者管理権限を付与しました', 'success')
    else:
        flash(f'{tadmin_name} から管理者管理権限を剝奪しました', 'success')
    
    return redirect(url_for('tenant_admin.tenant_admins'))


@bp.route('/tenant_admins/<int:tadmin_id>/transfer_ownership', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def transfer_tenant_ownership(tadmin_id):
    """テナントオーナー権限を他のテナント管理者に移譲"""
    # オーナーのみ実行可能
    if not is_tenant_owner():
        flash('オーナーのみがオーナー権限を移譲できます', 'error')
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    # 自分自身には移譲できない
    if tadmin_id == session.get('user_id'):
        flash('自分自身にオーナー権限を移譲することはできません', 'error')
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    tenant_id = session.get('tenant_id')
    current_user_id = session.get('user_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 移譲先のテナント管理者を確認
    cur.execute(_sql(conn, '''
        SELECT id, name 
        FROM "T_管理者" 
        WHERE id = %s AND tenant_id = %s AND role = %s AND active = 1
    '''), (tadmin_id, tenant_id, ROLES["TENANT_ADMIN"]))
    row = cur.fetchone()
    
    if not row:
        flash('移譲先のテナント管理者が見つかりません', 'error')
        conn.close()
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    new_owner_name = row[1]
    
    # 現在のオーナーのis_ownerを0に設定
    cur.execute(_sql(conn, '''
        UPDATE "T_管理者"
        SET is_owner = 0
        WHERE id = %s
    '''), (current_user_id,))
    
    # 新しいオーナーのis_ownerを1に設定し、can_manage_adminsも1に設定
    cur.execute(_sql(conn, '''
        UPDATE "T_管理者"
        SET is_owner = 1, can_manage_admins = 1
        WHERE id = %s
    '''), (tadmin_id,))
    
    conn.commit()
    conn.close()
    
    flash(f'{new_owner_name} にオーナー権限を移譲しました', 'success')
    return redirect(url_for('tenant_admin.tenant_admins'))


# ========================================
# テナント管理者マイページ
# ========================================

@bp.route('/mypage', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def mypage():
    """テナント管理者マイページ"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # ユーザー情報を取得
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, email, can_manage_admins, created_at, updated_at
        FROM "T_管理者"
        WHERE id = %s AND role = %s
    '''), (user_id, ROLES["TENANT_ADMIN"]))
    
    row = cur.fetchone()
    
    if not row:
        flash('ユーザー情報が見つかりません', 'error')
        conn.close()
        return redirect(url_for('tenant_admin.dashboard'))
    
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
    tenant_name = '未選択'
    if tenant_id:
        cur.execute(_sql(conn, 'SELECT 名称 FROM "T_テナント" WHERE id = %s'), (tenant_id,))
        tenant_row = cur.fetchone()
        tenant_name = tenant_row[0] if tenant_row else '不明'
    
    # テナントリストを取得（テナント管理者が管理するテナント）
    cur.execute(_sql(conn, '''
        SELECT DISTINCT t.id, t.名称
        FROM "T_テナント" t
        INNER JOIN "T_管理者" a ON a.tenant_id = t.id
        WHERE a.id = %s AND a.role = %s
        ORDER BY t.名称
    '''), (user_id, ROLES["TENANT_ADMIN"]))
    tenant_list = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    
    # 店舗リストを取得（テナント管理者が管理するテナントの店舗）
    store_list = []
    if tenant_list:
        tenant_ids = [t['id'] for t in tenant_list]
        placeholders = ','.join(['%s'] * len(tenant_ids))
        cur.execute(_sql(conn, f'''
            SELECT id, 名称
            FROM "T_店舗"
            WHERE tenant_id IN ({placeholders})
            ORDER BY 名称
        '''), tenant_ids)
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
                return render_template('tenant_mypage.html', user=user, tenant_name=tenant_name, tenant_list=tenant_list, store_list=store_list)
            
            # ログインID重複チェック（自分以外）
            cur.execute(_sql(conn, 'SELECT id FROM "T_管理者" WHERE login_id = %s AND id != %s'), (login_id, user_id))
            if cur.fetchone():
                conn.close()
                flash('このログインIDは既に使用されています', 'error')
                return render_template('tenant_mypage.html', user=user, tenant_name=tenant_name, tenant_list=tenant_list, store_list=store_list)
            
            # プロフィール更新
            cur.execute(_sql(conn, '''
                UPDATE "T_管理者"
                SET login_id = %s, name = %s, email = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            '''), (login_id, name, email, user_id))
            conn.commit()
            conn.close()
            
            flash('プロフィール情報を更新しました', 'success')
            return redirect(url_for('tenant_admin.mypage'))
        
        elif action == 'change_password':
            # パスワード変更
            current_password = request.form.get('current_password', '').strip()
            new_password = request.form.get('new_password', '').strip()
            new_password_confirm = request.form.get('new_password_confirm', '').strip()
        
            # パスワード一致チェック
            if new_password != new_password_confirm:
                flash('パスワードが一致しません', 'error')
                conn.close()
                return render_template('tenant_mypage.html', user=user, tenant_name=tenant_name, tenant_list=tenant_list, store_list=store_list)
            
            # 現在のパスワードを確認
            cur.execute(_sql(conn, 'SELECT password_hash FROM "T_管理者" WHERE id = %s'), (user_id,))
            row = cur.fetchone()
            if not row or not check_password_hash(row[0], current_password):
                conn.close()
                flash('現在のパスワードが正しくありません', 'error')
                return render_template('tenant_mypage.html', user=user, tenant_name=tenant_name, tenant_list=tenant_list, store_list=store_list)
            
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
            return redirect(url_for('tenant_admin.mypage'))
    
    conn.close()
    return render_template('tenant_mypage.html', user=user, tenant_name=tenant_name, tenant_list=tenant_list, store_list=store_list)


@bp.route('/mypage/select_tenant', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def select_tenant_from_mypage():
    """マイページからテナントを選択してダッシュボードへ進む"""
    tenant_id = request.form.get('tenant_id')
    
    if not tenant_id:
        flash('テナントを選択してください', 'error')
        return redirect(url_for('tenant_admin.mypage'))
    
    # テナントIDをセッションに保存
    session['tenant_id'] = int(tenant_id)
    flash('テナントを選択しました', 'success')
    
    return redirect(url_for('tenant_admin.dashboard'))


@bp.route('/mypage/select_store', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def select_store_from_mypage():
    """マイページから店舗を選択して店舗ダッシュボードへ進む"""
    store_id = request.form.get('store_id')
    
    if not store_id:
        flash('店舗を選択してください', 'error')
        return redirect(url_for('tenant_admin.mypage'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 店舗情報を取得
    cur.execute(_sql(conn, 'SELECT tenant_id, 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    
    if not store_row:
        flash('店舗が見つかりません', 'error')
        conn.close()
        return redirect(url_for('tenant_admin.mypage'))
    
    tenant_id = store_row[0]
    store_name = store_row[1]
    
    # テナント名を取得
    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_テナント" WHERE id = %s'), (tenant_id,))
    tenant_row = cur.fetchone()
    tenant_name = tenant_row[0] if tenant_row else '不明'
    
    conn.close()
    
    # セッションに店舗情報を保存
    session['store_id'] = int(store_id)
    session['tenant_id'] = tenant_id
    session['store_name'] = store_name
    session['tenant_name'] = tenant_name
    
    flash(f'{store_name} を選択しました', 'success')
    
    return redirect(url_for('admin.dashboard'))


@bp.route('/tenant_apps')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_apps():
    """テナントアプリ一覧"""
    tenant_id = session.get('tenant_id')
    
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # テナント情報を取得
    cur.execute(_sql(conn, 'SELECT id, 名称, slug, created_at FROM "T_テナント" WHERE id = %s'), (tenant_id,))
    tenant_row = cur.fetchone()
    
    if not tenant_row:
        flash('テナント情報が見つかりません', 'error')
        conn.close()
        return redirect(url_for('tenant_admin.dashboard'))
    
    tenant = {
        'id': tenant_row[0],
        '名称': tenant_row[1],
        'slug': tenant_row[2],
        'created_at': tenant_row[3]
    }
    
    # TODO: テナントに紐付くアプリを取得する実装
    # 現時点では空のリストを返す
    apps = []
    
    conn.close()
    
    return render_template('tenant_apps.html', tenant=tenant, apps=apps)


# ============================================================
# アプリ管理（テナント管理者用）
# ============================================================

# 利用可能なアプリ一覧（現在は空）
# 将来的にアプリを追加する場合は、以下の形式で追加してください：
# {'name': 'app-name', 'display_name': 'アプリ表示名', 'scope': 'store'/'tenant'}
AVAILABLE_APPS = []

@bp.route('/app_management', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def app_management():
    """店舗別アプリ設定（テナント管理者用）"""
    user_id = session.get('user_id')
    user_role = session.get('role')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # テナント管理者が管理できるテナント一覧を取得
    if user_role == ROLES["SYSTEM_ADMIN"]:
        # システム管理者は全テナントにアクセス可能
        cur.execute(_sql(conn, '''
            SELECT id, "名称"
            FROM "T_テナント"
            WHERE "有効" = 1
            ORDER BY id
        '''))
    else:
        # テナント管理者は自分が管理するテナントのみ
        cur.execute(_sql(conn, '''
            SELECT DISTINCT t.id, t."名称"
            FROM "T_テナント" t
            INNER JOIN "T_テナント管理者_テナント" tt ON t.id = tt.tenant_id
            WHERE tt.tenant_admin_id = %s AND t."有効" = 1
            ORDER BY t.id
        '''), (user_id,))
    tenants = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    
    selected_tenant_id = None
    selected_store_id = None
    stores = []
    store_apps = []
    
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        if action == 'select_tenant':
            # テナント選択
            selected_tenant_id = request.form.get('tenant_id', type=int)
            
            # 権限チェック
            if user_role != ROLES["SYSTEM_ADMIN"]:
                cur.execute(_sql(conn, '''
                    SELECT COUNT(*) FROM "T_テナント管理者_テナント"
                    WHERE tenant_admin_id = %s AND tenant_id = %s
                '''), (user_id, selected_tenant_id))
                if cur.fetchone()[0] == 0:
                    conn.close()
                    flash('このテナントを管理する権限がありません', 'error')
                    return redirect(url_for('tenant_admin.app_management'))
            
            if selected_tenant_id:
                # 店舗一覧を取得
                cur.execute(_sql(conn, '''
                    SELECT id, "名称" FROM "T_店舗"
                    WHERE tenant_id = %s AND "有効" = 1
                    ORDER BY id
                '''), (selected_tenant_id,))
                stores = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
        
        elif action == 'select_store':
            # 店舗選択
            selected_tenant_id = request.form.get('tenant_id', type=int)
            selected_store_id = request.form.get('store_id', type=int)
            
            # 権限チェック
            if user_role != ROLES["SYSTEM_ADMIN"]:
                cur.execute(_sql(conn, '''
                    SELECT COUNT(*) FROM "T_テナント管理者_テナント"
                    WHERE tenant_admin_id = %s AND tenant_id = %s
                '''), (user_id, selected_tenant_id))
                if cur.fetchone()[0] == 0:
                    conn.close()
                    flash('このテナントを管理する権限がありません', 'error')
                    return redirect(url_for('tenant_admin.app_management'))
            
            if selected_tenant_id:
                cur.execute(_sql(conn, '''
                    SELECT id, "名称" FROM "T_店舗"
                    WHERE tenant_id = %s AND "有効" = 1
                    ORDER BY id
                '''), (selected_tenant_id,))
                stores = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
            
            if selected_store_id:
                # 店舗がテナントに属しているか確認
                cur.execute(_sql(conn, '''
                    SELECT tenant_id FROM "T_店舗" WHERE id = %s
                '''), (selected_store_id,))
                row = cur.fetchone()
                if not row or row[0] != selected_tenant_id:
                    conn.close()
                    flash('この店舗を管理する権限がありません', 'error')
                    return redirect(url_for('tenant_admin.app_management'))
                
                # 店舗単位のアプリ一覧を取得
                store_apps_data = {}
                for app in AVAILABLE_APPS:
                    if app['scope'] == 'store':
                        cur.execute(_sql(conn, '''
                            SELECT enabled FROM "T_店舗アプリ設定"
                            WHERE store_id = %s AND app_name = %s
                        '''), (selected_store_id, app['name']))
                        row = cur.fetchone()
                        enabled = row[0] if row else 1  # デフォルトは有効
                        store_apps_data[app['name']] = enabled
                
                store_apps = [
                    {
                        'name': app['name'],
                        'display_name': app['display_name'],
                        'enabled': store_apps_data.get(app['name'], 1)
                    }
                    for app in AVAILABLE_APPS if app['scope'] == 'store'
                ]
        
        elif action == 'update_apps':
            # アプリ設定更新
            selected_tenant_id = request.form.get('tenant_id', type=int)
            selected_store_id = request.form.get('store_id', type=int)
            
            # 権限チェック
            if user_role != ROLES["SYSTEM_ADMIN"]:
                cur.execute(_sql(conn, '''
                    SELECT COUNT(*) FROM "T_テナント管理者_テナント"
                    WHERE tenant_admin_id = %s AND tenant_id = %s
                '''), (user_id, selected_tenant_id))
                if cur.fetchone()[0] == 0:
                    conn.close()
                    flash('このテナントを管理する権限がありません', 'error')
                    return redirect(url_for('tenant_admin.app_management'))
            
            if selected_tenant_id:
                cur.execute(_sql(conn, '''
                    SELECT id, "名称" FROM "T_店舗"
                    WHERE tenant_id = %s AND "有効" = 1
                    ORDER BY id
                '''), (selected_tenant_id,))
                stores = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
            
            if selected_store_id:
                # 店舗がテナントに属しているか確認
                cur.execute(_sql(conn, '''
                    SELECT tenant_id FROM "T_店舗" WHERE id = %s
                '''), (selected_store_id,))
                row = cur.fetchone()
                if not row or row[0] != selected_tenant_id:
                    conn.close()
                    flash('この店舗を管理する権限がありません', 'error')
                    return redirect(url_for('tenant_admin.app_management'))
                
                for app in AVAILABLE_APPS:
                    if app['scope'] == 'store':
                        enabled = 1 if request.form.get(f'app_{app["name"]}') == 'on' else 0
                        
                        # UPSERT処理
                        cur.execute(_sql(conn, '''
                            SELECT id FROM "T_店舗アプリ設定"
                            WHERE store_id = %s AND app_name = %s
                        '''), (selected_store_id, app['name']))
                        
                        if cur.fetchone():
                            # 更新
                            cur.execute(_sql(conn, '''
                                UPDATE "T_店舗アプリ設定"
                                SET enabled = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE store_id = %s AND app_name = %s
                            '''), (enabled, selected_store_id, app['name']))
                        else:
                            # 挿入
                            cur.execute(_sql(conn, '''
                                INSERT INTO "T_店舗アプリ設定" (store_id, app_name, enabled)
                                VALUES (%s, %s, %s)
                            '''), (selected_store_id, app['name'], enabled))
                
                conn.commit()
                flash('店舗のアプリ設定を更新しました', 'success')
                
                # 更新後のデータを再取得
                store_apps_data = {}
                for app in AVAILABLE_APPS:
                    if app['scope'] == 'store':
                        cur.execute(_sql(conn, '''
                            SELECT enabled FROM "T_店舗アプリ設定"
                            WHERE store_id = %s AND app_name = %s
                        '''), (selected_store_id, app['name']))
                        row = cur.fetchone()
                        enabled = row[0] if row else 1
                        store_apps_data[app['name']] = enabled
                
                store_apps = [
                    {
                        'name': app['name'],
                        'display_name': app['display_name'],
                        'enabled': store_apps_data.get(app['name'], 1)
                    }
                    for app in AVAILABLE_APPS if app['scope'] == 'store'
                ]
    
    conn.close()
    
    return render_template('tenant_admin_app_management.html',
                         tenants=tenants,
                         stores=stores,
                         selected_tenant_id=selected_tenant_id,
                         selected_store_id=selected_store_id,
                         store_apps=store_apps)
