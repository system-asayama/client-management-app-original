# -*- coding: utf-8 -*-
"""
アンケート機能 Blueprint
"""
from flask import Blueprint, jsonify, request, render_template, session, redirect, url_for, g
from functools import wraps
import os
import sys

# store_dbをインポート
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import store_db

bp = Blueprint('survey', __name__)

# ===== 店舗識別ミドルウェア =====
@bp.url_value_preprocessor
def pull_store_slug(endpoint, values):
    """かURLから店舗slugを取得してgに保存"""
    import sys
    sys.stderr.write(f"DEBUG pull_store_slug: endpoint={endpoint}, values={values}\n")
    sys.stderr.flush()
    
    # valuesが空の場合はrequest.view_argsから取得を試みる
    from flask import request
    store_slug = None
    if values and 'store_slug' in values:
        store_slug = values.pop('store_slug')
    elif hasattr(request, 'view_args') and request.view_args and 'store_slug' in request.view_args:
        store_slug = request.view_args.get('store_slug')
    
    if store_slug:
        g.store_slug = store_slug
        sys.stderr.write(f"DEBUG pull_store_slug: store_slug={g.store_slug}\n")
        sys.stderr.flush()
        store = store_db.get_store_by_slug(g.store_slug)
        sys.stderr.write(f"DEBUG pull_store_slug: store={store}\n")
        sys.stderr.flush()
        if store:
            g.store = store
            g.store_id = store['id']
        else:
            g.store = None
            g.store_id = None
    else:
        g.store_slug = None
        g.store = None
        g.store_id = None

def require_store(f):
    """店舗が必須のルートで使用するデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.store:
            return "店舗が見つかりません", 404
        return f(*args, **kwargs)
    return decorated_function

# OpenAI クライアントを動的に取得する関数
def get_openai_client(app_type=None, app_id=None, store_id=None, tenant_id=None):
    """
    OpenAIクライアントを階層的に取得。
    優先順位: アプリ設定 > 店舗設定 > テナント設定 > 環境変数
    """
    from openai import OpenAI
    api_key = None
    
    try:
        conn = store_db.get_db_connection()
        cursor = conn.cursor()
        
        # 1. アプリ設定のキーを確認
        if app_type and app_id:
            if app_type == 'survey':
                cursor.execute("SELECT openai_api_key, store_id FROM \"T_店舗_アンケート設定\" WHERE id = %s", (app_id,))
            elif app_type == 'slot':
                cursor.execute("SELECT openai_api_key, store_id FROM \"T_店舗_スロット設定\" WHERE id = %s", (app_id,))
            
            result = cursor.fetchone()
            if result:
                if result[0]:  # アプリにAPIキーが設定されている
                    api_key = result[0]
                    conn.close()
                    return OpenAI(api_key=api_key, base_url='https://api.openai.com/v1')
                # アプリにキーがない場合、store_idを取得
                if not store_id and result[1]:
                    store_id = result[1]
        
        # 2. 店舗設定のキーを確認
        if store_id:
            cursor.execute("SELECT openai_api_key, tenant_id FROM \"T_店舗\" WHERE id = %s", (store_id,))
            result = cursor.fetchone()
            if result:
                if result[0]:  # 店舗にAPIキーが設定されている
                    api_key = result[0]
                    conn.close()
                    return OpenAI(api_key=api_key, base_url='https://api.openai.com/v1')
                # 店舗にキーがない場合、tenant_idを取得
                if not tenant_id and result[1]:
                    tenant_id = result[1]
        
        # 3. テナント設定のキーを確認
        if tenant_id:
            cursor.execute("SELECT openai_api_key FROM \"T_テナント\" WHERE id = %s", (tenant_id,))
            result = cursor.fetchone()
            if result and result[0]:
                api_key = result[0]
                conn.close()
                return OpenAI(api_key=api_key, base_url='https://api.openai.com/v1')
        
        conn.close()
    except Exception as e:
        print(f"Error getting OpenAI API key from database: {e}")
    
    # 4. 環境変数を確認
    if not api_key:
        api_key = os.environ.get('OPENAI_API_KEY')

    
    if not api_key:
        raise ValueError("OpenAI APIキーが設定されていません。アプリ、店舗、またはテナントの管理画面でAPIキーを設定してください。")
    
    return OpenAI(api_key=api_key, base_url='https://api.openai.com/v1')

def _generate_review_text(survey_data, store_id):
    """
    アンケートデータからAIを使って口コミ投稿文を生成
    """
    # アンケートアプリIDを取得
    survey_app_id = None
    try:
        conn = store_db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM T_店舗_アンケート設定 WHERE store_id = %s", (store_id,))
        result = cursor.fetchone()
        if result:
            survey_app_id = result[0]
        conn.close()
    except Exception as e:
        print(f"Error getting survey app ID: {e}")
    
    # OpenAIクライアントを取得
    try:
        openai_client = get_openai_client(
            app_type='survey',
            app_id=survey_app_id,
            store_id=store_id
        )
    except Exception as e:
        print(f"Error getting OpenAI client: {e}")
        return "口コミ投稿文の生成に失敗しました。"
    
    # アンケート設定を取得して質問文を取得
    survey_config = None
    try:
        conn = store_db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT config_json FROM T_店舗_アンケート設定 WHERE store_id = %s", (store_id,))
        result = cursor.fetchone()
        if result and result[0]:
            import json
            survey_config = json.loads(result[0])
        conn.close()
    except Exception as e:
        print(f"Error getting survey config: {e}")
    
    # アンケート回答を質問と結びつけて整形
    qa_pairs = []
    
    if survey_config and 'questions' in survey_config:
        questions = survey_config['questions']
        for i, question in enumerate(questions):
            question_id = f"q{i+1}"
            if question_id in survey_data:
                answer = survey_data[question_id]
                question_text = question.get('text', '')
                
                # 回答を整形
                if isinstance(answer, list):
                    answer_text = '、'.join(answer)
                elif question.get('type') == 'rating':
                    answer_text = f"{answer}点（5点満点）"
                elif question.get('type') == 'comment_rating':
                    # コメント（5段階）は選択肢のラベルをそのまま使用
                    answer_text = str(answer)
                else:
                    answer_text = str(answer)
                
                qa_pairs.append(f"質問: {question_text}\n回答: {answer_text}")
    else:
        # 設定がない場合は従来通り
        for key, value in survey_data.items():
            if key.startswith('q'):
                if isinstance(value, list):
                    qa_pairs.append(', '.join(value))
                else:
                    qa_pairs.append(str(value))
    
    qa_text = '\n\n'.join(qa_pairs)

    # 業種・AI指示文を取得
    ai_review_settings = {'business_type': '', 'ai_instruction': ''}
    try:
        import store_db as _store_db_ai
        ai_review_settings = _store_db_ai.get_ai_review_settings(store_id)
    except Exception as e:
        print(f"Error getting ai_review_settings: {e}")

    business_type = ai_review_settings.get('business_type', '')
    ai_instruction = ai_review_settings.get('ai_instruction', '')

    # 業種・指示文をプロンプトに展開
    business_type_line = f"\n\u3010業種】{business_type}" if business_type else ""
    ai_instruction_block = f"\n\n\u3010追加指示】\n{ai_instruction}" if ai_instruction else ""

    # 業種別のシステムプロンプト追加文
    business_system_hint = ""
    if business_type:
        business_system_hint = f"\n\u3053の口コミは「{business_type}」向けです。その業種に合った表現・用語を使い、その業種の顧客目線で自然な口コミを書いてください。"
    if ai_instruction:
        business_system_hint += f"\n追加指示: {ai_instruction}"

    # デバッグ：AIに渡されるデータをログ出力
    import sys
    sys.stderr.write("=" * 80 + "\n")
    sys.stderr.write("DEBUG: AIに渡されるアンケートデータ\n")
    sys.stderr.write("=" * 80 + "\n")
    sys.stderr.write(f"survey_data: {survey_data}\n")
    sys.stderr.write(f"survey_config questions count: {len(survey_config.get('questions', [])) if survey_config else 0}\n")
    sys.stderr.write(f"qa_pairs count: {len(qa_pairs)}\n")
    sys.stderr.write("\nqa_text:\n")
    sys.stderr.write(qa_text + "\n")
    sys.stderr.write("=" * 80 + "\n")
    sys.stderr.flush()
    
    # プロンプト作成
    sys.stderr.write("\n" + "=" * 80 + "\n")
    sys.stderr.write("DEBUG: OpenAIに送信するプロンプト\n")
    sys.stderr.write("=" * 80 + "\n")
    
    prompt = f"""以下のアンケート回答から、実際の人間が書いたような自然な口コミ投稿文を日本語で作成してください。{business_type_line}

【アンケート回答】
{qa_text}{ai_instruction_block}

【絶対に守るべきルール】
1. 上記のすべての質問と回答を考慮してください
2. 「○○がおいしい」「特に○○が印象的」「おすすめの一品」のような曖昧な表現は絶対に使わないでください
3. 料理やメニューについて言及する場合は、必ず具体的な名前（例：ハラミ、ホルモン、カルビなど）を使ってください
4. 回答に具体的な料理名が含まれている場合は、それを曖昧な表現に置き換えず、そのまま使ってください
5. 例：「ハラミ」と回答されている場合→「ハラミが美味しかった」と書く（「おすすめの一品」と書かない）
6. 自由記入欄に肯定的な文言があれば積極的に活用してください
7. 自由記入欄に「○○」のような曖昧な表現があれば、その部分を省略するか、他の質問の回答から具体的な名前を探して使ってください
8. AIが書いたと分からないよう、自然な言い回しや表現を使ってください
9. 完璧すぎる文章ではなく、少しカジュアルで人間らしい表現を心がけてください

【要件】
- 180～220文字程度で簡潔にまとめる（厳密に200文字である必要はない）
- 自然な口語体で書く（「めっちゃ」「すごく」「とても」など自然な表現を使う）
- 具体的な体験を含める
- 「です・ます」調で統一する
- 句読点や改行を適度に使って読みやすくする

口コミ投稿文:"""
    
    sys.stderr.write(prompt + "\n")
    sys.stderr.write("=" * 80 + "\n")
    sys.stderr.flush()
    
    try:
        sys.stderr.write("DEBUG: OpenAI APIを呼び出します (model=gpt-4.1-mini)\n")
        sys.stderr.flush()
        
        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": f"""あなたは実際の人間が書いたような自然な口コミ投稿文を作成する専門家です。{business_system_hint}

絶対に守るべきルール:
1. すべてのアンケート回答を考慮してください
2. 「○○がおいしい」「特に○○が印象的」「おすすめの一品」のような曘昧な表現は絶対に使わないでください
3. 料理やメニューについて言及する場合は、必ず具体的な名前（例：ハラミ、ホルモン、カルビ）を使ってください
4. 回答に具体的な料理名が含まれている場合は、それを曘昧な表現に置き換えず、そのまま使ってください
5. 例：「ハラミ」と回答→「ハラミが美味しかった」（「おすすめの一品」と書かない）
6. 自由記入欄に肯定的な文言があれば積極的に活用してください
7. 自由記入欄に「○○」のような曘昧な表現があれば、他の質問の回答から具体的な名前を探して使ってください
8. AIが書いたと分からないよう、自然な言い回しや表現を使ってください
9. 言い回しのトーンをランダムに変化させてください：
   - 柔らかい表現：「めっちゃ」「すごく」「とても」「かなり」「本当に」「さすが」
   - 普通の表現：「非常に」「大変」「とても」「かなり」
   - 固めの表現：「大変」「非常に」「特に」「大変満足」
10. 文体のバリエーションを持たせてください：
   - カジュアル：口語的で親しみやすい表現
   - 丁寧：落ち着いた丁寧な表現
   - バランス型：丁寧さと親しみやすさの中間
11. 文章の長さは180～220文字程度を目安にしてください"""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        generated_text = response.choices[0].message.content.strip()
        
        sys.stderr.write("\n" + "=" * 80 + "\n")
        sys.stderr.write("DEBUG: OpenAIからのレスポンス\n")
        sys.stderr.write("=" * 80 + "\n")
        sys.stderr.write(f"生成されたレビュー:\n{generated_text}\n")
        sys.stderr.write("=" * 80 + "\n")
        sys.stderr.flush()
        
        return generated_text
    except Exception as e:
        print(f"Error generating review text: {e}")
        return "口コミ投稿文の生成に失敗しました。"


# ===== ルート =====
@bp.get("/store/<store_slug>")
@require_store
def store_index():
    """店舗トップ - アンケートへリダイレクト"""
    # アンケート未回答の場合はアンケートページへ
    if not session.get(f'survey_completed_{g.store_id}'):
        return redirect(url_for('survey.survey', store_slug=g.store_slug))
    return redirect(url_for('slot.slot_page', store_slug=g.store_slug))

@bp.get("/store/<store_slug>/survey")
@require_store
def survey():
    """アンケートページ"""
    print(f"DEBUG: survey() called, store_id={g.store_id}, store={g.store}")
    survey_config = store_db.get_survey_config(g.store_id)
    print(f"DEBUG: survey_config={survey_config}")
    return render_template("survey.html", 
                         store=g.store,
                         survey_config=survey_config)

@bp.post("/store/<store_slug>/submit_survey")
@require_store
def submit_survey():
    """アンケート送信"""
    try:
        body = request.get_json(silent=True) or {}
        import sys
        sys.stderr.write(f"DEBUG submit_survey: body = {body}\n")
        sys.stderr.flush()
        # 最初の質問の回答を評価として使用（5段階評価の場合）
        rating = 3  # デフォルト
        first_answer = body.get('q1', '')

        # アンケート設定を取得して最初の質問タイプを確認
        survey_config_for_type = None
        try:
            survey_config_for_type = store_db.get_survey_config(g.store_id)
        except Exception:
            pass
        first_question_type = 'rating'
        first_question_options = []
        if survey_config_for_type and survey_config_for_type.get('questions'):
            first_q = survey_config_for_type['questions'][0]
            first_question_type = first_q.get('type', 'rating')
            first_question_options = first_q.get('options', [])

        if first_question_type == 'rating':
            # 星評価：数値が直接入っている
            try:
                rating = int(first_answer)
                if rating < 1:
                    rating = 1
                elif rating > 5:
                    rating = 5
            except (ValueError, TypeError):
                rating = 3
        elif first_question_type in ('comment_rating', 'radio', 'checkbox'):
            # コメント（5段階）：選択肢の位置を数値に変換（1番目=5点、最後=1点）
            opts = first_question_options if first_question_options else ['非常に満足', '満足', '普通', 'やや不満', '非常に不満']
            try:
                idx = opts.index(first_answer)
                # 先頭の選択肢の方が高評価（例: 非常に満足=5、非常に不満=1）
                rating = len(opts) - idx
            except ValueError:
                # 選択肢にない場合はテキストマッチングで推測
                if '非常に満足' in first_answer or '強く思う' in first_answer or '非常に良い' in first_answer:
                    rating = 5
                elif '満足' in first_answer or '思う' in first_answer or '良い' in first_answer:
                    rating = 4
                elif '普通' in first_answer or 'どちらとも' in first_answer:
                    rating = 3
                elif 'やや' in first_answer:
                    rating = 2
                else:
                    rating = 1
        else:
            # その他のタイプ：数値変換を試みる
            try:
                rating = int(first_answer)
                if rating < 1:
                    rating = 1
                elif rating > 5:
                    rating = 5
            except (ValueError, TypeError):
                rating = 3
        
        # ratingをbodyに追加
        body['rating'] = rating
        
        # アンケート回答を保存
        sys.stderr.write(f"DEBUG submit_survey: rating = {rating}, store_id = {g.store_id}\n")
        sys.stderr.flush()
        store_db.save_survey_response(g.store_id, body)
        
        # 口コミ投稿促進設定を取得
        from review_prompt_settings import get_review_prompt_mode
        review_mode = get_review_prompt_mode(g.store_id)
        sys.stderr.write(f"DEBUG: rating = {rating}, review_mode = {review_mode}\n")
        sys.stderr.flush()
        
        # 設定に応じてAIレビュー生成とリダイレクト先を制御
        generated_review = ''
        redirect_url = f"/store/{g.store_slug}/slot"  # デフォルトはスロットページ
        
        # 「星4以上のみ投稿を促す」設定の場合
        if review_mode == 'high_rating_only':
            if rating >= 4:
                # 星4以上のAIレビュー生成
                sys.stderr.write("DEBUG: AIレビュー生成を開始します（星4以上）\n")
                sys.stderr.flush()
                try:
                    generated_review = _generate_review_text(body, g.store_id)
                    sys.stderr.write(f"DEBUG: AIレビュー生成成功: {generated_review[:100]}...\n")
                    sys.stderr.flush()
                except Exception as e:
                    sys.stderr.write(f"ERROR: AIレビュー生成失敗: {e}\n")
                    import traceback
                    sys.stderr.write(traceback.format_exc())
                    sys.stderr.flush()
                redirect_url = f"/store/{g.store_slug}/review_confirm"
            else:
                # 星3以下はスロットページに直接遷移
                sys.stderr.write("DEBUG: 星3以下のためスロットページに遷移\n")
                sys.stderr.flush()
                redirect_url = f"/store/{g.store_slug}/slot"
        else:
            # 「全ての評価に投稿を促す」設定の場合
            sys.stderr.write("DEBUG: AIレビュー生成を開始します（全ての評価）\n")
            sys.stderr.flush()
            try:
                generated_review = _generate_review_text(body, g.store_id)
                sys.stderr.write(f"DEBUG: AIレビュー生成成功: {generated_review[:100]}...\n")
                sys.stderr.flush()
            except Exception as e:
                sys.stderr.write(f"ERROR: AIレビュー生成失敗: {e}\n")
                import traceback
                sys.stderr.write(traceback.format_exc())
                sys.stderr.flush()
            redirect_url = f"/store/{g.store_slug}/review_confirm"
        
        # セッションにアンケート完了フラグと評価を設定
        session[f'survey_completed_{g.store_id}'] = True
        session[f'survey_rating_{g.store_id}'] = rating
        session[f'generated_review_{g.store_id}'] = generated_review
        session[f'survey_data_{g.store_id}'] = body  # アンケートデータも保存
        
        return jsonify({
            "ok": True, 
            "message": "アンケートにご協力いただきありがとうございます！",
            "rating": rating,
            "generated_review": generated_review,
            "redirect_url": redirect_url
        })
    except Exception as e:
        import sys
        sys.stderr.write(f"ERROR submit_survey: {e}\n")
        sys.stderr.flush()
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 400
@bp.post("/store/<store_slug>/reset_survey")
@require_store
def reset_survey():
    """アンケートをリセット"""
    session.pop(f'survey_completed_{g.store_id}', None)
    session.pop(f'survey_rating_{g.store_id}', None)
    session.pop(f'generated_review_{g.store_id}', None)
    return jsonify({"ok": True, "message": "アンケートをリセットしました"})

@bp.get("/store/<store_slug>/review_confirm")
@require_store
def review_confirm():
    """口コミ確認ページ"""
    from review_prompt_settings import should_show_review_button, get_review_prompt_mode
    import sys
    
    generated_review = session.get(f'generated_review_{g.store_id}', '')
    google_review_url = store_db.get_google_review_url(g.store_id)
    rating = session.get(f'survey_rating_{g.store_id}', 0)
    
    # デバッグログ
    mode = get_review_prompt_mode(g.store_id)
    sys.stderr.write(f"DEBUG review_confirm: store_id={g.store_id}, rating={rating}, mode={mode}\n")
    sys.stderr.flush()
    
    # 設定に基づいてレビューボタンを表示するか判定
    show_review_button = should_show_review_button(g.store_id, rating)
    sys.stderr.write(f"DEBUG review_confirm: show_review_button={show_review_button}\n")
    sys.stderr.flush()
    
    return render_template("review_confirm.html",
        store=g.store,
        store_slug=g.store_slug,
        generated_review=generated_review,
        google_review_url=google_review_url,
        rating=rating,
        show_review_button=show_review_button
    )
