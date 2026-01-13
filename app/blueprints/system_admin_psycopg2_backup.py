# -*- coding: utf-8 -*-
"""
システム管理者ダッシュボード
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file
from ..utils import require_roles, ROLES, get_db_connection, is_owner, can_manage_system_admins
from ..utils.db import _sql
from werkzeug.security import generate_password_hash, check_password_hash
import os
import markdown

bp = Blueprint('system_admin', __name__, url_prefix='/system_admin')


@bp.route('/')
@require_roles(ROLES["SYSTEM_ADMIN"])
def dashboard():
    """システム管理者ダッシュボード"""
    return render_template('system_admin_dashboard.html')


@bp.route('/settings', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def settings():
    """システム設定"""
    user_id = session.get('user_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        openai_api_key = request.form.get('openai_api_key', '').strip()
        
        # OpenAI APIキーを更新
        cur.execute(_sql(conn, '''
            UPDATE "T_管理者"
            SET openai_api_key = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        '''), (openai_api_key, user_id))
        conn.commit()
        
        flash('システム設定を更新しました', 'success')
    
    # 現在の設定を取得
    cur.execute(_sql(conn, '''
        SELECT openai_api_key
        FROM "T_管理者"
        WHERE id = %s
    '''), (user_id,))
    
    row = cur.fetchone()
    conn.close()
    
    settings_data = {
        'openai_api_key': row[0] if row and row[0] else ''
    }
    
    return render_template('sys_settings.html', settings=settings_data)


@bp.route('/docs')
@require_roles(ROLES["SYSTEM_ADMIN"])
def docs():
    """ドキュメント一覧"""
    docs_list = [
        {
            'title': '移植ガイド',
            'description': 'login-system-appを基盤として新しいビジネスアプリケーションを開発するための詳細な手順書',
            'filename': 'MIGRATION_GUIDE.md',
            'url': 'system_admin.doc_view'
        },
        {
            'title': 'AVAILABLE_APPSの定義方法',
            'description': '新しいビジネスアプリケーションを追加する際のAVAILABLE_APPSの定義方法',
            'filename': 'AVAILABLE_APPS_GUIDE.md',
            'url': 'system_admin.doc_view'
        }
    ]
    return render_template('sys_docs.html', docs=docs_list)


@bp.route('/docs/<filename>')
@require_roles(ROLES["SYSTEM_ADMIN"])
def doc_view(filename):
    """ドキュメント閲覧"""
    # セキュリティ: ファイル名のバリデーション
    allowed_files = ['MIGRATION_GUIDE.md', 'AVAILABLE_APPS_GUIDE.md', 'README.md']
    if filename not in allowed_files:
        flash('指定されたドキュメントは存在しません', 'error')
        return redirect(url_for('system_admin.docs'))
    
    # ドキュメントファイルのパスを取得
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    doc_path = os.path.join(base_dir, 'docs', filename)
    
    # ファイルが存在しない場合
    if not os.path.exists(doc_path):
        flash('ドキュメントファイルが見つかりません', 'error')
        return redirect(url_for('system_admin.docs'))
    
    # Markdownファイルを読み込んでHTMLに変換
    with open(doc_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code', 'codehilite'])
    
    # タイトルを取得（最初の#行）
    title = filename.replace('.md', '')
    for line in md_content.split('\n'):
        if line.startswith('# '):
            title = line.replace('# ', '').strip()
            break
    
    return render_template('sys_doc_view.html', title=title, content=html_content, filename=filename)


@bp.route('/docs/<filename>/download')
@require_roles(ROLES["SYSTEM_ADMIN"])
def doc_download(filename):
    """ドキュメントダウンロード"""
    # セキュリティ: ファイル名のバリデーション
    allowed_files = ['MIGRATION_GUIDE.md', 'AVAILABLE_APPS_GUIDE.md', 'README.md']
    if filename not in allowed_files:
        flash('指定されたドキュメントは存在しません', 'error')
        return redirect(url_for('system_admin.docs'))
    
    # ドキュメントファイルのパスを取得
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    doc_path = os.path.join(base_dir, 'docs', filename)
    
    # ファイルが存在しない場合
    if not os.path.exists(doc_path):
        flash('ドキュメントファイルが見つかりません', 'error')
        return redirect(url_for('system_admin.docs'))
    
    return send_file(doc_path, as_attachment=True, download_name=filename)


# ========================================
# テナント管理
# ========================================

@bp.route('/tenants')
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenants():
    """テナント一覧"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT id, 名称, slug, 有効 FROM "T_テナント" ORDER BY id'))
    tenants = []
    for row in cur.fetchall():
        tenants.append({
            'id': row[0],
            '名称': row[1],
            'slug': row[2],
            '有効': row[3]
        })
    conn.close()
    return render_template('sys_tenants.html', tenants=tenants)


@bp.route('/tenants/<int:tid>')
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_detail(tid):
    """テナント詳細"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # テナント情報を取得
    cur.execute(_sql(conn, 'SELECT id, 名称, slug, 有効, created_at FROM "T_テナント" WHERE id = %s'), (tid,))
    row = cur.fetchone()
    
    if not row:
        flash('テナントが見つかりません', 'error')
        conn.close()
        return redirect(url_for('system_admin.tenants'))
    
    tenant = {
        'id': row[0],
        '名称': row[1],
        'slug': row[2],
        '有効': row[3],
        'created_at': row[4]
    }
    
    # テナント管理者数を取得
    cur.execute(_sql(conn, 'SELECT COUNT(*) FROM "T_管理者" WHERE tenant_id = %s AND role = %s'),
               (tid, ROLES["TENANT_ADMIN"]))
    admin_count = cur.fetchone()[0]
    
    conn.close()
    
    return render_template('sys_tenant_detail.html', 
                         tenant=tenant,
                         admin_count=admin_count)


@bp.route('/tenants/new', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_new():
    """テナント新規作成"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        
        if not name or not slug:
            flash('名称とslugは必須です', 'error')
            return render_template('sys_tenant_new.html', name=name, slug=slug)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # slug重複チェック
        cur.execute(_sql(conn, 'SELECT id FROM "T_テナント" WHERE slug = %s'), (slug,))
        if cur.fetchone():
            flash(f'slug "{slug}" は既に使用されています', 'error')
            conn.close()
            return render_template('sys_tenant_new.html', name=name, slug=slug)
        
        # テナント作成
        cur.execute(_sql(conn, '''
            INSERT INTO "T_テナント" (名称, slug, 有効)
            VALUES (%s, %s, 1)
        '''), (name, slug))
        conn.commit()
        conn.close()
        
        flash(f'テナント "{name}" を作成しました', 'success')
        return redirect(url_for('system_admin.tenants'))
    
    return render_template('sys_tenant_new.html')


@bp.route('/tenants/<int:tid>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_edit(tid):
    """テナント編集"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        active = int(request.form.get('active', 1))
        
        if not name or not slug:
            flash('名称とslugは必須です', 'error')
        else:
            # slug重複チェック（自分以外）
            cur.execute(_sql(conn, 'SELECT id FROM "T_テナント" WHERE slug = %s AND id != %s'), (slug, tid))
            if cur.fetchone():
                flash(f'slug "{slug}" は既に使用されています', 'error')
            else:
                cur.execute(_sql(conn, '''
                    UPDATE "T_テナント"
                    SET 名称 = %s, slug = %s, 有効 = %s
                    WHERE id = %s
                '''), (name, slug, active, tid))
                conn.commit()
                flash('テナント情報を更新しました', 'success')
                conn.close()
                return redirect(url_for('system_admin.tenants'))
    
    # テナント情報取得
    cur.execute(_sql(conn, 'SELECT id, 名称, slug, 有効 FROM "T_テナント" WHERE id = %s'), (tid,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        flash('テナントが見つかりません', 'error')
        return redirect(url_for('system_admin.tenants'))
    
    tenant = {
        'id': row[0],
        '名称': row[1],
        'slug': row[2],
        '有効': row[3]
    }
    
    return render_template('sys_tenant_edit.html', tenant=tenant)


@bp.route('/tenants/<int:tid>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_delete(tid):
    """テナント削除"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # テナントに紐づく管理者がいないかチェック
    cur.execute(_sql(conn, 'SELECT COUNT(*) FROM "T_管理者" WHERE tenant_id = %s'), (tid,))
    count = cur.fetchone()[0]
    
    if count > 0:
        flash('このテナントには管理者が紐づいているため削除できません', 'error')
    else:
        cur.execute(_sql(conn, 'DELETE FROM "T_テナント" WHERE id = %s'), (tid,))
        conn.commit()
        flash('テナントを削除しました', 'success')
    
    conn.close()
    return redirect(url_for('system_admin.tenants'))


# ========================================
# テナント管理者管理
# ========================================

@bp.route('/tenants/<int:tid>/admins')
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admins(tid):
    """テナント管理者一覧"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # テナント情報取得
    cur.execute(_sql(conn, 'SELECT id, 名称, slug FROM "T_テナント" WHERE id = %s'), (tid,))
    tenant_row = cur.fetchone()
    
    if not tenant_row:
        flash('テナントが見つかりません', 'error')
        conn.close()
        return redirect(url_for('system_admin.tenants'))
    
    tenant = {
        'id': tenant_row[0],
        '名称': tenant_row[1],
        'slug': tenant_row[2]
    }
    
    # テナント管理者一覧取得
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, active
        FROM "T_管理者"
        WHERE tenant_id = %s AND role = %s
        ORDER BY id
    '''), (tid, ROLES["TENANT_ADMIN"]))
    
    admins = []
    for row in cur.fetchall():
        admins.append({
            'id': row[0],
            'login_id': row[1],
            'name': row[2],
            'active': row[3]
        })
    
    conn.close()
    return render_template('sys_tenant_admins.html', tenant=tenant, admins=admins)


@bp.route('/tenants/<int:tid>/admins/new', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admin_new(tid):
    """テナント管理者新規作成"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # テナント情報取得
    cur.execute(_sql(conn, 'SELECT id, 名称, slug FROM "T_テナント" WHERE id = %s'), (tid,))
    tenant_row = cur.fetchone()
    
    if not tenant_row:
        flash('テナントが見つかりません', 'error')
        conn.close()
        return redirect(url_for('system_admin.tenants'))
    
    tenant = {
        'id': tenant_row[0],
        '名称': tenant_row[1],
        'slug': tenant_row[2]
    }
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        active = int(request.form.get('active', 1))
        
        # バリデーション
        if not login_id or not name or not password:
            flash('ログインID、氏名、パスワードは必須です', 'error')
            conn.close()
            return render_template('sys_tenant_admin_new.html', tenant=tenant)
        
        if password != password_confirm:
            flash('パスワードが一致しません', 'error')
            conn.close()
            return render_template('sys_tenant_admin_new.html', tenant=tenant)
        
        if len(password) < 8:
            flash('パスワードは8文字以上にしてください', 'error')
            conn.close()
            return render_template('sys_tenant_admin_new.html', tenant=tenant)
        
        # ログインID重複チェック
        cur.execute(_sql(conn, 'SELECT id FROM "T_管理者" WHERE login_id = %s'), (login_id,))
        if cur.fetchone():
            flash(f'ログインID "{login_id}" は既に使用されています', 'error')
            conn.close()
            return render_template('sys_tenant_admin_new.html', tenant=tenant)
        
        # テナント管理者作成
        hashed_password = generate_password_hash(password)
        cur.execute(_sql(conn, '''
            INSERT INTO "T_管理者" (login_id, name, email, password_hash, role, tenant_id, active, is_owner, can_manage_admins)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''), (login_id, name, email, hashed_password, ROLES["TENANT_ADMIN"], tid, active, 1, 1))
        
        # 中間テーブルにも追加
        cur.execute(_sql(conn, 'SELECT id FROM \"T_管理者\" WHERE login_id = %s'), (login_id,))
        new_admin_id = cur.fetchone()[0]
        cur.execute(_sql(conn, '''
            INSERT INTO \"T_テナント管理者_テナント\" (tenant_admin_id, tenant_id)
            VALUES (%s, %s)
        '''), (new_admin_id, tid))
        
        conn.commit()
        conn.close()
        
        flash(f'テナント管理者 "{name}" を作成しました', 'success')
        return redirect(url_for('system_admin.tenant_admins', tid=tid))
    
    conn.close()
    return render_template('sys_tenant_admin_new.html', tenant=tenant)


@bp.route('/tenants/<int:tid>/admins/<int:admin_id>/toggle', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admin_toggle(tid, admin_id):
    """テナント管理者の有効/無効切り替え"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(_sql(conn, '''
        UPDATE "T_管理者"
        SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END
        WHERE id = %s AND tenant_id = %s AND role = %s
    '''), (admin_id, tid, ROLES["TENANT_ADMIN"]))
    
    conn.commit()
    conn.close()
    
    flash('ステータスを更新しました', 'success')
    return redirect(url_for('system_admin.tenant_admins', tid=tid))


@bp.route('/tenants/<int:tid>/admins/<int:admin_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admin_edit(tid, admin_id):
    """テナント管理者編集"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # テナント情報取得
    cur.execute(_sql(conn, 'SELECT id, 名称, slug FROM "T_テナント" WHERE id = %s'), (tid,))
    tenant_row = cur.fetchone()
    
    if not tenant_row:
        flash('テナントが見つかりません', 'error')
        conn.close()
        return redirect(url_for('system_admin.tenants'))
    
    tenant = {
        'id': tenant_row[0],
        '名称': tenant_row[1],
        'slug': tenant_row[2]
    }
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        active = 1 if request.form.get('active') == '1' else 0
        
        if not login_id or not name:
            flash('ログインIDと氏名は必須です', 'error')
        else:
            # ログインIDの重複チェック
            cur.execute(_sql(conn, 'SELECT id FROM "T_管理者" WHERE login_id = %s AND id != %s'), (login_id, admin_id))
            if cur.fetchone():
                flash('このログインIDは既に使用されています', 'error')
            else:
                if password:
                    hashed_pw = generate_password_hash(password)
                    cur.execute(_sql(conn, '''
                        UPDATE "T_管理者"
                        SET login_id = %s, name = %s, email = %s, password_hash = %s, active = %s
                        WHERE id = %s AND tenant_id = %s AND role = %s
                    '''), (login_id, name, email, hashed_pw, active, admin_id, tid, ROLES["TENANT_ADMIN"]))
                else:
                    cur.execute(_sql(conn, '''
                        UPDATE "T_管理者"
                        SET login_id = %s, name = %s, email = %s, active = %s
                        WHERE id = %s AND tenant_id = %s AND role = %s
                    '''), (login_id, name, email, active, admin_id, tid, ROLES["TENANT_ADMIN"]))
                
                conn.commit()
                conn.close()
                flash('テナント管理者を更新しました', 'success')
                return redirect(url_for('system_admin.tenant_admins', tid=tid))
    
    # GETリクエスト時は現在の情報を表示
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, email, active
        FROM "T_管理者"
        WHERE id = %s AND tenant_id = %s AND role = %s
    '''), (admin_id, tid, ROLES["TENANT_ADMIN"]))
    
    admin_row = cur.fetchone()
    conn.close()
    
    if not admin_row:
        flash('テナント管理者が見つかりません', 'error')
        return redirect(url_for('system_admin.tenant_admins', tid=tid))
    
    admin = {
        'id': admin_row[0],
        'login_id': admin_row[1],
        'name': admin_row[2],
        'email': admin_row[3],
        'active': admin_row[4]
    }
    
    return render_template('sys_tenant_admin_edit.html', tenant=tenant, admin=admin)


@bp.route('/tenants/<int:tid>/admins/<int:admin_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admin_delete(tid, admin_id):
    """テナント管理者削除"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(_sql(conn, '''
        DELETE FROM "T_管理者"
        WHERE id = %s AND tenant_id = %s AND role = %s
    '''), (admin_id, tid, ROLES["TENANT_ADMIN"]))
    
    conn.commit()
    conn.close()
    
    flash('テナント管理者を削除しました', 'success')
    return redirect(url_for('system_admin.tenant_admins', tid=tid))


# ========================================
# システム管理者管理
# ========================================

@bp.route('/system_admins')
@require_roles(ROLES["SYSTEM_ADMIN"])
def system_admins():
    """システム管理者一覧"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, active, created_at, is_owner, can_manage_admins 
        FROM "T_管理者" 
        WHERE role = %s 
        ORDER BY is_owner DESC, can_manage_admins DESC, id
    '''), (ROLES["SYSTEM_ADMIN"],))
    
    admins = []
    for row in cur.fetchall():
        admins.append({
            'id': row[0],
            'login_id': row[1],
            'name': row[2],
            'active': row[3],
            'created_at': row[4],
            'is_owner': row[5],
            'can_manage_admins': row[6]
        })
    conn.close()
    return render_template('sys_system_admins.html', admins=admins, is_owner=is_owner, can_manage_system_admins=can_manage_system_admins)


@bp.route('/system_admins/new', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def system_admin_new():
    """システム管理者新規作成（システム管理者管理権限が必要）"""
    # システム管理者管理権限チェック
    if not can_manage_system_admins():
        flash('システム管理者を作成する権限がありません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        
        # バリデーション
        if not login_id or not name or not password:
            flash('全ての項目を入力してください', 'error')
            return render_template('sys_system_admin_new.html')
        
        if password != password_confirm:
            flash('パスワードが一致しません', 'error')
            return render_template('sys_system_admin_new.html')
        
        # 重複チェック
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, 'SELECT id FROM "T_管理者" WHERE login_id = %s'), (login_id,))
        if cur.fetchone():
            flash('このログインIDは既に使用されています', 'error')
            conn.close()
            return render_template('sys_system_admin_new.html')
        
        # システム管理者作成
        password_hash = generate_password_hash(password)
        cur.execute(_sql(conn, '''
            INSERT INTO "T_管理者" (login_id, name, email, password_hash, role, tenant_id, active)
            VALUES (%s, %s, %s, %s, %s, NULL, 1)
        '''), (login_id, name, email, password_hash, ROLES["SYSTEM_ADMIN"]))
        
        conn.close()
        flash(f'システム管理者「{name}」を作成しました', 'success')
        return redirect(url_for('system_admin.system_admins'))
    
    return render_template('sys_system_admin_new.html')


@bp.route('/system_admins/<int:admin_id>/toggle', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def system_admin_toggle(admin_id):
    """システム管理者の有効/無効切り替え"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 現在の状態を取得
    cur.execute(_sql(conn, 'SELECT active, name FROM "T_管理者" WHERE id = %s AND role = %s'), 
                (admin_id, ROLES["SYSTEM_ADMIN"]))
    row = cur.fetchone()
    if not row:
        flash('システム管理者が見つかりません', 'error')
        conn.close()
        return redirect(url_for('system_admin.system_admins'))
    
    current_active = row[0]
    name = row[1]
    new_active = 0 if current_active == 1 else 1
    
    # 更新
    cur.execute(_sql(conn, 'UPDATE "T_管理者" SET active = %s WHERE id = %s'), (new_active, admin_id))
    conn.close()
    
    status = '有効' if new_active == 1 else '無効'
    flash(f'システム管理者「{name}」を{status}にしました', 'success')
    return redirect(url_for('system_admin.system_admins'))


@bp.route('/system_admins/<int:admin_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def system_admin_delete(admin_id):
    """システム管理者削除（システム管理者管理権限が必要）"""
    # システム管理者管理権限チェック
    if not can_manage_system_admins():
        flash('システム管理者を削除する権限がありません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    # 自分自身は削除できない
    if admin_id == session.get('user_id'):
        flash('自分自身は削除できません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # システム管理者の確認
    cur.execute(_sql(conn, 'SELECT name, can_manage_admins, is_owner FROM "T_管理者" WHERE id = %s AND role = %s'), 
                (admin_id, ROLES["SYSTEM_ADMIN"]))
    row = cur.fetchone()
    if not row:
        flash('システム管理者が見つかりません', 'error')
        conn.close()
        return redirect(url_for('system_admin.system_admins'))
    
    name = row[0]
    target_can_manage = row[1]
    target_is_owner = row[2]
    
    # オーナー以外の場合、同じ権限を持つユーザーは削除不可
    if not is_owner() and (target_can_manage == 1 or target_is_owner == 1):
        flash('システム管理者管理権限を持つ他のユーザーは削除できません', 'error')
        conn.close()
        return redirect(url_for('system_admin.system_admins'))
    
    # 削除
    cur.execute(_sql(conn, 'DELETE FROM "T_管理者" WHERE id = %s'), (admin_id,))
    conn.close()
    
    flash(f'システム管理者「{name}」を削除しました', 'success')
    return redirect(url_for('system_admin.system_admins'))


@bp.route('/system_admins/<int:admin_id>/transfer_ownership', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def transfer_ownership(admin_id):
    """オーナー権限を他のシステム管理者に移譲"""
    # オーナーのみ実行可能
    if not is_owner():
        flash('オーナーのみがオーナー権限を移譲できます', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    # 自分自身には移譲できない
    if admin_id == session.get('user_id'):
        flash('自分自身にオーナー権限を移譲することはできません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 移譲先がシステム管理者であることを確認
    cur.execute(_sql(conn, 'SELECT name FROM "T_管理者" WHERE id = %s AND role = %s'), 
                (admin_id, ROLES["SYSTEM_ADMIN"]))
    row = cur.fetchone()
    if not row:
        flash('移譲先のシステム管理者が見つかりません', 'error')
        conn.close()
        return redirect(url_for('system_admin.system_admins'))
    
    new_owner_name = row[0]
    
    # 全てのis_ownerを0にしてから、指定したユーザーを1にする
    cur.execute(_sql(conn, 'UPDATE "T_管理者" SET is_owner = 0 WHERE role = %s'), (ROLES["SYSTEM_ADMIN"],))
    cur.execute(_sql(conn, 'UPDATE "T_管理者" SET is_owner = 1 WHERE id = %s'), (admin_id,))
    conn.close()
    
    flash(f'オーナー権限を「{new_owner_name}」に移譲しました', 'success')
    return redirect(url_for('system_admin.system_admins'))


@bp.route('/system_admins/<int:admin_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def system_admin_edit(admin_id):
    """システム管理者編集（システム管理者管理権限が必要）"""
    # システム管理者管理権限チェック
    if not can_manage_system_admins():
        flash('システム管理者を編集する権限がありません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # システム管理者情報を取得（can_manage_adminsも取得）
    cur.execute(_sql(conn, 'SELECT id, login_id, name, email, active, can_manage_admins, is_owner FROM "T_管理者" WHERE id = %s AND role = %s'),
                (admin_id, ROLES["SYSTEM_ADMIN"]))
    row = cur.fetchone()
    if not row:
        flash('システム管理者が見つかりません', 'error')
        conn.close()
        return redirect(url_for('system_admin.system_admins'))
    
    target_can_manage = row[5]
    target_is_owner = row[6]
    
    # オーナー以外の場合、同じ権限を持つユーザーは編集不可
    if not is_owner() and (target_can_manage == 1 or target_is_owner == 1):
        flash('システム管理者管理権限を持つ他のユーザーは編集できません', 'error')
        conn.close()
        return redirect(url_for('system_admin.system_admins'))
    
    admin = {
        'id': row[0],
        'login_id': row[1],
        'name': row[2],
        'email': row[3],
        'active': row[4]
    }
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        
        # バリデーション
        if not login_id or not name:
            flash('ログインIDと氏名は必須です', 'error')
            conn.close()
            return render_template('sys_system_admin_edit.html', admin=admin)
        
        # ログインID重複チェック（自分以外）
        cur.execute(_sql(conn, 'SELECT id FROM "T_管理者" WHERE login_id = %s AND id != %s'),
                    (login_id, admin_id))
        if cur.fetchone():
            flash('このログインIDは既に使用されています', 'error')
            conn.close()
            return render_template('sys_system_admin_edit.html', admin=admin)
        
        # パスワード一致チェック（パスワードが入力されている場合）
        if password and password != password_confirm:
            flash('パスワードが一致しません', 'error')
            conn.close()
            return render_template('sys_system_admin_edit.html', admin=admin)
        
        # 更新
        if password:
            # パスワードも更新
            password_hash = generate_password_hash(password)
            cur.execute(_sql(conn, '''
                UPDATE "T_管理者" 
                SET login_id = %s, name = %s, email = %s, password_hash = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            '''), (login_id, name, email, password_hash, admin_id))
        else:
            # パスワードは更新しない
            cur.execute(_sql(conn, '''
                UPDATE "T_管理者" 
                SET login_id = %s, name = %s, email = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            '''), (login_id, name, email, admin_id))
        
        conn.commit()
        conn.close()
        flash(f'システム管理者「{name}」を更新しました', 'success')
        return redirect(url_for('system_admin.system_admins'))
    
    conn.close()
    return render_template('sys_system_admin_edit.html', admin=admin)


@bp.route('/system_admins/<int:admin_id>/toggle_manage_permission', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def toggle_manage_permission(admin_id):
    """システム管理者管理権限の付与・剥奪（オーナーのみ）"""
    # オーナーのみ実行可能
    if not is_owner():
        flash('オーナーのみがシステム管理者管理権限を変更できます', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    # 自分自身の権限は変更できない
    if admin_id == session.get('user_id'):
        flash('自分自身の権限は変更できません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 対象がシステム管理者であることを確認
    cur.execute(_sql(conn, 'SELECT name, can_manage_admins, is_owner FROM "T_管理者" WHERE id = %s AND role = %s'),
                (admin_id, ROLES["SYSTEM_ADMIN"]))
    row = cur.fetchone()
    if not row:
        flash('システム管理者が見つかりません', 'error')
        conn.close()
        return redirect(url_for('system_admin.system_admins'))
    
    name = row[0]
    current_permission = row[1]
    is_owner_flag = row[2]
    
    # オーナーの権限は変更できない
    if is_owner_flag == 1:
        flash('オーナーの権限は変更できません', 'error')
        conn.close()
        return redirect(url_for('system_admin.system_admins'))
    
    # 権限を切り替え
    new_permission = 0 if current_permission == 1 else 1
    cur.execute(_sql(conn, 'UPDATE "T_管理者" SET can_manage_admins = %s WHERE id = %s'), (new_permission, admin_id))
    conn.close()
    
    status = '付与' if new_permission == 1 else '剥奪'
    flash(f'「{name}」にシステム管理者管理権限を{status}しました', 'success')
    return redirect(url_for('system_admin.system_admins'))


# ========================================
# システム管理者マイページ
# ========================================

@bp.route('/mypage', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def mypage():
    """システム管理者マイページ"""
    user_id = session.get('user_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(_sql(conn, '''
        SELECT id, login_id, name, email, is_owner, can_manage_admins, openai_api_key, created_at, updated_at
        FROM "T_管理者"
        WHERE id = %s AND role = %s
    '''), (user_id, ROLES["SYSTEM_ADMIN"]))
    
    row = cur.fetchone()
    
    if not row:
        conn.close()
        flash('ユーザー情報が見つかりません', 'error')
        return redirect(url_for('system_admin.dashboard'))
    
    user = {
        'id': row[0],
        'login_id': row[1],
        'name': row[2],
        'email': row[3],
        'is_owner': row[4],
        'can_manage_admins': row[5],
        'openai_api_key': row[6],
        'role': ROLES["SYSTEM_ADMIN"],
        'created_at': row[7],
        'updated_at': row[8]
    }
    
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
                return render_template('sys_mypage.html', user=user, tenant_list=[], store_list=[])
            
            # ログインID重複チェック（自分以外）
            cur.execute(_sql(conn, 'SELECT id FROM "T_管理者" WHERE login_id = %s AND id != %s'), (login_id, user_id))
            if cur.fetchone():
                conn.close()
                flash('このログインIDは既に使用されています', 'error')
                return render_template('sys_mypage.html', user=user, tenant_list=[], store_list=[])
            
            # プロフィール更新
            cur.execute(_sql(conn, '''
                UPDATE "T_管理者"
                SET login_id = %s, name = %s, email = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            '''), (login_id, name, email, user_id))
            conn.commit()
            conn.close()
            
            flash('プロフィール情報を更新しました', 'success')
            return redirect(url_for('system_admin.mypage'))
        
        elif action == 'change_password':
            # パスワード変更
            current_password = request.form.get('current_password', '').strip()
            new_password = request.form.get('new_password', '').strip()
            new_password_confirm = request.form.get('new_password_confirm', '').strip()
        
            # パスワード一致チェック
            if new_password != new_password_confirm:
                conn.close()
                flash('パスワードが一致しません', 'error')
                # テナント・店舗リストを取得してテンプレートに渡す
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute(_sql(conn, 'SELECT id, "名称" FROM "T_テナント" WHERE "有効" = 1 ORDER BY id'))
                tenant_list = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
                cur.execute(_sql(conn, 'SELECT id, "名称", tenant_id FROM "T_店舗" WHERE "有効" = 1 ORDER BY tenant_id, id'))
                store_list = [{'id': row[0], 'name': row[1], 'tenant_id': row[2]} for row in cur.fetchall()]
                for store in store_list:
                    cur.execute(_sql(conn, 'SELECT "名称" FROM "T_テナント" WHERE id = %s'), (store['tenant_id'],))
                    tenant_row = cur.fetchone()
                    if tenant_row:
                        store['tenant_name'] = tenant_row[0]
                conn.close()
                return render_template('sys_mypage.html', user=user, tenant_list=tenant_list, store_list=store_list)
        
            # 現在のパスワードを確認
            cur.execute(_sql(conn, 'SELECT password_hash FROM "T_管理者" WHERE id = %s'), (user_id,))
            row = cur.fetchone()
            if not row or not check_password_hash(row[0], current_password):
                conn.close()
                flash('現在のパスワードが正しくありません', 'error')
                # テナント・店舗リストを取得してテンプレートに渡す
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute(_sql(conn, 'SELECT id, "名称" FROM "T_テナント" WHERE "有効" = 1 ORDER BY id'))
                tenant_list = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
                cur.execute(_sql(conn, 'SELECT id, "名称", tenant_id FROM "T_店舗" WHERE "有効" = 1 ORDER BY tenant_id, id'))
                store_list = [{'id': row[0], 'name': row[1], 'tenant_id': row[2]} for row in cur.fetchall()]
                for store in store_list:
                    cur.execute(_sql(conn, 'SELECT "名称" FROM "T_テナント" WHERE id = %s'), (store['tenant_id'],))
                    tenant_row = cur.fetchone()
                    if tenant_row:
                        store['tenant_name'] = tenant_row[0]
                conn.close()
                return render_template('sys_mypage.html', user=user, tenant_list=tenant_list, store_list=store_list)
        
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
            return redirect(url_for('system_admin.mypage'))
    
    # テナントリストを取得
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT id, "名称" FROM "T_テナント" WHERE "有効" = 1 ORDER BY id'))
    tenant_list = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    
    # 店舗リストを取得
    cur.execute(_sql(conn, 'SELECT id, "名称", tenant_id FROM "T_店舗" WHERE "有効" = 1 ORDER BY tenant_id, id'))
    store_list = [{'id': row[0], 'name': row[1], 'tenant_id': row[2]} for row in cur.fetchall()]
    
    # テナント名を店舗リストに追加
    for store in store_list:
        cur.execute(_sql(conn, 'SELECT "名称" FROM "T_テナント" WHERE id = %s'), (store['tenant_id'],))
        tenant_row = cur.fetchone()
        if tenant_row:
            store['tenant_name'] = tenant_row[0]
    
    conn.close()
    return render_template('sys_mypage.html', user=user, tenant_list=tenant_list, store_list=store_list)


@bp.route('/select_tenant_from_mypage', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def select_tenant_from_mypage():
    """マイページからテナントを選択してテナント管理者ダッシュボードへ"""
    tenant_id = request.form.get('tenant_id')
    
    if not tenant_id:
        flash('テナントを選択してください', 'error')
        return redirect(url_for('system_admin.mypage'))
    
    # テナントが存在するか確認
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT id, "名称" FROM "T_テナント" WHERE id = %s AND "有効" = 1'), (tenant_id,))
    tenant = cur.fetchone()
    conn.close()
    
    if not tenant:
        flash('選択したテナントが見つかりません', 'error')
        return redirect(url_for('system_admin.mypage'))
    
    # セッションにテナント情報を保存
    session['tenant_id'] = tenant[0]
    session['store_id'] = None  # 店舗選択をクリア
    
    flash(f'テナント「{tenant[1]}」を選択しました', 'success')
    
    # テナント管理者ダッシュボードへリダイレクト
    return redirect('/tenant_admin/')


@bp.route('/select_store_from_mypage', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def select_store_from_mypage():
    """マイページから店舗を選択して店舗管理者ダッシュボードへ"""
    store_id = request.form.get('store_id')
    
    if not store_id:
        flash('店舗を選択してください', 'error')
        return redirect(url_for('system_admin.mypage'))
    
    # 店舗が存在するか確認
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT id, "名称", tenant_id FROM "T_店舗" WHERE id = %s AND "有効" = 1'), (store_id,))
    store = cur.fetchone()
    
    if not store:
        conn.close()
        flash('選択した店舗が見つかりません', 'error')
        return redirect(url_for('system_admin.mypage'))
    
    # テナント名も取得
    cur.execute(_sql(conn, 'SELECT "名称" FROM "T_テナント" WHERE id = %s'), (store[2],))
    tenant = cur.fetchone()
    conn.close()
    
    # セッションに店舗情報とテナント情報を保存
    session['store_id'] = store[0]
    session['tenant_id'] = store[2]
    
    if tenant:
        flash(f'店舗「{store[1]}」（テナント: {tenant[0]}）を選択しました', 'success')
    else:
        flash(f'店舗「{store[1]}」を選択しました', 'success')
    
    # 店舗管理者ダッシュボードへリダイレクト
    return redirect('/admin/')


# ============================================================
# アプリ管理
# ============================================================

# 利用可能なアプリ一覧の定義
# 利用可能なアプリ一覧（現在は空）
# 将来的にアプリを追加する場合は、以下の形式で追加してください：
# {'name': 'app-name', 'display_name': 'アプリ表示名', 'scope': 'store'/'tenant'}
AVAILABLE_APPS = []

@bp.route('/app_management')
@require_roles(ROLES["SYSTEM_ADMIN"])
def app_management():
    """アプリ管理トップページ"""
    return render_template('sys_app_management.html')

@bp.route('/app_management/tenant', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def app_management_tenant():
    """テナント別アプリ設定"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # テナント一覧を取得
    cur.execute(_sql(conn, 'SELECT id, "名称" FROM "T_テナント" WHERE "有効" = 1 ORDER BY id'))
    tenants = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    
    selected_tenant_id = None
    tenant_apps = []
    
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        if action == 'select_tenant':
            # テナント選択
            selected_tenant_id = request.form.get('tenant_id', type=int)
            
            if selected_tenant_id:
                # テナント単位のアプリ一覧を取得
                tenant_apps_data = {}
                for app in AVAILABLE_APPS:
                    if app['scope'] == 'tenant':
                        cur.execute(_sql(conn, '''
                            SELECT enabled FROM "T_テナントアプリ設定"
                            WHERE tenant_id = %s AND app_name = %s
                        '''), (selected_tenant_id, app['name']))
                        row = cur.fetchone()
                        enabled = row[0] if row else 1  # デフォルトは有効
                        tenant_apps_data[app['name']] = enabled
                
                tenant_apps = [
                    {
                        'name': app['name'],
                        'display_name': app['display_name'],
                        'enabled': tenant_apps_data.get(app['name'], 1)
                    }
                    for app in AVAILABLE_APPS if app['scope'] == 'tenant'
                ]
        
        elif action == 'update_apps':
            # アプリ設定更新
            selected_tenant_id = request.form.get('tenant_id', type=int)
            
            if selected_tenant_id:
                for app in AVAILABLE_APPS:
                    if app['scope'] == 'tenant':
                        enabled = 1 if request.form.get(f'app_{app["name"]}') == 'on' else 0
                        
                        # UPSERT処理
                        cur.execute(_sql(conn, '''
                            SELECT id FROM "T_テナントアプリ設定"
                            WHERE tenant_id = %s AND app_name = %s
                        '''), (selected_tenant_id, app['name']))
                        
                        if cur.fetchone():
                            # 更新
                            cur.execute(_sql(conn, '''
                                UPDATE "T_テナントアプリ設定"
                                SET enabled = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE tenant_id = %s AND app_name = %s
                            '''), (enabled, selected_tenant_id, app['name']))
                        else:
                            # 挿入
                            cur.execute(_sql(conn, '''
                                INSERT INTO "T_テナントアプリ設定" (tenant_id, app_name, enabled)
                                VALUES (%s, %s, %s)
                            '''), (selected_tenant_id, app['name'], enabled))
                
                conn.commit()
                flash('テナントのアプリ設定を更新しました', 'success')
                
                # 更新後のデータを再取得
                tenant_apps_data = {}
                for app in AVAILABLE_APPS:
                    if app['scope'] == 'tenant':
                        cur.execute(_sql(conn, '''
                            SELECT enabled FROM "T_テナントアプリ設定"
                            WHERE tenant_id = %s AND app_name = %s
                        '''), (selected_tenant_id, app['name']))
                        row = cur.fetchone()
                        enabled = row[0] if row else 1
                        tenant_apps_data[app['name']] = enabled
                
                tenant_apps = [
                    {
                        'name': app['name'],
                        'display_name': app['display_name'],
                        'enabled': tenant_apps_data.get(app['name'], 1)
                    }
                    for app in AVAILABLE_APPS if app['scope'] == 'tenant'
                ]
    
    conn.close()
    
    return render_template('sys_app_management_tenant.html',
                         tenants=tenants,
                         selected_tenant_id=selected_tenant_id,
                         tenant_apps=tenant_apps)

@bp.route('/app_management/store', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def app_management_store():
    """店舗別アプリ設定"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # テナント一覧を取得
    cur.execute(_sql(conn, 'SELECT id, "名称" FROM "T_テナント" WHERE "有効" = 1 ORDER BY id'))
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
            
            if selected_tenant_id:
                cur.execute(_sql(conn, '''
                    SELECT id, "名称" FROM "T_店舗"
                    WHERE tenant_id = %s AND "有効" = 1
                    ORDER BY id
                '''), (selected_tenant_id,))
                stores = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
            
            if selected_store_id:
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
            
            if selected_tenant_id:
                cur.execute(_sql(conn, '''
                    SELECT id, "名称" FROM "T_店舗"
                    WHERE tenant_id = %s AND "有効" = 1
                    ORDER BY id
                '''), (selected_tenant_id,))
                stores = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
            
            if selected_store_id:
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
    
    return render_template('sys_app_management_store.html',
                         tenants=tenants,
                         stores=stores,
                         selected_tenant_id=selected_tenant_id,
                         selected_store_id=selected_store_id,
                         store_apps=store_apps)
