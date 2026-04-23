# -*- coding: utf-8 -*-
"""
アンケートシステム Blueprint
survey-system-app から移植
"""
import os
import json
import csv
from io import StringIO
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, session

from ..utils.decorators import require_roles, ROLES
from ..utils.db import get_db_connection, _sql

bp = Blueprint('survey_app', __name__, url_prefix='/apps/survey')


def _get_store_id():
    """セッションから店舗IDを取得"""
    return session.get('store_id')


def _get_admin_info():
    """セッションから管理者情報を取得"""
    return {
        'name': session.get('user_name', '管理者'),
        'login_id': session.get('login_id', ''),
        'store_name': session.get('store_name', '')
    }


@bp.route("/")
@bp.route("")
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def index():
    """アンケートシステムトップ - セッションのstore_idへリダイレクト"""
    store_id = session.get("store_id")
    if store_id:
        return redirect(url_for("survey_app.dashboard", store_id=store_id))
    flash("店舗が選択されていません。ダッシュボードから店舗を選択してください。", "error")
    return redirect(url_for("app_manager.dashboard"))


# ===== ダッシュボード =====
@bp.route('/store/<int:store_id>/')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def dashboard(store_id):
    """アンケートダッシュボード"""
    admin = _get_admin_info()
    conn = get_db_connection()
    cur = conn.cursor()

    # 店舗情報
    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store = cur.fetchone()
    if not store:
        conn.close()
        flash('店舗が見つかりません', 'error')
        return redirect(url_for('admin.store_info'))
    store_name = store[0]

    # 回答統計
    cur.execute(_sql(conn, 'SELECT COUNT(*) FROM "T_アンケート回答" WHERE store_id = %s'), (store_id,))
    total_responses = cur.fetchone()[0]

    cur.execute(_sql(conn, '''
        SELECT rating, COUNT(*) FROM "T_アンケート回答"
        WHERE store_id = %s GROUP BY rating
    '''), (store_id,))
    rating_rows = cur.fetchall()
    rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for row in rating_rows:
        if row[0] in rating_counts:
            rating_counts[row[0]] = row[1]

    avg_rating = 0
    if total_responses > 0:
        cur.execute(_sql(conn, 'SELECT AVG(rating) FROM "T_アンケート回答" WHERE store_id = %s'), (store_id,))
        avg_rating = round(cur.fetchone()[0] or 0, 2)

    # 最新10件
    cur.execute(_sql(conn, '''
        SELECT id, rating, visit_purpose, atmosphere, recommend, comment, created_at
        FROM "T_アンケート回答" WHERE store_id = %s
        ORDER BY created_at DESC LIMIT 10
    '''), (store_id,))
    recent_responses = [
        {'id': r[0], 'rating': r[1], 'visit_purpose': r[2], 'atmosphere': r[3],
         'recommend': r[4], 'comment': r[5], 'timestamp': str(r[6])}
        for r in cur.fetchall()
    ]
    conn.close()

    return render_template('survey_app_dashboard.html',
                           admin=admin,
                           store_id=store_id,
                           store_name=store_name,
                           total_responses=total_responses,
                           rating_counts=rating_counts,
                           avg_rating=avg_rating,
                           recent_responses=recent_responses)


# ===== 回答一覧 =====
@bp.route('/store/<int:store_id>/responses')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def responses(store_id):
    """全回答データを表示"""
    admin = _get_admin_info()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store = cur.fetchone()
    store_name = store[0] if store else ''

    cur.execute(_sql(conn, '''
        SELECT id, rating, visit_purpose, atmosphere, recommend, comment, generated_review, created_at
        FROM "T_アンケート回答" WHERE store_id = %s
        ORDER BY created_at DESC
    '''), (store_id,))
    survey_responses = [
        {'id': r[0], 'rating': r[1], 'visit_purpose': r[2], 'atmosphere': r[3],
         'recommend': r[4], 'comment': r[5], 'generated_review': r[6], 'timestamp': str(r[7])}
        for r in cur.fetchall()
    ]
    conn.close()

    return render_template('survey_app_responses.html',
                           admin=admin,
                           store_id=store_id,
                           store_name=store_name,
                           responses=survey_responses)


# ===== CSV エクスポート =====
@bp.route('/store/<int:store_id>/export/csv')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def export_csv(store_id):
    """回答データをCSVでエクスポート"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, '''
        SELECT id, created_at, rating, visit_purpose, atmosphere, recommend, comment, generated_review
        FROM "T_アンケート回答" WHERE store_id = %s ORDER BY created_at DESC
    '''), (store_id,))
    rows = cur.fetchall()
    conn.close()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['ID', '回答日時', '評価', '訪問目的', '雰囲気', 'おすすめ度', 'コメント', 'AI生成口コミ'])
    for r in rows:
        writer.writerow(list(r))

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=survey_responses.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8-sig"
    return output


# ===== アンケート設定エディタ =====
@bp.route('/store/<int:store_id>/editor', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def survey_editor(store_id):
    """アンケート設定エディタ"""
    admin = _get_admin_info()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store = cur.fetchone()
    store_name = store[0] if store else ''

    if request.method == 'POST':
        survey_title = request.form.get('survey_title', '').strip()
        survey_description = request.form.get('survey_description', '').strip()

        questions = []
        question_indices = set()
        for key in request.form.keys():
            if key.startswith('questions['):
                try:
                    question_indices.add(int(key.split('[')[1].split(']')[0]))
                except ValueError:
                    continue

        for idx in sorted(question_indices):
            question_text = request.form.get(f'questions[{idx}][text]', '').strip()
            question_type = request.form.get(f'questions[{idx}][type]', 'text')
            if not question_text:
                continue
            is_required = request.form.get(f'questions[{idx}][required]') == 'true'
            question = {'id': idx + 1, 'text': question_text, 'type': question_type, 'required': is_required}
            if question_type in ['radio', 'checkbox', 'comment_rating']:
                options = request.form.getlist(f'questions[{idx}][options][]')
                question['options'] = [opt.strip() for opt in options if opt.strip()]
            questions.append(question)

        survey_config = {
            'title': survey_title,
            'description': survey_description,
            'questions': questions,
            'updated_at': datetime.now().isoformat()
        }
        config_json = json.dumps(survey_config, ensure_ascii=False)

        cur.execute(_sql(conn, 'SELECT id FROM "T_店舗_アンケート設定" WHERE store_id = %s'), (store_id,))
        existing = cur.fetchone()
        if existing:
            cur.execute(_sql(conn, '''
                UPDATE "T_店舗_アンケート設定"
                SET title = %s, config_json = %s, updated_at = CURRENT_TIMESTAMP
                WHERE store_id = %s
            '''), (survey_title, config_json, store_id))
        else:
            cur.execute(_sql(conn, '''
                INSERT INTO "T_店舗_アンケート設定" (store_id, title, config_json)
                VALUES (%s, %s, %s)
            '''), (store_id, survey_title, config_json))
        conn.commit()
        conn.close()

        flash('アンケート設定を保存しました', 'success')
        return redirect(url_for('survey_app.survey_editor', store_id=store_id))

    # GET: DBから設定を読み込み
    cur.execute(_sql(conn, 'SELECT title, config_json FROM "T_店舗_アンケート設定" WHERE store_id = %s'), (store_id,))
    row = cur.fetchone()
    conn.close()

    if row and row[1]:
        try:
            survey_config = json.loads(row[1])
        except Exception:
            survey_config = None
    else:
        survey_config = None

    if not survey_config:
        survey_config = {
            'title': 'お店アンケート',
            'description': 'ご来店ありがとうございます！',
            'questions': [
                {'id': 1, 'text': '総合評価', 'type': 'rating', 'required': True},
                {'id': 2, 'text': '訪問目的', 'type': 'radio', 'required': True,
                 'options': ['食事', 'カフェ', '買い物', 'その他']},
                {'id': 3, 'text': 'お店の雰囲気（複数選択可）', 'type': 'checkbox', 'required': False,
                 'options': ['静か', '賑やか', '落ち着く', 'おしゃれ', 'カジュアル']},
                {'id': 4, 'text': 'おすすめ度', 'type': 'radio', 'required': True,
                 'options': ['ぜひおすすめしたい', 'おすすめしたい', 'どちらでもない', 'おすすめしない']},
                {'id': 5, 'text': 'ご感想・ご意見（任意）', 'type': 'text', 'required': False}
            ]
        }

    return render_template('survey_app_editor.html',
                           admin=admin,
                           store_id=store_id,
                           store_name=store_name,
                           survey_config=survey_config)


# ===== 回答受付（顧客向け） =====
@bp.route('/store/<int:store_id>/answer', methods=['GET', 'POST'])
def answer(store_id):
    """アンケート回答フォーム（顧客向け）"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store = cur.fetchone()
    if not store:
        conn.close()
        return '店舗が見つかりません', 404
    store_name = store[0]

    cur.execute(_sql(conn, 'SELECT title, config_json FROM "T_店舗_アンケート設定" WHERE store_id = %s'), (store_id,))
    row = cur.fetchone()

    if row and row[1]:
        try:
            survey_config = json.loads(row[1])
        except Exception:
            survey_config = None
    else:
        survey_config = None

    if not survey_config:
        survey_config = {
            'title': 'お店アンケート',
            'description': 'ご来店ありがとうございます！',
            'questions': [
                {'id': 1, 'text': '総合評価', 'type': 'rating', 'required': True},
                {'id': 5, 'text': 'ご感想・ご意見（任意）', 'type': 'text', 'required': False}
            ]
        }

    if request.method == 'POST':
        rating = int(request.form.get('rating', 3))
        visit_purpose = request.form.get('visit_purpose', '')
        atmosphere = request.form.get('atmosphere', '')
        recommend = request.form.get('recommend', '')
        comment = request.form.get('comment', '')
        response_json = json.dumps(dict(request.form), ensure_ascii=False)

        cur.execute(_sql(conn, '''
            INSERT INTO "T_アンケート回答"
            (store_id, rating, visit_purpose, atmosphere, recommend, comment, response_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        '''), (store_id, rating, visit_purpose, atmosphere, recommend, comment, response_json))
        conn.commit()
        conn.close()

        return render_template('survey_app_thanks.html', store_name=store_name)

    conn.close()
    return render_template('survey_app_answer.html',
                           store_id=store_id,
                           store_name=store_name,
                           survey_config=survey_config)
