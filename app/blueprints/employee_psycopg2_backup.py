"""
従業員マイページ
"""

from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from ..utils import require_roles, ROLES
from ..utils.db import get_db_connection, _sql

bp = Blueprint('employee', __name__, url_prefix='/employee')


@bp.route('/dashboard')
@require_roles(ROLES["EMPLOYEE"], ROLES["SYSTEM_ADMIN"])
def dashboard():
    """従業員ダッシュボード"""
    return render_template('employee_dashboard.html')


@bp.route('/mypage', methods=['GET', 'POST'])
@require_roles(ROLES["EMPLOYEE"], ROLES["SYSTEM_ADMIN"])
def mypage():
    """従業員マイページ"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    # ユーザー情報を取得
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, email, created_at, updated_at
        FROM "T_従業員"
        WHERE id = %s
    '''), (user_id,))
    
    row = cur.fetchone()
    
    if not row:
        flash('ユーザー情報が見つかりません', 'error')
        conn.close()
        return redirect(url_for('employee.dashboard'))
    
    user = {
        'id': row[0],
        'login_id': row[1],
        'name': row[2],
        'email': row[3],
        'created_at': row[4],
        'updated_at': row[5]
    }
    
    # テナント名を取得
    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_テナント" WHERE id = %s'), (tenant_id,))
    tenant_row = cur.fetchone()
    tenant_name = tenant_row[0] if tenant_row else '不明'
    
    # 所属店舗を取得（表示用）
    cur.execute(_sql(conn, '''
        SELECT s.名称
        FROM "T_店舗" s
        INNER JOIN "T_従業員_店舗" es ON s.id = es.store_id
        WHERE es.employee_id = %s
    '''), (user_id,))
    stores = [row[0] for row in cur.fetchall()]
    
    # 所属店舗を取得（選択用）
    cur.execute(_sql(conn, '''
        SELECT s.id, s.名称
        FROM "T_店舗" s
        INNER JOIN "T_従業員_店舗" es ON s.id = es.store_id
        WHERE es.employee_id = %s
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
                return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
            
            # ログインID重複チェック（自分以外）
            cur.execute(_sql(conn, 'SELECT id FROM "T_従業員" WHERE login_id = %s AND id != %s'), (login_id, user_id))
            if cur.fetchone():
                conn.close()
                flash('このログインIDは既に使用されています', 'error')
                return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
            
            # プロフィール更新
            cur.execute(_sql(conn, '''
                UPDATE "T_従業員"
                SET login_id = %s, name = %s, email = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            '''), (login_id, name, email, user_id))
            conn.commit()
            conn.close()
            
            flash('プロフィール情報を更新しました', 'success')
            return redirect(url_for('employee.mypage'))
        
        elif action == 'change_password':
            # パスワード変更
            current_password = request.form.get('current_password', '').strip()
            new_password = request.form.get('new_password', '').strip()
            new_password_confirm = request.form.get('new_password_confirm', '').strip()
            
            # パスワード一致チェック
            if new_password != new_password_confirm:
                flash('パスワードが一致しません', 'error')
                conn.close()
                return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
            
            # 現在のパスワードを確認
            cur.execute(_sql(conn, 'SELECT password_hash FROM "T_従業員" WHERE id = %s'), (user_id,))
            row = cur.fetchone()
            if not row or not check_password_hash(row[0], current_password):
                conn.close()
                flash('現在のパスワードが正しくありません', 'error')
                return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
            
            # パスワードを更新
            password_hash = generate_password_hash(new_password)
            cur.execute(_sql(conn, '''
                UPDATE "T_従業員"
                SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            '''), (password_hash, user_id))
            conn.commit()
            conn.close()
            
            flash('パスワードを変更しました', 'success')
            return redirect(url_for('employee.mypage'))
    
    conn.close()
    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)


@bp.route('/select_store_from_mypage', methods=['POST'])
@require_roles(ROLES["EMPLOYEE"], ROLES["SYSTEM_ADMIN"])
def select_store_from_mypage():
    """マイページから店舗を選択してダッシュボードに進む"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    store_id = request.form.get('store_id')
    
    if not store_id:
        flash('店舗を選択してください', 'error')
        return redirect(url_for('employee.mypage'))
    
    # 従業員が選択した店舗に所属しているか確認
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(_sql(conn, '''
        SELECT COUNT(*) FROM "T_従業員_店舗"
        WHERE employee_id = %s AND store_id = %s
    '''), (user_id, store_id))
    
    count = cur.fetchone()[0]
    conn.close()
    
    if count == 0:
        flash('選択した店舗にアクセスする権限がありません', 'error')
        return redirect(url_for('employee.mypage'))
    
    # セッションに店舗IDを保存
    session['store_id'] = int(store_id)
    
    flash('店舗を選択しました', 'success')
    return redirect(url_for('employee.dashboard'))
