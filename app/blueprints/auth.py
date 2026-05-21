# -*- coding: utf-8 -*-
"""
認証関連ルート
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from ..utils import (
    get_db, _sql, login_user, admin_exists, ROLES,
    validate_csrf, lockout_remaining, record_failure, clear_login_attempts,
)

bp = Blueprint('auth', __name__)


@bp.route('/')
def index():
    """トップページ - ロール別リダイレクト"""
    role = session.get("role")
    if role == ROLES["SYSTEM_ADMIN"]:
        return redirect(url_for('system_admin.mypage'))
    if role == ROLES["TENANT_ADMIN"]:
        return redirect(url_for('tenant_admin.dashboard'))
    if role == ROLES["APP_MANAGER"]:
        return redirect(url_for('app_manager.dashboard'))
    if role == ROLES["ADMIN"]:
        return redirect(url_for('admin.dashboard'))
    if role == ROLES["EMPLOYEE"]:
        return redirect(url_for('employee.mypage'))
    return redirect(url_for('auth.select_login'))


@bp.route('/select_login')
def select_login():
    """ログイン選択画面"""
    # 管理者が未作成なら、初回セットアップへ誘導
    if not admin_exists():
        return redirect(url_for('auth.first_admin_setup'))
    return render_template('login_choice.html')


@bp.route('/first_admin_setup', methods=['GET', 'POST'])
def first_admin_setup():
    """初回セットアップ（最初の sysadmin 作成）"""
    # すでに管理者がいれば、このページは出さない
    if admin_exists():
        return redirect(url_for('auth.select_login'))

    error = None
    if request.method == 'POST':
        # --- CSRF チェック（定数時間比較） ---
        if not validate_csrf():
            error = "セッションが無効です。もう一度お試しください。"
        else:
            name = (request.form.get('name') or '').strip()
            login_id = (request.form.get('login_id') or '').strip()
            email = (request.form.get('email') or '').strip()
            password = request.form.get('password') or ''
            confirm = request.form.get('confirm') or ''

            # --- 入力バリデーション ---
            if not name or not login_id or not email or not password or not confirm:
                error = "すべての項目を入力してください。"
            elif len(password) < 8:
                error = "パスワードは8文字以上にしてください。"
            elif password != confirm:
                error = "パスワード（確認）が一致しません。"

            if not error:
                # 既存重複確認 & 作成
                conn = get_db()
                try:
                    cur = conn.cursor()
                    # 同じ login_id が無いか
                    sql_chk = _sql(conn, 'SELECT 1 FROM "T_管理者" WHERE login_id=%s')
                    cur.execute(sql_chk, (login_id,))
                    exists = cur.fetchone()
                    if exists:
                        error = "このログインIDはすでに使用されています。"
                    else:
                        ph = generate_password_hash(password)
                        sql_ins = _sql(conn, '''
                            INSERT INTO "T_管理者"(login_id, name, email, password_hash, role, tenant_id, is_owner, can_manage_admins)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ''')
                        cur.execute(sql_ins, (login_id, name, email, ph, ROLES["SYSTEM_ADMIN"], None, 1, 1))
                        from ..utils.db import _is_pg
                        if not _is_pg(conn):
                            conn.commit()
                        flash("システム管理者を作成しました。ログインできます。", "success")
                        return redirect(url_for('auth.select_login'))
                finally:
                    try:
                        conn.close()
                    except:
                        pass

    return render_template('first_setup.html', error=error)


@bp.route('/system_admin_login', methods=['GET','POST'])
def system_admin_login():
    """システム管理者ログイン"""
    error = None
    if request.method == 'POST':
        if not validate_csrf():
            error = "セッションが無効です。ページを再読み込みしてもう一度お試しください。"
            return render_template('sysadmin_login.html', error=error)
        login_id = request.form.get('login_id','').strip()
        password = request.form.get('password','')
        rl_key = 'system_admin:' + login_id.lower()
        wait = lockout_remaining(rl_key)
        if wait:
            error = f"ログイン試行が多すぎます。約{(wait + 59) // 60}分後に再度お試しください。"
            return render_template('sysadmin_login.html', error=error)
        conn = get_db()
        try:
            cur = conn.cursor()
            sql = _sql(conn, 'SELECT id, name, password_hash, tenant_id, is_owner FROM "T_管理者" WHERE login_id=%s AND role=%s AND COALESCE(active, 1)=1')
            cur.execute(sql, (login_id, ROLES["SYSTEM_ADMIN"]))
            row = cur.fetchone()
            if row and check_password_hash(row[2], password):
                clear_login_attempts(rl_key)
                user_id, name, tenant_id, is_owner = row[0], row[1], row[3], row[4]
                login_user(user_id, name, ROLES["SYSTEM_ADMIN"], tenant_id)
                session['is_owner'] = (is_owner == 1)
                return redirect(url_for('system_admin.mypage'))
            record_failure(rl_key)
            error = "ログインIDまたはパスワードが違います"
        finally:
            try: conn.close()
            except: pass
    return render_template('sysadmin_login.html', error=error)


@bp.route('/tenant_admin_login', methods=['GET','POST'])
def tenant_admin_login():
    """テナント管理者ログイン"""
    error = None
    if request.method == 'POST':
        if not validate_csrf():
            error = "セッションが無効です。ページを再読み込みしてもう一度お試しください。"
            return render_template('tenant_admin_login.html', error=error)
        login_id = request.form.get('login_id','').strip()
        password = request.form.get('password','')
        rl_key = 'tenant_admin:' + login_id.lower()
        wait = lockout_remaining(rl_key)
        if wait:
            error = f"ログイン試行が多すぎます。約{(wait + 59) // 60}分後に再度お試しください。"
            return render_template('tenant_admin_login.html', error=error)
        conn = get_db()
        try:
            cur = conn.cursor()
            sql = _sql(conn, 'SELECT id, name, password_hash, tenant_id, is_owner FROM "T_管理者" WHERE login_id=%s AND role=%s AND COALESCE(active, 1)=1')
            cur.execute(sql, (login_id, ROLES["TENANT_ADMIN"]))
            row = cur.fetchone()
            if row and check_password_hash(row[2], password):
                clear_login_attempts(rl_key)
                user_id, name, tenant_id, is_owner = row[0], row[1], row[3], row[4]
                login_user(user_id, name, ROLES["TENANT_ADMIN"], tenant_id)
                session['is_owner'] = (is_owner == 1)
                return redirect(url_for('tenant_admin.mypage'))
            else:
                record_failure(rl_key)
                error = "ログインIDまたはパスワードが違います"
        finally:
            try: conn.close()
            except: pass
    return render_template('tenant_admin_login.html', error=error)


@bp.route('/admin_login', methods=['GET','POST'])
def admin_login():
    """管理者ログイン"""
    error = None
    if request.method == 'POST':
        if not validate_csrf():
            error = "セッションが無効です。ページを再読み込みしてもう一度お試しください。"
            return render_template('store_login.html', error=error)
        login_id = request.form.get('login_id','').strip()
        password = request.form.get('password','')
        rl_key = 'admin:' + login_id.lower()
        wait = lockout_remaining(rl_key)
        if wait:
            error = f"ログイン試行が多すぎます。約{(wait + 59) // 60}分後に再度お試しください。"
            return render_template('store_login.html', error=error)
        conn = get_db()
        try:
            cur = conn.cursor()
            sql = _sql(conn, 'SELECT id, name, password_hash, tenant_id, is_owner FROM "T_管理者" WHERE login_id=%s AND role=%s AND COALESCE(active, 1)=1')
            cur.execute(sql, (login_id, ROLES["ADMIN"]))
            row = cur.fetchone()
            if row and check_password_hash(row[2], password):
                clear_login_attempts(rl_key)
                user_id, name, tenant_id, is_owner = row[0], row[1], row[3], row[4]
                if not tenant_id:
                    error = "この管理者にはテナントが紐づいていません。"
                else:
                    login_user(user_id, name, ROLES["ADMIN"], tenant_id)
                    session['store_id'] = None  # 店舗未選択
                    session['is_owner'] = (is_owner == 1)
                    return redirect(url_for('admin.mypage'))
            else:
                record_failure(rl_key)
                error = "ログインIDまたはパスワードが違います"
        finally:
            try: conn.close()
            except: pass
    return render_template('store_login.html', error=error)


@bp.route('/employee_login', methods=['GET','POST'])
def employee_login():
    """従業員ログイン"""
    error = None
    if request.method == 'POST':
        if not validate_csrf():
            error = "セッションが無効です。ページを再読み込みしてもう一度お試しください。"
            return render_template('staff_login.html', error=error)
        login_id = request.form.get('login_id','').strip()  # email でも login_id でもOK
        password = request.form.get('password','')
        rl_key = 'employee:' + login_id.lower()
        wait = lockout_remaining(rl_key)
        if wait:
            error = f"ログイン試行が多すぎます。約{(wait + 59) // 60}分後に再度お試しください。"
            return render_template('staff_login.html', error=error)
        conn = get_db()
        try:
            cur = conn.cursor()
            sql = _sql(conn, 'SELECT id, name, password_hash, tenant_id FROM "T_従業員" WHERE (login_id=%s OR email=%s) AND COALESCE(active, 1)=1')
            cur.execute(sql, (login_id, login_id))
            row = cur.fetchone()
            if row:
                user_id, name, hashv, tenant_id = row[0], row[1], row[2], row[3]
                if hashv and check_password_hash(hashv, password):
                    clear_login_attempts(rl_key)
                    login_user(user_id, name, ROLES["EMPLOYEE"], tenant_id, is_employee=True)
                    session['store_id'] = None  # 店舗未選択
                    return redirect(url_for('employee.mypage'))
            record_failure(rl_key)
            error = "ログインIDまたはパスワードが違います"
        finally:
            try: conn.close()
            except: pass
    return render_template('staff_login.html', error=error)


@bp.route('/staff_login', methods=['GET','POST'])
def staff_login():
    """既存互換：従業員ログイン（/staff_login）"""
    return redirect(url_for('auth.employee_login'))


@bp.route('/logout')
def logout():
    """ログアウト"""
    session.clear()
    return redirect(url_for('auth.select_login'))


# ========================================
# ルートエイリアス（元のapp.pyとの互換性）
# ========================================

@bp.route('/system_admin')
def system_admin_redirect():
    """元のapp.pyとの互換性のため /system_admin → /system_admin/ へリダイレクト"""
    return redirect(url_for('system_admin.mypage'))


@bp.route('/tenant_admin')
def tenant_admin_redirect():
    """元のapp.pyとの互換性のため /tenant_admin → /tenant_admin/ へリダイレクト"""
    return redirect(url_for('tenant_admin.dashboard'))


@bp.route('/admin')
def admin_redirect():
    """元のapp.pyとの互換性のため /admin → /admin/ へリダイレクト"""
    return redirect(url_for('admin.dashboard'))
