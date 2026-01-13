"""
会社基本情報管理ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session
from app.db import get_conn

bp = Blueprint('company', __name__, url_prefix='/company')


@bp.route('/')
def company_list():
    """会社基本情報一覧"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    companies = conn.execute("SELECT * FROM T_会社基本情報 ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('company_list.html', companies=companies)


@bp.route('/<int:company_id>')
def company_info(company_id):
    """会社基本情報詳細"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    company = conn.execute("SELECT * FROM T_会社基本情報 WHERE id = ?", (company_id,)).fetchone()
    conn.close()
    
    if not company:
        return "会社情報が見つかりません", 404
    
    return render_template('company_info.html', company=company)


@bp.route('/create/<int:client_id>', methods=['GET', 'POST'])
def company_create(client_id):
    """会社基本情報新規登録"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    client = conn.execute('SELECT * FROM T_顧問先 WHERE id = ?', (client_id,)).fetchone()
    
    if not client:
        conn.close()
        return "顧問先が見つかりません", 404
    
    # 既に会社情報が存在する場合はリダイレクト
    company = conn.execute("SELECT * FROM T_会社基本情報 WHERE 顧問先ID = ?", (client_id,)).fetchone()
    if company:
        conn.close()
        return redirect(url_for('company.company_info', company_id=company['id']))
    
    if request.method == 'POST':
        conn.execute('''
            INSERT INTO T_会社基本情報 (
                顧問先ID, 会社名, 郵便番号, 都道府県, 市区町村番地, 建物名部屋番号,
                電話番号1, 電話番号2, ファックス番号, メールアドレス,
                担当者名, 業種, 従業員数, 法人番号
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', [
            client_id,
            request.form['会社名'],
            request.form['郵便番号'],
            request.form['都道府県'],
            request.form['市区町村番地'],
            request.form['建物名部屋番号'],
            request.form['電話番号1'],
            request.form['電話番号2'],
            request.form['ファックス番号'],
            request.form['メールアドレス'],
            request.form['担当者名'],
            request.form['業種'],
            request.form.get('従業員数') or request.form.get('従業数'),
            request.form['法人番号']
        ])
        conn.commit()
        conn.close()
        return redirect(url_for('clients.client_info', client_id=client_id))
    
    conn.close()
    return render_template('company_create.html', client=client)


@bp.route('/<int:company_id>/edit', methods=['GET', 'POST'])
def company_edit(company_id):
    """会社基本情報編集"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    company = conn.execute("SELECT * FROM T_会社基本情報 WHERE id = ?", (company_id,)).fetchone()
    clients = conn.execute("SELECT id, name, type FROM T_顧問先").fetchall()
    
    if not company:
        conn.close()
        return "会社情報が見つかりません", 404
    
    if request.method == 'POST':
        conn.execute('''
            UPDATE T_会社基本情報 SET
                顧問先ID=?, 会社名=?, 郵便番号=?, 都道府県=?, 市区町村番地=?, 建物名部屋番号=?,
                電話番号1=?, 電話番号2=?, ファックス番号=?, メールアドレス=?,
                担当者名=?, 業種=?, 従業員数=?, 法人番号=?
            WHERE id=?
        ''', [
            request.form['顧問先ID'],
            request.form['会社名'],
            request.form['郵便番号'],
            request.form['都道府県'],
            request.form['市区町村番地'],
            request.form['建物名部屋番号'],
            request.form['電話番号1'],
            request.form['電話番号2'],
            request.form['ファックス番号'],
            request.form['メールアドレス'],
            request.form['担当者名'],
            request.form['業種'],
            request.form.get('従業員数'),
            request.form['法人番号'],
            company_id
        ])
        conn.commit()
        conn.close()
        return redirect(url_for('company.company_info', company_id=company_id))
    
    conn.close()
    return render_template('company_edit.html', company=company, clients=clients)


@bp.route('/<int:company_id>/delete', methods=['POST'])
def company_delete(company_id):
    """会社基本情報削除"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_conn()
    conn.execute("DELETE FROM T_会社基本情報 WHERE id = ?", (company_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('company.company_list'))
