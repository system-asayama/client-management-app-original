"""
事業所管理ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session
from app.db import get_conn

bp = Blueprint('organization', __name__, url_prefix='/org')


@bp.route('/')
def org_list():
    """事業所一覧"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    orgs = conn.execute("SELECT * FROM T_事業所 ORDER BY id DESC").fetchall()
    conn.close()
    
    return render_template('org_list.html', orgs=orgs)


@bp.route('/create', methods=['GET', 'POST'])
def org_create():
    """事業所作成"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        name = request.form['name']
        
        conn = get_conn()
        conn.execute("INSERT INTO T_事業所 (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
        
        return redirect(url_for('organization.org_list'))
    
    return render_template('org_form.html')


@bp.route('/<int:org_id>')
def org_detail(org_id):
    """事業所詳細"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    org = conn.execute("SELECT * FROM T_事業所 WHERE id = ?", (org_id,)).fetchone()
    conn.close()
    
    if not org:
        return "事業所が見つかりません", 404
    
    return render_template('org_detail.html', org=org)


@bp.route('/<int:org_id>/dashboard')
def org_dashboard(org_id):
    """事業所ダッシュボード"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    org = conn.execute("SELECT * FROM T_事業所 WHERE id = ?", (org_id,)).fetchone()
    
    if not org:
        conn.close()
        return "事業所が見つかりません", 404
    
    # 統計情報などを取得
    stats = {
        'clients_count': conn.execute("SELECT COUNT(*) as cnt FROM T_顧問先").fetchone()['cnt'],
        'users_count': conn.execute("SELECT COUNT(*) as cnt FROM T_ユーザー").fetchone()['cnt'],
    }
    
    conn.close()
    
    return render_template('org_dashboard.html', org=org, stats=stats, org_id=org_id)


@bp.route('/select')
def select_org():
    """事業所選択"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    orgs = conn.execute("SELECT * FROM T_事業所 ORDER BY id DESC").fetchall()
    conn.close()
    
    return render_template('select_org.html', orgs=orgs)


@bp.route('/set/<int:org_id>')
def set_org(org_id):
    """事業所をセッションに設定"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    session['org_id'] = org_id
    return redirect(url_for('organization.org_dashboard', org_id=org_id))
