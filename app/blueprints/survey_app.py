# -*- coding: utf-8 -*-
"""
アンケートシステム Blueprint
survey-system-app から移植（AI口コミ生成・Googleレビュー誘導・設定管理を含む）
"""
import os
import json
import csv
import sys
from io import StringIO
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, session, jsonify
from ..utils.decorators import require_roles, ROLES
from ..utils.db import get_db_connection, _sql

bp = Blueprint('survey_app', __name__, url_prefix='/apps/survey')


def _get_admin_info():
    return {
        'name': session.get('user_name', '管理者'),
        'login_id': session.get('login_id', ''),
        'store_name': session.get('store_name', '')
    }


def _get_openai_client(store_id=None, survey_app_id=None):
    from openai import OpenAI
    api_key = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if survey_app_id:
            cur.execute(_sql(conn, 'SELECT openai_api_key, store_id FROM "T_店舗_アンケート設定" WHERE id = %s'), (survey_app_id,))
            row = cur.fetchone()
            if row and row[0]:
                conn.close()
                return OpenAI(api_key=row[0])
            if not store_id and row and row[1]:
                store_id = row[1]
        if store_id:
            cur.execute(_sql(conn, 'SELECT openai_api_key, tenant_id FROM "T_店舗" WHERE id = %s'), (store_id,))
            row = cur.fetchone()
            if row and row[0]:
                conn.close()
                return OpenAI(api_key=row[0])
            tenant_id = row[1] if row else None
            if tenant_id:
                cur.execute(_sql(conn, 'SELECT openai_api_key FROM "T_テナント" WHERE id = %s'), (tenant_id,))
                row = cur.fetchone()
                if row and row[0]:
                    conn.close()
                    return OpenAI(api_key=row[0])
        conn.close()
    except Exception as e:
        sys.stderr.write(f"Error getting OpenAI API key: {e}\n")
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OpenAI APIキーが設定されていません。")
    return OpenAI(api_key=api_key)


def _get_survey_settings(store_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, '''
            SELECT id, title, config_json, openai_api_key,
                   ai_review_mode, business_type, ai_instruction, google_review_url
            FROM "T_店舗_アンケート設定" WHERE store_id = %s
        '''), (store_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            config = None
            if row[2]:
                try:
                    config = json.loads(row[2])
                except Exception:
                    config = None
            return {
                'id': row[0], 'title': row[1], 'config': config,
                'openai_api_key': row[3],
                'ai_review_mode': row[4] or 'all',
                'business_type': row[5] or '',
                'ai_instruction': row[6] or '',
                'google_review_url': row[7] or '#',
            }
    except Exception as e:
        sys.stderr.write(f"_get_survey_settings error: {e}\n")
    return {
        'id': None, 'title': 'お店アンケート', 'config': None,
        'openai_api_key': None, 'ai_review_mode': 'all',
        'business_type': '', 'ai_instruction': '', 'google_review_url': '#',
    }


def _get_default_survey_config():
    return {
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


def _generate_review_text(survey_data, store_id, survey_settings=None):
    if survey_settings is None:
        survey_settings = _get_survey_settings(store_id)
    survey_config = survey_settings.get('config') or _get_default_survey_config()
    business_type = survey_settings.get('business_type', '')
    ai_instruction = survey_settings.get('ai_instruction', '')
    survey_app_id = survey_settings.get('id')

    qa_pairs = []
    for q in survey_config.get('questions', []):
        qid = f"q{q['id']}"
        answer = survey_data.get(qid, '')
        if isinstance(answer, list):
            answer = '、'.join(answer)
        if answer:
            qa_pairs.append(f"Q: {q['text']}\nA: {answer}")
    qa_text = '\n\n'.join(qa_pairs) if qa_pairs else '（回答なし）'

    business_type_line = f"\n【業種】{business_type}" if business_type else ""
    ai_instruction_block = f"\n\n【追加指示】\n{ai_instruction}" if ai_instruction else ""
    business_system_hint = ""
    if business_type:
        business_system_hint = f"\nこの口コミは「{business_type}」向けです。"
    if ai_instruction:
        business_system_hint += f"\n追加指示: {ai_instruction}"

    prompt = f"""以下のアンケート回答から、実際の人間が書いたような自然な口コミ投稿文を日本語で作成してください。{business_type_line}
【アンケート回答】
{qa_text}{ai_instruction_block}
【要件】
- 180～220文字程度で簡潔にまとめる
- 自然な口語体・「です・ます」調
- 具体的な体験を含める
- AIが書いたと分からないよう自然な表現を使う
口コミ投稿文:"""

    openai_client = _get_openai_client(store_id=store_id, survey_app_id=survey_app_id)
    response = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": f"あなたは自然な口コミ投稿文を作成する専門家です。{business_system_hint}"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=500
    )
    return response.choices[0].message.content.strip()


def run_survey_migrations():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for sql in [
            'ALTER TABLE "T_店舗_アンケート設定" ADD COLUMN IF NOT EXISTS ai_review_mode VARCHAR(20) DEFAULT \'all\'',
            'ALTER TABLE "T_店舗_アンケート設定" ADD COLUMN IF NOT EXISTS business_type VARCHAR(100)',
            'ALTER TABLE "T_店舗_アンケート設定" ADD COLUMN IF NOT EXISTS ai_instruction TEXT',
            'ALTER TABLE "T_店舗_アンケート設定" ADD COLUMN IF NOT EXISTS google_review_url VARCHAR(500)',
        ]:
            try:
                cur.execute(sql)
            except Exception as e:
                sys.stderr.write(f"Migration warning: {e}\n")
        conn.commit()
        conn.close()
        print("survey_app migrations OK")
    except Exception as e:
        sys.stderr.write(f"survey_app migration error: {e}\n")


@bp.route("/")
@bp.route("")
@require_roles(ROLES["ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def index():
    store_id = session.get("store_id")
    if store_id:
        return redirect(url_for("survey_app.dashboard", store_id=store_id))
    # store_idがない場合（テナント管理者など）は店舗選択画面を表示
    tenant_id = session.get("tenant_id")
    if not tenant_id:
        flash("ログインし直してください。", "error")
        return redirect(url_for("auth.login"))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, 'SELECT id, 名称 FROM "T_店舗" WHERE tenant_id = %s AND 有効 = 1 ORDER BY id'), (tenant_id,))
        stores = [{'id': r[0], 'name': r[1]} for r in cur.fetchall()]
        conn.close()
    except Exception as e:
        stores = []
        sys.stderr.write(f"survey index store fetch error: {e}\n")
    if len(stores) == 1:
        return redirect(url_for("survey_app.dashboard", store_id=stores[0]['id']))
    admin = _get_admin_info()
    return render_template('survey_app_store_select.html', stores=stores, admin=admin)


@bp.route('/store/<int:store_id>/')
@require_roles(ROLES["ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def dashboard(store_id):
    admin = _get_admin_info()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT 名称, slug FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    if not store_row:
        conn.close()
        flash('店舗が見つかりません', 'error')
        return redirect(url_for('admin.store_info'))
    store_name = store_row[0]
    store_slug = store_row[1]

    stats = {'total': 0, 'avg_rating': 0, 'rating_dist': {}}
    try:
        cur.execute(_sql(conn, 'SELECT COUNT(*) FROM "T_アンケート回答" WHERE store_id = %s'), (store_id,))
        stats['total'] = cur.fetchone()[0]
        if stats['total'] > 0:
            cur.execute(_sql(conn, 'SELECT AVG(rating) FROM "T_アンケート回答" WHERE store_id = %s'), (store_id,))
            avg = cur.fetchone()[0]
            stats['avg_rating'] = round(float(avg), 1) if avg else 0
            cur.execute(_sql(conn, 'SELECT rating, COUNT(*) FROM "T_アンケート回答" WHERE store_id = %s GROUP BY rating ORDER BY rating DESC'), (store_id,))
            for row in cur.fetchall():
                stats['rating_dist'][row[0]] = row[1]
    except Exception as e:
        sys.stderr.write(f"Stats error: {e}\n")

    recent_responses = []
    try:
        cur.execute(_sql(conn, 'SELECT id, rating, comment, created_at FROM "T_アンケート回答" WHERE store_id = %s ORDER BY created_at DESC LIMIT 5'), (store_id,))
        for row in cur.fetchall():
            recent_responses.append({'id': row[0], 'rating': row[1], 'comment': row[2] or '', 'created_at': row[3]})
    except Exception as e:
        sys.stderr.write(f"Recent responses error: {e}\n")

    conn.close()
    survey_settings = _get_survey_settings(store_id)

    return render_template('survey_app_dashboard.html',
                           admin=admin, store_id=store_id, store_name=store_name,
                           store_slug=store_slug, stats=stats,
                           total_responses=stats['total'],
                           avg_rating=stats['avg_rating'],
                           rating_counts=stats['rating_dist'],
                           recent_responses=recent_responses, survey_settings=survey_settings)


@bp.route('/store/<int:store_id>/editor', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def survey_editor(store_id):
    admin = _get_admin_info()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    if not store_row:
        conn.close()
        flash('店舗が見つかりません', 'error')
        return redirect(url_for('survey_app.index'))
    store_name = store_row[0]

    if request.method == 'POST':
        survey_title = request.form.get('survey_title', '').strip()
        survey_description = request.form.get('survey_description', '').strip()
        questions = []
        question_indices = set()
        for key in request.form.keys():
            if key.startswith('questions['):
                try:
                    idx = int(key.split('[')[1].split(']')[0])
                    question_indices.add(idx)
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
        survey_config = {'title': survey_title, 'description': survey_description, 'questions': questions}
        config_json = json.dumps(survey_config, ensure_ascii=False)
        cur.execute(_sql(conn, 'SELECT id FROM "T_店舗_アンケート設定" WHERE store_id = %s'), (store_id,))
        existing = cur.fetchone()
        if existing:
            cur.execute(_sql(conn, 'UPDATE "T_店舗_アンケート設定" SET title = %s, config_json = %s, updated_at = CURRENT_TIMESTAMP WHERE store_id = %s'), (survey_title, config_json, store_id))
        else:
            cur.execute(_sql(conn, 'INSERT INTO "T_店舗_アンケート設定" (store_id, title, config_json) VALUES (%s, %s, %s)'), (store_id, survey_title, config_json))
        conn.commit()
        conn.close()
        flash('アンケート設定を保存しました', 'success')
        return redirect(url_for('survey_app.survey_editor', store_id=store_id))

    conn.close()
    survey_settings = _get_survey_settings(store_id)
    survey_config = survey_settings.get('config') or _get_default_survey_config()
    return render_template('survey_app_editor.html', admin=admin, store_id=store_id, store_name=store_name, survey_config=survey_config)


@bp.route('/store/<int:store_id>/settings', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def survey_settings_view(store_id):
    admin = _get_admin_info()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT 名称, slug FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    if not store_row:
        conn.close()
        flash('店舗が見つかりません', 'error')
        return redirect(url_for('survey_app.index'))
    store_name = store_row[0]
    store_slug = store_row[1]
    if request.method == 'POST':
        openai_api_key = request.form.get('openai_api_key', '').strip() or None
        google_review_url = request.form.get('google_review_url', '').strip() or None
        ai_review_mode = request.form.get('ai_review_mode', 'all')
        business_type = request.form.get('business_type', '').strip() or None
        ai_instruction = request.form.get('ai_instruction', '').strip() or None
        cur.execute(_sql(conn, 'SELECT id FROM "T_店舗_アンケート設定" WHERE store_id = %s'), (store_id,))
        existing = cur.fetchone()
        if existing:
            cur.execute(_sql(conn, '''UPDATE "T_店舗_アンケート設定"
                SET openai_api_key = %s, google_review_url = %s,
                    ai_review_mode = %s, business_type = %s, ai_instruction = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE store_id = %s'''),
                (openai_api_key, google_review_url, ai_review_mode, business_type, ai_instruction, store_id))
        else:
            cur.execute(_sql(conn, '''INSERT INTO "T_店舗_アンケート設定"
                (store_id, title, config_json, openai_api_key, google_review_url, ai_review_mode, business_type, ai_instruction)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)'''),
                (store_id, 'お店アンケート', '{}', openai_api_key, google_review_url, ai_review_mode, business_type, ai_instruction))
        conn.commit()
        conn.close()
        flash('設定を保存しました', 'success')
        return redirect(url_for('survey_app.survey_settings_view', store_id=store_id))

    conn.close()
    settings_data = _get_survey_settings(store_id)
    slot_cfg = _get_slot_config(store_id)
    slot_settings_data = _get_slot_settings(store_id)
    prizes_data = _get_prizes(store_id)
    return render_template('survey_app_settings.html', admin=admin, store_id=store_id, store_name=store_name, store_slug=store_slug, settings=settings_data,
                           slot_cfg=slot_cfg, slot_settings=slot_settings_data, prizes=prizes_data)


@bp.route('/store/<int:store_id>/responses')
@require_roles(ROLES["ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def responses(store_id):
    admin = _get_admin_info()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    if not store_row:
        conn.close()
        flash('店舗が見つかりません', 'error')
        return redirect(url_for('survey_app.index'))
    store_name = store_row[0]
    cur.execute(_sql(conn, 'SELECT id, rating, visit_purpose, atmosphere, recommend, comment, generated_review, response_json, created_at FROM "T_アンケート回答" WHERE store_id = %s ORDER BY created_at DESC'), (store_id,))
    rows = cur.fetchall()
    conn.close()
    responses_list = [{'id': r[0], 'rating': r[1], 'visit_purpose': r[2], 'atmosphere': r[3], 'recommend': r[4], 'comment': r[5], 'generated_review': r[6], 'response_json': r[7], 'created_at': r[8]} for r in rows]
    class _Store:
        def __init__(self, id, name): self.id = id; self.store_name = name
    store = _Store(store_id, store_name)
    return render_template('survey_app_responses.html', admin=admin, store_id=store_id, store_name=store_name, store=store, responses=responses_list)


@bp.route('/store/<int:store_id>/export_csv')
@require_roles(ROLES["ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def export_csv(store_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT id, rating, visit_purpose, atmosphere, recommend, comment, generated_review, created_at FROM "T_アンケート回答" WHERE store_id = %s ORDER BY created_at DESC'), (store_id,))
    rows = cur.fetchall()
    conn.close()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', '評価', '訪問目的', '雰囲気', 'おすすめ度', 'コメント', '生成口コミ', '回答日時'])
    for row in rows:
        writer.writerow(row)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
    response.headers['Content-Disposition'] = f'attachment; filename=survey_responses_{store_id}.csv'
    return response


def _handle_survey_submit(store_id, store_slug, survey_settings, survey_config):
    try:
        body = request.get_json(silent=True) or {}
        rating = 3
        questions = survey_config.get('questions', [])
        if questions:
            first_q = questions[0]
            first_answer = body.get(f"q{first_q['id']}", '')
            if first_q.get('type') == 'rating':
                try:
                    rating = max(1, min(5, int(first_answer)))
                except (ValueError, TypeError):
                    rating = 3
            elif first_q.get('type') in ['radio', 'comment_rating']:
                opts = first_q.get('options', ['非常に満足', '満足', '普通', 'やや不満', '非常に不満'])
                try:
                    idx = opts.index(first_answer)
                    rating = len(opts) - idx
                except ValueError:
                    rating = 3
        body['rating'] = rating

        visit_purpose = body.get('q2', '')
        atmosphere = body.get('q3', '')
        if isinstance(atmosphere, list):
            atmosphere = '、'.join(atmosphere)
        recommend = body.get('q4', '')
        comment = body.get('q5', '')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, '''INSERT INTO "T_アンケート回答"
            (store_id, rating, visit_purpose, atmosphere, recommend, comment, response_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)'''),
            (store_id, rating, visit_purpose, atmosphere, recommend, comment, json.dumps(body, ensure_ascii=False)))
        conn.commit()
        conn.close()

        ai_review_mode = survey_settings.get('ai_review_mode', 'all')
        generated_review = ''
        redirect_url = f"/apps/survey/store/{store_id}/thanks"

        should_generate = (ai_review_mode == 'all') or (ai_review_mode == 'high_rating_only' and rating >= 4)
        if should_generate:
            try:
                generated_review = _generate_review_text(body, store_id, survey_settings)
                redirect_url = f"/apps/survey/store/{store_id}/review_confirm"
            except Exception as e:
                sys.stderr.write(f"AI review generation failed: {e}\n")

        session[f'survey_completed_{store_id}'] = True
        session[f'survey_rating_{store_id}'] = rating
        session[f'generated_review_{store_id}'] = generated_review
        session[f'survey_data_{store_id}'] = body

        return jsonify({'ok': True, 'message': 'アンケートにご協力いただきありがとうございます！', 'rating': rating, 'generated_review': generated_review, 'redirect_url': redirect_url})
    except Exception as e:
        sys.stderr.write(f"ERROR submit_survey: {e}\n")
        import traceback
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e)}), 400


@bp.route('/store/<int:store_id>/answer', methods=['GET', 'POST'])
def answer(store_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT 名称, slug FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    conn.close()
    if not store_row:
        return '店舗が見つかりません', 404
    store_name = store_row[0]
    store_slug = store_row[1]
    survey_settings = _get_survey_settings(store_id)
    survey_config = survey_settings.get('config') or _get_default_survey_config()
    if request.method == 'POST':
        return _handle_survey_submit(store_id, store_slug, survey_settings, survey_config)
    return render_template('survey_app_answer.html', store={'id': store_id, '名称': store_name}, store_slug=store_slug, survey_config=survey_config)


@bp.route('/store/<int:store_id>/submit_survey', methods=['POST'])
def submit_survey(store_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT 名称, slug FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    conn.close()
    if not store_row:
        return jsonify({'ok': False, 'error': '店舗が見つかりません'}), 404
    store_slug = store_row[1]
    survey_settings = _get_survey_settings(store_id)
    survey_config = survey_settings.get('config') or _get_default_survey_config()
    return _handle_survey_submit(store_id, store_slug, survey_settings, survey_config)


@bp.route('/store/<int:store_id>/review_confirm')
def review_confirm_by_id(store_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT 名称, slug FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    conn.close()
    if not store_row:
        return '店舗が見つかりません', 404
    store_name = store_row[0]
    store_slug = store_row[1]
    generated_review = session.get(f'generated_review_{store_id}', '')
    rating = session.get(f'survey_rating_{store_id}', 0)
    survey_settings = _get_survey_settings(store_id)
    google_review_url = survey_settings.get('google_review_url', '#')
    ai_review_mode = survey_settings.get('ai_review_mode', 'all')
    show_review_button = (ai_review_mode == 'all') or (ai_review_mode == 'high_rating_only' and rating >= 4)
    return render_template('survey_app_review_confirm.html',
                           store={'id': store_id, '名称': store_name},
                           store_slug=store_slug,
                           generated_review=generated_review,
                           google_review_url=google_review_url,
                           rating=rating,
                           show_review_button=show_review_button)


@bp.route('/store/<int:store_id>/regenerate_review', methods=['POST'])
def regenerate_review_by_id(store_id):
    survey_data = session.get(f'survey_data_{store_id}', {})
    survey_settings = _get_survey_settings(store_id)
    try:
        data = request.get_json(silent=True) or {}
        taste = data.get('taste', '')
        if taste and survey_data:
            survey_data['_taste_hint'] = taste
        generated_review = _generate_review_text(survey_data, store_id, survey_settings)
        session[f'generated_review_{store_id}'] = generated_review
        return jsonify({'ok': True, 'review_text': generated_review})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/store/<int:store_id>/thanks')
def thanks_by_id(store_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_店舗" WHERE id = %s'), (store_id,))
    store_row = cur.fetchone()
    conn.close()
    store_name = store_row[0] if store_row else ''
    return render_template('survey_app_thanks.html', store_name=store_name)


@bp.route('/tenant/<int:tenant_id>/summary')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_summary(tenant_id):
    admin = _get_admin_info()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(_sql(conn, 'SELECT 名称 FROM "T_テナント" WHERE id = %s'), (tenant_id,))
    tenant = cur.fetchone()
    if not tenant:
        conn.close()
        flash('テナントが見つかりません', 'error')
        return redirect(url_for('survey_app.index'))
    tenant_name = tenant[0]
    cur.execute(_sql(conn, '''
        SELECT s.id, s.名称, COUNT(r.id) as total, AVG(r.rating) as avg_rating
        FROM "T_店舗" s LEFT JOIN "T_アンケート回答" r ON r.store_id = s.id
        WHERE s.tenant_id = %s GROUP BY s.id, s.名称 ORDER BY s.名称
    '''), (tenant_id,))
    stores = [{'id': r[0], 'name': r[1], 'total': r[2], 'avg_rating': round(float(r[3]), 1) if r[3] else 0} for r in cur.fetchall()]
    conn.close()
    return render_template('survey_tenant_summary.html', admin=admin, tenant_id=tenant_id, tenant_name=tenant_name, stores=stores)


# ============================================================
# スロット機能 (survey-system-app から移植)
# ============================================================
from dataclasses import asdict
import random
from app.models_slot import Symbol, Config
from app.utils.slot_logic import (
    choice_by_prob,
    recalc_probs_inverse_and_expected,
    prob_total_ge,
    prob_total_le,
)
from app.utils.slot_config import default_config as _default_slot_config


def _run_slot_migrations():
    """スロット関連テーブルのマイグレーション"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for sql in [
            '''CREATE TABLE IF NOT EXISTS "T_店舗_景品設定" (
                id SERIAL PRIMARY KEY,
                store_id INTEGER NOT NULL UNIQUE,
                prizes_json TEXT NOT NULL DEFAULT '[]',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS "T_店舗_スロット設定" (
                id SERIAL PRIMARY KEY,
                store_id INTEGER NOT NULL UNIQUE,
                config_json TEXT NOT NULL DEFAULT '{}',
                slot_spin_count INTEGER NOT NULL DEFAULT 1,
                survey_complete_message TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''',
        ]:
            try:
                cur.execute(sql)
            except Exception as e:
                sys.stderr.write(f"Slot migration warning: {e}\n")
        conn.commit()
        conn.close()
        print("slot migrations OK")
    except Exception as e:
        sys.stderr.write(f"slot migration error: {e}\n")


def _get_slot_config(store_id: int) -> Config:
    """DBからスロット設定を取得"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, 'SELECT config_json FROM "T_店舗_スロット設定" WHERE store_id = %s'), (store_id,))
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            raw = json.loads(row[0])
            symbol_fields = {'id', 'label', 'payout_3', 'color', 'prob', 'is_disabled', 'is_default', 'is_reach', 'reach_symbol'}
            syms = [Symbol(**{k: v for k, v in s.items() if k in symbol_fields}) for s in raw.get('symbols', [])]
            if syms:
                return Config(
                    symbols=syms,
                    reels=raw.get('reels', 3),
                    base_bet=raw.get('base_bet', 1),
                    expected_total_5=raw.get('expected_total_5', 2500.0),
                    miss_probability=raw.get('miss_probability', 0.0),
                )
    except Exception as e:
        sys.stderr.write(f"_get_slot_config error: {e}\n")
    return _default_slot_config()


def _save_slot_config_db(store_id: int, cfg: Config) -> None:
    """DBにスロット設定を保存"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        payload = json.dumps(asdict(cfg), ensure_ascii=False)
        cur.execute(_sql(conn, 'SELECT id FROM "T_店舗_スロット設定" WHERE store_id = %s'), (store_id,))
        if cur.fetchone():
            cur.execute(_sql(conn, 'UPDATE "T_店舗_スロット設定" SET config_json = %s, updated_at = CURRENT_TIMESTAMP WHERE store_id = %s'), (payload, store_id))
        else:
            cur.execute(_sql(conn, 'INSERT INTO "T_店舗_スロット設定" (store_id, config_json) VALUES (%s, %s)'), (store_id, payload))
        conn.commit()
        conn.close()
    except Exception as e:
        sys.stderr.write(f"_save_slot_config_db error: {e}\n")


def _get_slot_settings(store_id: int) -> dict:
    """DBからスロット設定（spin_count・メッセージ）を取得"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, 'SELECT slot_spin_count, survey_complete_message FROM "T_店舗_スロット設定" WHERE store_id = %s'), (store_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            return {'slot_spin_count': row[0] or 1, 'survey_complete_message': row[1] or 'アンケートにご協力いただきありがとうございます！スロットをお楽しみください。'}
    except Exception as e:
        sys.stderr.write(f"_get_slot_settings error: {e}\n")
    return {'slot_spin_count': 1, 'survey_complete_message': 'アンケートにご協力いただきありがとうございます！スロットをお楽しみください。'}


def _save_slot_settings_db(store_id: int, slot_spin_count: int, survey_complete_message: str) -> None:
    """DBにスロット設定（spin_count・メッセージ）を保存"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, 'SELECT id FROM "T_店舗_スロット設定" WHERE store_id = %s'), (store_id,))
        if cur.fetchone():
            cur.execute(_sql(conn, 'UPDATE "T_店舗_スロット設定" SET slot_spin_count = %s, survey_complete_message = %s, updated_at = CURRENT_TIMESTAMP WHERE store_id = %s'), (slot_spin_count, survey_complete_message, store_id))
        else:
            cur.execute(_sql(conn, 'INSERT INTO "T_店舗_スロット設定" (store_id, slot_spin_count, survey_complete_message) VALUES (%s, %s, %s)'), (store_id, slot_spin_count, survey_complete_message))
        conn.commit()
        conn.close()
    except Exception as e:
        sys.stderr.write(f"_save_slot_settings_db error: {e}\n")


def _get_prizes(store_id: int) -> list:
    """DBから景品設定を取得"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, 'SELECT prizes_json FROM "T_店舗_景品設定" WHERE store_id = %s'), (store_id,))
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return json.loads(row[0])
    except Exception as e:
        sys.stderr.write(f"_get_prizes error: {e}\n")
    return []


def _save_prizes_db_internal(store_id: int, prizes: list) -> None:
    """DBに景品設定を保存（内部関数）"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        payload = json.dumps(prizes, ensure_ascii=False)
        cur.execute(_sql(conn, 'SELECT id FROM "T_店舗_景品設定" WHERE store_id = %s'), (store_id,))
        if cur.fetchone():
            cur.execute(_sql(conn, 'UPDATE "T_店舗_景品設定" SET prizes_json = %s, updated_at = CURRENT_TIMESTAMP WHERE store_id = %s'), (payload, store_id))
        else:
            cur.execute(_sql(conn, 'INSERT INTO "T_店舗_景品設定" (store_id, prizes_json) VALUES (%s, %s)'), (store_id, payload))
        conn.commit()
        conn.close()
    except Exception as e:
        sys.stderr.write(f"_save_prizes_db_internal error: {e}\n")


def _do_spin(cfg: Config) -> tuple:
    """スロットを5回スピンして結果を返す"""
    psum = sum(float(s.prob) for s in cfg.symbols) or 100.0
    for s in cfg.symbols:
        s.prob = float(s.prob) / psum * 100.0

    spins = []
    total_payout = 0.0
    miss_rate = cfg.miss_probability / 100.0
    normal_symbols = [s for s in cfg.symbols if not (hasattr(s, 'is_reach') and s.is_reach)]

    for _ in range(5):
        if random.random() < miss_rate:
            reel1 = random.choice(normal_symbols)
            others = [s for s in normal_symbols if s.id != reel1.id]
            reel2 = random.choice(others) if others else reel1
            reel3 = random.choice(normal_symbols)
            spins.append({
                "reels": [
                    {"id": reel1.id, "label": reel1.label, "color": reel1.color},
                    {"id": reel2.id, "label": reel2.label, "color": reel2.color},
                    {"id": reel3.id, "label": reel3.label, "color": reel3.color},
                ],
                "matched": False, "is_reach": False, "payout": 0,
            })
        else:
            symbol = choice_by_prob(cfg.symbols)
            is_reach = hasattr(symbol, 'is_reach') and symbol.is_reach
            if is_reach:
                reach_id = symbol.reach_symbol if hasattr(symbol, 'reach_symbol') else symbol.id
                orig = next((s for s in normal_symbols if s.id == reach_id), symbol)
                others = [s for s in normal_symbols if s.id != reach_id]
                r3 = random.choice(others) if others else orig
                spins.append({
                    "reels": [
                        {"id": orig.id, "label": orig.label, "color": orig.color},
                        {"id": orig.id, "label": orig.label, "color": orig.color},
                        {"id": r3.id, "label": r3.label, "color": r3.color},
                    ],
                    "matched": False, "is_reach": True,
                    "reach_symbol": {"id": orig.id, "label": orig.label, "color": orig.color},
                    "payout": 0,
                })
            else:
                payout = symbol.payout_3
                total_payout += payout
                spins.append({
                    "reels": [
                        {"id": symbol.id, "label": symbol.label, "color": symbol.color},
                        {"id": symbol.id, "label": symbol.label, "color": symbol.color},
                        {"id": symbol.id, "label": symbol.label, "color": symbol.color},
                    ],
                    "matched": True, "is_reach": False,
                    "symbol": {"id": symbol.id, "label": symbol.label, "color": symbol.color},
                    "payout": payout,
                })
    return spins, total_payout


# ---- API: スロット設定取得 ----
@bp.get('/store/<slug>/config')
def slot_config_get(slug):
    """店舗別スロット設定を取得（slug）"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, 'SELECT id FROM "T_店舗" WHERE slug = %s'), (slug,))
        row = cur.fetchone()
        conn.close()
        store_id = row[0] if row else None
    except Exception:
        store_id = None
    cfg = _get_slot_config(store_id) if store_id else _default_slot_config()
    return jsonify({
        "symbols": [asdict(s) for s in cfg.symbols],
        "reels": cfg.reels,
        "base_bet": cfg.base_bet,
        "expected_total_5": cfg.expected_total_5,
    })


# ---- API: スロット実行 ----
@bp.post('/store/<slug>/spin')
def slot_spin(slug):
    """店舗別スロット実行（slug）"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, 'SELECT id FROM "T_店舗" WHERE slug = %s'), (slug,))
        row = cur.fetchone()
        conn.close()
        store_id = row[0] if row else None
    except Exception:
        store_id = None

    cfg = _get_slot_config(store_id) if store_id else _default_slot_config()
    spins, total_payout = _do_spin(cfg)

    prize = None
    if store_id:
        prizes = _get_prizes(store_id)
        for p in prizes:
            min_score = p.get('min_score', 0)
            max_score = p.get('max_score')
            if max_score is None:
                if total_payout >= min_score:
                    prize = {"rank": p["rank"], "name": p["name"]}
                    break
            else:
                if min_score <= total_payout <= max_score:
                    prize = {"rank": p["rank"], "name": p["name"]}
                    break

    import time as _time
    result = {
        "ok": True,
        "spins": spins,
        "total_payout": total_payout,
        "expected_total_5": cfg.expected_total_5,
        "ts": int(_time.time()),
    }
    if prize:
        result["prize"] = prize
    return jsonify(result)


# ---- API: 確率計算 ----
@bp.post('/store/<slug>/calc_prob')
def slot_calc_prob(slug):
    """店舗別確率計算（slug）"""
    body = request.get_json(silent=True) or {}
    tmin = float(body.get("threshold_min", 0))
    tmax = body.get("threshold_max")
    tmax = None if tmax in (None, "", "null") else float(tmax)
    spins = max(1, int(body.get("spins", 5)))

    if "symbols" in body and body["symbols"]:
        symbols = [Symbol(
            id=s.get("id", ""), label=s.get("label", ""),
            payout_3=float(s.get("payout_3", 0)), prob=float(s.get("prob", 0)),
            color=s.get("color", "#000000"),
        ) for s in body["symbols"]]
        miss_rate = float(body.get("miss_probability", 0.0))
    else:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(_sql(conn, 'SELECT id FROM "T_店舗" WHERE slug = %s'), (slug,))
            row = cur.fetchone()
            conn.close()
            store_id = row[0] if row else None
        except Exception:
            store_id = None
        cfg = _get_slot_config(store_id) if store_id else _default_slot_config()
        symbols = list(cfg.symbols)
        miss_rate = cfg.miss_probability

    miss_sym = Symbol(id="miss", label="ハズレ", payout_3=0.0, prob=miss_rate, color="#000000")
    syms_with_miss = list(symbols) + [miss_sym]
    psum = sum(float(s.prob) for s in syms_with_miss) or 1.0
    for s in syms_with_miss:
        s.prob = float(s.prob) * 100.0 / psum

    prob_ge = prob_total_ge(syms_with_miss, spins, tmin)
    prob_le = 1.0 if tmax is None else prob_total_le(syms_with_miss, spins, tmax)
    prob_range = max(0.0, prob_le - (1.0 - prob_ge))
    return jsonify({"ok": True, "prob_ge": prob_ge, "prob_le": prob_le, "prob_range": prob_range, "tmin": tmin, "tmax": tmax, "spins": spins})


# ---- API: スロット結果保存 ----
@bp.post('/store/<slug>/slot/save_result')
def slot_save_result(slug):
    """スロット結果をセッションに保存"""
    try:
        data = request.get_json() or {}
        session['slot_total_score'] = data.get('total_score', 0)
        session['slot_prize'] = data.get('prize')
        session['slot_history'] = data.get('history', [])
        session['slot_set_scores'] = data.get('set_scores', [])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ---- API: アンケートリセット ----
@bp.post('/store/<slug>/reset_survey')
def slot_reset_survey(slug):
    """アンケートセッションをリセット"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, 'SELECT id FROM "T_店舗" WHERE slug = %s'), (slug,))
        row = cur.fetchone()
        conn.close()
        store_id = row[0] if row else None
    except Exception:
        store_id = None
    if store_id:
        session.pop(f'survey_completed_{store_id}', None)
        session.pop(f'survey_rating_{store_id}', None)
        session.pop(f'generated_review_{store_id}', None)
        session.pop(f'survey_data_{store_id}', None)
    return jsonify({"ok": True})


# ---- スロット画面（slug ベース） ----
@bp.get('/store/<slug>/slot')
def slot_page_by_slug(slug):
    """スロット画面（slug）"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, 'SELECT id FROM "T_店舗" WHERE slug = %s'), (slug,))
        row = cur.fetchone()
        conn.close()
        store_id = row[0] if row else None
    except Exception:
        store_id = None

    is_demo = request.args.get('demo', '').lower() == 'true'
    if not is_demo and store_id:
        if not session.get(f'survey_completed_{store_id}'):
            return redirect(f'/apps/survey/store/{store_id}/answer')

    slot_settings = _get_slot_settings(store_id) if store_id else {'slot_spin_count': 1, 'survey_complete_message': 'アンケートにご協力いただきありがとうございます！'}
    prizes = _get_prizes(store_id) if store_id else []
    return render_template('survey_app_slot.html',
                           store_slug=slug,
                           slot_spin_count=slot_settings['slot_spin_count'],
                           survey_complete_message=slot_settings['survey_complete_message'],
                           prizes=prizes,
                           is_demo=is_demo)


# ---- スロット結果画面（slug ベース） ----
@bp.get('/store/<slug>/slot/result')
def slot_result_by_slug(slug):
    """スロット結果画面（slug）"""
    total_score = session.pop('slot_total_score', 0)
    prize = session.pop('slot_prize', None)
    history = session.pop('slot_history', [])

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, 'SELECT id, 名称 FROM "T_店舗" WHERE slug = %s'), (slug,))
        row = cur.fetchone()
        conn.close()
        store_id = row[0] if row else None
        store_name = row[1] if row else slug
    except Exception:
        store_id = None
        store_name = slug

    survey_settings = _get_survey_settings(store_id) if store_id else {}
    google_review_url = survey_settings.get('google_review_url', '#')
    ai_review_mode = survey_settings.get('ai_review_mode', 'all')
    survey_rating = session.get(f'survey_rating_{store_id}', 0) if store_id else 0
    show_slot_review_button = (
        bool(google_review_url and google_review_url != '#') and
        (ai_review_mode == 'all' or (ai_review_mode == 'high_rating_only' and survey_rating >= 4))
    )
    return render_template('survey_app_slot_result.html',
                           total_score=total_score,
                           prize=prize,
                           history=history,
                           store={'id': store_id, 'name': store_name, 'slug': slug},
                           google_review_url=google_review_url,
                           show_slot_review_button=show_slot_review_button)


# ---- 管理画面: スロット設定保存 ----
@bp.post('/store/<int:store_id>/save_slot_config')
@require_roles(ROLES["ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def save_slot_config(store_id):
    """スロット設定を保存"""
    try:
        symbol_count = int(request.form.get('symbol_count', 0))
        symbols = []
        for i in range(symbol_count):
            sym_id = request.form.get(f'symbol_id_{i}', '').strip()
            if not sym_id:
                continue
            disabled = request.form.get(f'symbol_disabled_{i}') == 'on'
            if disabled:
                continue
            symbols.append(Symbol(
                id=sym_id,
                label=request.form.get(f'symbol_label_{i}', sym_id),
                payout_3=float(request.form.get(f'symbol_payout_{i}', 0) or 0),
                prob=float(request.form.get(f'symbol_prob_{i}', 0) or 0),
                color=request.form.get(f'symbol_color_{i}', '#888888'),
                is_reach=request.form.get(f'symbol_is_reach_{i}', 'false').lower() == 'true',
                reach_symbol=request.form.get(f'symbol_reach_symbol_{i}') or None,
            ))
        if not symbols:
            flash('シンボルが1件以上必要です', 'error')
            return redirect(url_for('survey_app.survey_settings_view', store_id=store_id))

        cfg = Config(
            symbols=symbols,
            reels=3,
            base_bet=1,
            expected_total_5=float(request.form.get('expected_total_5', 2500.0) or 2500.0),
            miss_probability=float(request.form.get('miss_probability', 0.0) or 0.0),
        )
        _save_slot_config_db(store_id, cfg)
        flash('スロット設定を保存しました', 'success')
    except Exception as e:
        sys.stderr.write(f"save_slot_config error: {e}\n")
        flash(f'保存エラー: {e}', 'error')
    return redirect(url_for('survey_app.survey_settings_view', store_id=store_id))


# ---- 管理画面: 景品設定保存 ----
@bp.post('/store/<int:store_id>/save_prizes')
@require_roles(ROLES["ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def save_prizes(store_id):
    """景品設定を保存（JSON API）"""
    try:
        data = request.get_json() or {}
        prizes = data.get('prizes', [])
        _save_prizes_db_internal(store_id, prizes)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ---- 管理画面: スロット基本設定保存 ----
@bp.post('/store/<int:store_id>/save_slot_settings')
@require_roles(ROLES["ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def save_slot_settings(store_id):
    """スロット基本設定（spin_count・メッセージ）を保存"""
    try:
        slot_spin_count = int(request.form.get('slot_spin_count', 1) or 1)
        survey_complete_message = request.form.get('survey_complete_message', '').strip() or 'アンケートにご協力いただきありがとうございます！スロットをお楽しみください。'
        _save_slot_settings_db(store_id, slot_spin_count, survey_complete_message)
        flash('スロット基本設定を保存しました', 'success')
    except Exception as e:
        sys.stderr.write(f"save_slot_settings error: {e}\n")
        flash(f'保存エラー: {e}', 'error')
    return redirect(url_for('survey_app.survey_settings_view', store_id=store_id))

# ---- API: 確率自動調整 ----
@bp.post('/store/<int:store_id>/optimize_probabilities')
@require_roles(ROLES["ADMIN"], ROLES["APP_MANAGER"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def optimize_probabilities(store_id):
    """確率自動調整API"""
    try:
        body = request.get_json(silent=True) or {}
        symbols_data = body.get('symbols', [])
        expected_total_5 = float(body.get('expected_total_5', 100.0))
        from app.utils.slot_logic import recalc_probs_inverse_and_expected
        symbols = [Symbol(
            id=s.get("id", ""), label=s.get("label", ""),
            payout_3=float(s.get("payout_3", 0)), prob=float(s.get("prob", 0)),
            color=s.get("color", "#000000"),
            is_disabled=s.get("is_disabled", False),
            is_default=s.get("is_default", False),
        ) for s in symbols_data]
        adjusted = recalc_probs_inverse_and_expected(symbols, expected_total_5)
        return jsonify({"ok": True, "symbols": [asdict(s) for s in adjusted]})
    except Exception as e:
        sys.stderr.write(f"optimize_probabilities error: {e}\n")
        return jsonify({"ok": False, "error": str(e)}), 500

# ---- API: スロット設定保存（slug, slot.jsから呼ばれる） ----
@bp.post('/store/<slug>/config')
def slot_config_save_by_slug(slug):
    """スロット設定をslugで保存（slot.jsから呼ばれる）"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(_sql(conn, 'SELECT id FROM "T_店舗" WHERE slug = %s'), (slug,))
        row = cur.fetchone()
        conn.close()
        store_id = row[0] if row else None
    except Exception:
        store_id = None
    if not store_id:
        return jsonify({"ok": False, "error": "store not found"}), 404
    body = request.get_json(silent=True) or {}
    symbols_data = body.get('symbols', [])
    if not symbols_data:
        return jsonify({"ok": False, "error": "symbols required"}), 400
    symbols = [Symbol(
        id=s.get('id', ''), label=s.get('label', ''),
        payout_3=float(s.get('payout_3', s.get('p3', 0))),
        prob=float(s.get('prob', 0)),
        color=s.get('color', '#888888'),
        is_disabled=s.get('is_disabled', False),
        is_default=s.get('is_default', False),
    ) for s in symbols_data if s.get('id')]
    if not symbols:
        return jsonify({"ok": False, "error": "no valid symbols"}), 400
    cfg = Config(
        symbols=symbols,
        reels=int(body.get('reels', 3)),
        base_bet=int(body.get('base_bet', 1)),
        expected_total_5=float(body.get('target_expected_total_5', body.get('expected_total_5', 2500.0)) or 2500.0),
        miss_probability=float(body.get('miss_probability', 0.0) or 0.0),
    )
    _save_slot_config_db(store_id, cfg)
    return jsonify({"ok": True, "symbols": [asdict(s) for s in cfg.symbols], "expected_total_5": cfg.expected_total_5})
