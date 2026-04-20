# -*- coding: utf-8 -*-
"""
定款作成アプリ Blueprint
freee会社設立と同様のステップ形式UIで定款を作成する
"""
import io
import json
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, session, send_file
)
from app.utils import require_roles, ROLES
# from app.utils.inkan_pdf import generate_inkan_pdf  # LibreOffice UNO版（スラグサイズ超過のため無効化）
from app.db import SessionLocal
from app.models_login import TeikanDocument

bp = Blueprint('teikan', __name__, url_prefix='/apps/teikan')


def get_session_data():
    """セッションから定款データを取得する"""
    return session.get('teikan_data', {})


def save_session_data(data):
    """定款データをセッションに保存する"""
    session['teikan_data'] = data
    session.modified = True


def autosave_draft(data):
    """各ステップ保存時に自動的にDBに下書き保存するヘルパー関数"""
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    user_id = session.get('user_id')
    draft_id = session.get('teikan_draft_id')  # 現在編集中の下書きID

    db = SessionLocal()
    try:
        from app.db import Base, engine
        Base.metadata.create_all(bind=engine)

        company_name = data.get('company_name', '')
        company_type = data.get('company_type', '合同会社')
        data_json = json.dumps(data, ensure_ascii=False)

        if draft_id:
            # 既存の下書きを更新
            doc = db.query(TeikanDocument).filter(
                TeikanDocument.id == draft_id,
                TeikanDocument.tenant_id == tenant_id
            ).first()
            if doc and doc.status == 'draft':
                doc.company_name = company_name
                doc.company_type = company_type
                doc.data_json = data_json
                db.commit()
                return  # 更新成功

        # 新規下書き作成
        doc = TeikanDocument(
            tenant_id=tenant_id,
            store_id=store_id,
            created_by=user_id,
            company_name=company_name,
            company_type=company_type,
            status='draft',
            data_json=data_json
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        session['teikan_draft_id'] = doc.id  # 下書きIDをセッションに保存
        session.modified = True
    except Exception:
        db.rollback()
    finally:
        db.close()


@bp.route('/')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def index():
    """定款アプリトップページ"""
    return render_template('teikan/index.html')


@bp.route('/select_type')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def select_type():
    """法人形態選択画面"""
    return render_template('teikan/select_type.html')


@bp.route('/new')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def new_document():
    """新規定款作成：セッションをクリアして法人形態選択画面へ"""
    session.pop('teikan_data', None)
    session.pop('teikan_draft_id', None)
    session.modified = True
    return redirect(url_for('teikan.select_type'))


@bp.route('/start/<company_type>')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def start_with_type(company_type):
    """法人形態を選択して定款作成を開始する"""
    session.pop('teikan_data', None)
    session.pop('teikan_draft_id', None)
    data = {'company_type': company_type}
    save_session_data(data)
    return redirect(url_for('teikan.confirm'))


@bp.route('/step1', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def step1():
    """ステップ1: 基本情報入力（法人形態・商号・住所・登記方法）"""
    data = get_session_data()

    if request.method == 'POST':
        data['company_type'] = request.form.get('company_type', '合同会社')
        data['company_name'] = request.form.get('company_name', '')
        data['company_name_kana'] = request.form.get('company_name_kana', '')
        data['company_type_position'] = request.form.get('company_type_position', 'before')
        data['registration_method'] = request.form.get('registration_method', '法務局に直接提出')
        data['postal_code'] = request.form.get('postal_code', '')
        data['address'] = request.form.get('address', '')
        data['address_detail'] = request.form.get('address_detail', '')
        if request.form.get('capital_from_step1'):
            data['capital'] = request.form.get('capital', '0')
        data['phone'] = request.form.get('phone', '')
        data['has_board_of_directors'] = request.form.get('has_board_of_directors', 'false')
        save_session_data(data)
        autosave_draft(data)
        return redirect(url_for('teikan.confirm'))

    return render_template('teikan/step1.html', data=data)


@bp.route('/step2', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def step2():
    """ステップ2: 社員情報入力（代表社員・出資金・資本金）"""
    data = get_session_data()

    if request.method == 'POST':
        members = []
        member_count = int(request.form.get('member_count', 1))
        for i in range(member_count):
            member = {
                'name': request.form.get(f'member_name_{i}', ''),
                'name_kana': request.form.get(f'member_name_kana_{i}', ''),
                'is_representative': request.form.get(f'is_representative_{i}') == 'on',
                'contribution': request.form.get(f'contribution_{i}', '0'),
                'postal_code': request.form.get(f'member_postal_{i}', ''),
                'address': request.form.get(f'member_address_{i}', ''),
                'phone': request.form.get(f'member_phone_{i}', ''),
                'birth_era': request.form.get(f'member_birth_era_{i}', ''),
                'birth_year': request.form.get(f'member_birth_year_{i}', ''),
                'birth_month': request.form.get(f'member_birth_month_{i}', ''),
                'birth_day': request.form.get(f'member_birth_day_{i}', ''),
            }
            if member['name']:
                members.append(member)

        data['members'] = members
        save_session_data(data)
        autosave_draft(data)
        return redirect(url_for('teikan.confirm'))

    return render_template('teikan/step2.html', data=data)


@bp.route('/step3', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def step3():
    """ステップ3: 事業目的入力"""
    data = get_session_data()

    if request.method == 'POST':
        purposes = []
        purpose_count = int(request.form.get('purpose_count', 1))
        for i in range(purpose_count):
            p = request.form.get(f'purpose_{i}', '').strip()
            if p:
                purposes.append(p)
        last_item = '前（各）号に附帯関連する一切の事業'
        if purposes and purposes[-1] != last_item:
            purposes.append(last_item)

        data['purposes'] = purposes
        save_session_data(data)
        autosave_draft(data)
        return redirect(url_for('teikan.confirm'))

    return render_template('teikan/step3.html', data=data)


@bp.route('/step4', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def step4():
    """ステップ4: 決算期・その他設定"""
    data = get_session_data()

    if request.method == 'POST':
        data['fiscal_start_month'] = request.form.get('fiscal_start_month', '3')
        data['fiscal_start_day'] = request.form.get('fiscal_start_day', '1')
        data['fiscal_end_month'] = request.form.get('fiscal_end_month', '2')
        data['fiscal_end_day'] = request.form.get('fiscal_end_day', '末日')
        data['established_date'] = request.form.get('established_date', '')
        save_session_data(data)
        autosave_draft(data)
        return redirect(url_for('teikan.confirm'))

    return render_template('teikan/step4.html', data=data)


@bp.route('/confirm')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def confirm():
    """確認画面：入力内容の確認（未入力でも表示、各項目から編集）"""
    data = get_session_data()
    return render_template('teikan/confirm.html', data=data)


@bp.route('/preview')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def preview():
    """定款プレビュー（HTML表示）"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    return render_template('teikan/preview.html', data=data)


@bp.route('/download_pdf')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def download_pdf():
    """定款PDFをダウンロードする"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))

    try:
        pdf_bytes = generate_teikan_pdf(data)
        company_name = data.get('company_name', '定款')
        filename = f"{company_name}_定款.pdf"

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(f'PDF生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.preview'))


@bp.route('/reset')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def reset():
    """セッションデータをリセットして最初から"""
    session.pop('teikan_data', None)
    return redirect(url_for('teikan.step1'))


@bp.route('/save', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def save():
    """定款データをDBに完成保存する（下書きがあれば更新、なければ新規作成）"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.confirm'))

    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    user_id = session.get('user_id')
    draft_id = session.get('teikan_draft_id')
    db = SessionLocal()
    try:
        from app.db import Base, engine
        Base.metadata.create_all(bind=engine)

        company_name = data.get('company_name', '')
        company_type = data.get('company_type', '合同会社')
        data_json = json.dumps(data, ensure_ascii=False)

        if draft_id:
            # 既存の下書きを完成に更新
            doc = db.query(TeikanDocument).filter(
                TeikanDocument.id == draft_id,
                TeikanDocument.tenant_id == tenant_id
            ).first()
            if doc:
                doc.company_name = company_name
                doc.company_type = company_type
                doc.status = 'completed'
                doc.data_json = data_json
                db.commit()
                flash(f'「{company_type}{company_name}」の定款を保存しました', 'success')
                session.pop('teikan_data', None)
                session.pop('teikan_draft_id', None)
                return redirect(url_for('teikan.history'))

        # 新規完成保存
        doc = TeikanDocument(
            tenant_id=tenant_id,
            store_id=store_id,
            created_by=user_id,
            company_name=company_name,
            company_type=company_type,
            status='completed',
            data_json=data_json
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        flash(f'「{doc.company_type}{doc.company_name}」の定款を保存しました', 'success')
        session.pop('teikan_data', None)
        session.pop('teikan_draft_id', None)
        return redirect(url_for('teikan.history'))
    except Exception as e:
        db.rollback()
        flash(f'保存エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.confirm'))
    finally:
        db.close()


@bp.route('/new_corporation')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def new_corporation():
    """新規法人設立：セッションをクリアして中間ページへ"""
    session.pop('teikan_data', None)
    session.pop('teikan_draft_id', None)
    session.modified = True
    return redirect(url_for('teikan.new_setup'))


@bp.route('/new_setup')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def new_setup():
    """新しい法人を設立する中間ページ"""
    data = get_session_data()
    has_data = bool(data.get('company_name'))
    return render_template('teikan/new_setup.html', has_data=has_data)


@bp.route('/history')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def history():
    """作成済み定款一覧"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        from app.db import Base, engine
        Base.metadata.create_all(bind=engine)

        docs = db.query(TeikanDocument).filter(
            TeikanDocument.tenant_id == tenant_id
        ).order_by(TeikanDocument.created_at.desc()).all()
        return render_template('teikan/history.html', docs=docs)
    except Exception as e:
        flash(f'一覧取得エラー: {str(e)}', 'error')
        return render_template('teikan/history.html', docs=[])
    finally:
        db.close()


@bp.route('/history/<int:doc_id>')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def history_detail(doc_id):
    """保存済み定款の詳細プレビュー"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        doc = db.query(TeikanDocument).filter(
            TeikanDocument.id == doc_id,
            TeikanDocument.tenant_id == tenant_id
        ).first()
        if not doc:
            flash('定款が見つかりません', 'error')
            return redirect(url_for('teikan.history'))
        data = json.loads(doc.data_json)
        return render_template('teikan/preview.html', data=data, doc=doc, readonly=True)
    finally:
        db.close()


@bp.route('/history/<int:doc_id>/download')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def history_download(doc_id):
    """保存済み定款のPDFダウンロード"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        doc = db.query(TeikanDocument).filter(
            TeikanDocument.id == doc_id,
            TeikanDocument.tenant_id == tenant_id
        ).first()
        if not doc:
            flash('定款が見つかりません', 'error')
            return redirect(url_for('teikan.history'))
        data = json.loads(doc.data_json)
        pdf_bytes = generate_teikan_pdf(data)
        filename = f"{doc.company_type}{doc.company_name}_定款.pdf"
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(f'PDF生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.history'))
    finally:
        db.close()


@bp.route('/history/<int:doc_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def history_delete(doc_id):
    """保存済み定款の削除"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        doc = db.query(TeikanDocument).filter(
            TeikanDocument.id == doc_id,
            TeikanDocument.tenant_id == tenant_id
        ).first()
        if not doc:
            flash('定款が見つかりません', 'error')
            return redirect(url_for('teikan.history'))
        name = f"{doc.company_type}{doc.company_name}"
        db.delete(doc)
        db.commit()
        flash(f'「{name}」の定款を削除しました', 'success')
        return redirect(url_for('teikan.history'))
    except Exception as e:
        db.rollback()
        flash(f'削除エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.history'))
    finally:
        db.close()


@bp.route('/history/<int:doc_id>/edit')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def history_edit(doc_id):
    """保存済み定款をセッションに読み込んで編集再開"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        doc = db.query(TeikanDocument).filter(
            TeikanDocument.id == doc_id,
            TeikanDocument.tenant_id == tenant_id
        ).first()
        if not doc:
            flash('定款が見つかりません', 'error')
            return redirect(url_for('teikan.history'))
        data = json.loads(doc.data_json)
        save_session_data(data)
        session['teikan_draft_id'] = doc.id  # 編集中のドキュメントIDをセッションに保存
        session.modified = True
        flash('法人データを読み込みました', 'info')
        return redirect(url_for('teikan.new_setup'))
    finally:
        db.close()


def generate_teikan_pdf(data):
    """
    定款PDFを生成する（ReportLabを使用）
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    # 日本語フォントの設定（リポジトリ内 → システムの順に探索）
    font_candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts', 'ipag.ttf'),
        '/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf',
        '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf',
    ]
    jp_font_path = None
    for candidate in font_candidates:
        if os.path.exists(candidate):
            jp_font_path = candidate
            break

    if jp_font_path:
        try:
            if 'JapaneseGothic' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('JapaneseGothic', jp_font_path))
            font_name = 'JapaneseGothic'
            font_bold = 'JapaneseGothic'
        except Exception:
            font_name = 'Helvetica'
            font_bold = 'Helvetica-Bold'
    else:
        font_name = 'Helvetica'
        font_bold = 'Helvetica-Bold'

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margin_left = 25 * mm
    margin_right = 25 * mm
    margin_top = 25 * mm
    margin_bottom = 20 * mm
    content_width = width - margin_left - margin_right

    y_ref = [height - margin_top]

    def get_y():
        return y_ref[0]

    def set_y(val):
        y_ref[0] = val

    def new_page():
        c.showPage()
        set_y(height - margin_top)

    def check_page_break(needed_mm=25):
        if get_y() < margin_bottom + needed_mm * mm:
            new_page()

    def draw_wrapped_text(text, x, y_pos, max_width, font=font_name, size=10.5, line_height=16):
        c.setFont(font, size)
        line = ''
        lines = []
        for char in text:
            test_line = line + char
            if c.stringWidth(test_line, font, size) <= max_width:
                line = test_line
            else:
                if line:
                    lines.append(line)
                line = char
        if line:
            lines.append(line)

        for ln in lines:
            if y_pos < margin_bottom + 10 * mm:
                new_page()
                y_pos = height - margin_top
            c.drawString(x, y_pos, ln)
            y_pos -= line_height
        return y_pos

    def draw_chapter(title_text):
        check_page_break(30)
        c.setFont(font_bold, 12)
        tw = c.stringWidth(title_text, font_bold, 12)
        c.drawString((width - tw) / 2, get_y(), title_text)
        set_y(get_y() - 25)

    def draw_article(article_num, title_text, content_lines):
        check_page_break(25)
        c.setFont(font_bold, 10.5)
        header = f'第{article_num}条（{title_text}）'
        c.drawString(margin_left, get_y(), header)
        set_y(get_y() - 18)
        for line in content_lines:
            if not line:
                set_y(get_y() - 8)
                continue
            check_page_break(15)
            indent = margin_left + 5 * mm
            new_y = draw_wrapped_text(line, indent, get_y(), content_width - 10 * mm, size=10.5, line_height=16)
            set_y(new_y - 2)
        set_y(get_y() - 8)

    # ===== 共通データ取得 =====
    company_name = data.get('company_name', '')
    company_type = data.get('company_type', '合同会社')
    purposes = data.get('purposes', [])
    address = data.get('address', '') + data.get('address_detail', '')
    capital = data.get('capital', '0')
    try:
        capital_int = int(str(capital).replace(',', '').replace('円', ''))
        capital_str = f'{capital_int:,}円'
    except Exception:
        capital_str = f'{capital}円'
    members = data.get('members', [])
    fiscal_start_month = data.get('fiscal_start_month', '3')
    fiscal_start_day = data.get('fiscal_start_day', '1')
    fiscal_end_month = data.get('fiscal_end_month', '2')
    fiscal_end_day = data.get('fiscal_end_day', '末日')
    if fiscal_end_day == '末日':
        fiscal_end_str = f'{fiscal_end_month}月末日'
    else:
        fiscal_end_str = f'{fiscal_end_month}月{fiscal_end_day}日'
    established_date = data.get('established_date', '') or '令和　　年　　月　　日'
    rep_members = [m for m in members if m.get('is_representative')]
    if not rep_members and members:
        rep_members = [members[0]]
    rep_lines = [f'　{m.get("name", "")}' for m in rep_members] or ['　（代表者氏名）']

    # ===== 表紙 =====
    c.setFont(font_bold, 18)
    title = '定　　款'
    title_width = c.stringWidth(title, font_bold, 18)
    c.drawString((width - title_width) / 2, get_y(), title)
    set_y(get_y() - 40)
    c.setFont(font_bold, 14)
    cn = f'{company_type}{company_name}'
    cn_width = c.stringWidth(cn, font_bold, 14)
    c.drawString((width - cn_width) / 2, get_y(), cn)
    set_y(get_y() - 60)

    # ===== 法人形態別テンプレート =====
    if company_type == '合同会社':
        # ---------- 合同会社 ----------
        draw_chapter('第一章　総則')
        draw_article('1', '商号', [f'当会社は、合同会社{company_name}と称する。'])
        purpose_lines = ['当会社は、次の事業を営むことを目的とする。']
        for i, p in enumerate(purposes, 1):
            purpose_lines.append(f'　{i}．{p}')
        draw_article('2', '目的', purpose_lines)
        draw_article('3', '本店の所在地', [f'当会社は、本店を{address}に置く。'])
        draw_article('4', '公告方法', ['当会社の公告は、官報に掲載する方法により行う。'])

        draw_chapter('第二章　社員及び出資')
        contribution_lines = ['社員の氏名、住所及び出資の目的並びにその価額は、次のとおりである。']
        for m in members:
            contrib = m.get('contribution', '0')
            try:
                contrib_str = f"{int(str(contrib).replace(',','').replace('円','')):,}円"
            except Exception:
                contrib_str = f'{contrib}円'
            contribution_lines += [f'　氏名：{m.get("name","")}', f'　住所：{m.get("address","")}', f'　出資の価額：金{contrib_str}', '']
        draw_article('5', '社員の出資', contribution_lines)
        draw_article('6', '資本金の額', [f'当会社の資本金の額は、金{capital_str}とする。'])

        draw_chapter('第三章　業務執行及び代表')
        draw_article('7', '業務執行社員', ['当会社の業務は、社員全員が執行する。', '業務を執行する社員は、当会社を代表する。'])
        draw_article('8', '代表社員', ['当会社を代表する社員は、次のとおりとする。'] + rep_lines)
        draw_article('9', '業務執行の決定', ['当会社の業務執行は、社員の過半数をもって決定する。'])

        draw_chapter('第四章　計算')
        draw_article('10', '事業年度', [f'当会社の事業年度は、毎年{fiscal_start_month}月{fiscal_start_day}日から翌年{fiscal_end_str}までとする。'])
        draw_article('11', '利益の配当', ['当会社は、毎事業年度終了後、社員の出資の価額に応じて利益の配当を行う。'])

        draw_chapter('第五章　附則')
        draw_article('12', '設立に際して出資される財産の価額', [f'当会社の設立に際して出資される財産の価額は、金{capital_str}とする。'])
        draw_article('13', '最初の事業年度', [f'当会社の最初の事業年度は、当会社成立の日から{fiscal_end_str}までとする。'])
        draw_article('14', '設立時代表社員', ['当会社の設立時の代表社員は、次のとおりとする。'] + rep_lines)
        draw_article('15', '附則', [f'当会社の定款は、{established_date}に作成した。'])

        check_page_break(60)
        set_y(get_y() - 20)
        c.setFont(font_name, 10.5)
        c.drawString(margin_left, get_y(), '以上、合同会社設立のため、この定款を作成し、社員が記名押印する。')
        set_y(get_y() - 30)
        c.drawString(margin_left, get_y(), f'　　　　　　　　　　　　　　　　　　　　{established_date}')
        set_y(get_y() - 30)
        for m in members:
            check_page_break(20)
            c.drawString(margin_left + 20 * mm, get_y(), f'社員　{m.get("name", "")}　　　　　　　印')
            set_y(get_y() - 25)

    elif company_type == '株式会社':
        # ---------- 株式会社 ----------
        total_shares = data.get('total_shares', '400')
        draw_chapter('第一章　総則')
        draw_article('1', '商号', [f'当会社は、株式会社{company_name}と称する。'])
        purpose_lines = ['当会社は、次の事業を営むことを目的とする。']
        for i, p in enumerate(purposes, 1):
            purpose_lines.append(f'　{i}．{p}')
        draw_article('2', '目的', purpose_lines)
        draw_article('3', '本店の所在地', [f'当会社は、本店を{address}に置く。'])
        draw_article('4', '公告方法', ['当会社の公告は、官報に掲載する方法により行う。'])

        draw_chapter('第二章　株式')
        draw_article('5', '発行可能株式総数', [f'当会社の発行可能株式総数は、{total_shares}株とする。'])
        draw_article('6', '株券の不発行', ['当会社の株式については、株券を発行しない。'])
        draw_article('7', '株式の譲渡制限', ['当会社の株式を譲渡するには、取締役会の承認を要する。ただし、当会社の株主に譲渡する場合は、この限りでない。'])

        draw_chapter('第三章　株主総会')
        draw_article('8', '招集', ['当会社の定時株主総会は、毎事業年度終了後３ヶ月以内に招集し、臨時株主総会は、必要に応じて招集する。'])
        draw_article('9', '議長', ['株主総会の議長は、代表取締役社長がこれに当たる。'])
        draw_article('10', '決議', ['株主総会の普通決議は、法令に別段の定めがある場合を除き、議決権を行使することができる株主の議決権の過半数を有する株主が出席し、出席した当該株主の議決権の過半数をもって行う。'])

        draw_chapter('第四章　取締役')
        draw_article('11', '取締役の員数', ['当会社の取締役は、１名以上とする。'])
        draw_article('12', '取締役の選任', ['取締役は、株主総会の決議によって選任する。'])
        draw_article('13', '代表取締役', ['当会社の代表取締役は、取締役の互選によって定める。'])
        draw_article('14', '取締役の任期', ['取締役の任期は、選任後２年以内に終了する事業年度のうち最終のものに関する定時株主総会の終結の時までとする。ただし、定款変更その他正当な事由がある場合には、株主総会の決議によって短縮することができる。'])

        draw_chapter('第五章　計算')
        draw_article('15', '事業年度', [f'当会社の事業年度は、毎年{fiscal_start_month}月{fiscal_start_day}日から翌年{fiscal_end_str}までとする。'])
        draw_article('16', '剰余金の配当', ['当会社の剰余金の配当は、毎事業年度末日の最終の株主名簿に記載された株主又は登録株式質権者に対して行う。'])

        draw_chapter('第六章　附則')
        draw_article('17', '設立に際して出資される財産の価額', [f'当会社の設立に際して出資される財産の価額は、金{capital_str}とする。'])
        draw_article('18', '最初の事業年度', [f'当会社の最初の事業年度は、当会社成立の日から{fiscal_end_str}までとする。'])
        draw_article('19', '設立時取締役', ['当会社の設立時取締役は、次のとおりとする。'] + rep_lines)
        draw_article('20', '附則', [f'当会社の定款は、{established_date}に作成した。'])

        check_page_break(60)
        set_y(get_y() - 20)
        c.setFont(font_name, 10.5)
        c.drawString(margin_left, get_y(), '以上、株式会社設立のため、この定款を作成し、発起人が記名押印する。')
        set_y(get_y() - 30)
        c.drawString(margin_left, get_y(), f'　　　　　　　　　　　　　　　　　　　　{established_date}')
        set_y(get_y() - 30)
        for m in members:
            check_page_break(20)
            c.drawString(margin_left + 20 * mm, get_y(), f'発起人　{m.get("name", "")}　　　　　　　印')
            set_y(get_y() - 25)

    elif company_type == '一般社団法人':
        # ---------- 一般社団法人 ----------
        draw_chapter('第一章　総則')
        draw_article('1', '名称', [f'当法人は、一般社団法人{company_name}と称する。'])
        purpose_lines = ['当法人は、次の事業を行うことを目的とする。']
        for i, p in enumerate(purposes, 1):
            purpose_lines.append(f'　{i}．{p}')
        draw_article('2', '目的', purpose_lines)
        draw_article('3', '主たる事務所の所在地', [f'当法人は、主たる事務所を{address}に置く。'])
        draw_article('4', '公告方法', ['当法人の公告は、官報に掲載する方法により行う。'])

        draw_chapter('第二章　会員')
        draw_article('5', '会員の種別', ['当法人の会員は、次の２種とする。', '　１．正会員　当法人の目的に賛同して入会した個人又は団体', '　２．賛助会員　当法人の事業を賛助するために入会した個人又は団体'])
        draw_article('6', '入会', ['当法人の会員になろうとする者は、理事会が別に定める入会申込書を提出し、理事会の承認を得なければならない。'])
        draw_article('7', '会費', ['会員は、社員総会において別に定める会費を納入しなければならない。'])

        draw_chapter('第三章　社員総会')
        draw_article('8', '社員総会の構成', ['当法人の社員総会は、正会員をもって構成する。'])
        draw_article('9', '社員総会の開催', ['当法人の定時社員総会は、毎事業年度終了後３ヶ月以内に開催し、臨時社員総会は、必要に応じて開催する。'])
        draw_article('10', '社員総会の決議', ['社員総会の決議は、法令又はこの定款に別段の定めがある場合を除き、総社員の議決権の過半数を有する社員が出席し、出席した当該社員の議決権の過半数をもって行う。'])

        draw_chapter('第四章　役員')
        draw_article('11', '役員の設置', ['当法人に、理事１名以上及び監事１名を置く。'])
        draw_article('12', '役員の選任', ['理事及び監事は、社員総会の決議によって選任する。'])
        draw_article('13', '代表理事', ['当法人の代表理事は、理事の互選によって定める。'])
        draw_article('14', '役員の任期', ['理事の任期は、選任後２年以内に終了する事業年度のうち最終のものに関する定時社員総会の終結の時までとする。', '監事の任期は、選任後２年以内に終了する事業年度のうち最終のものに関する定時社員総会の終結の時までとする。'])

        draw_chapter('第五章　計算')
        draw_article('15', '事業年度', [f'当法人の事業年度は、毎年{fiscal_start_month}月{fiscal_start_day}日から翌年{fiscal_end_str}までとする。'])
        draw_article('16', '剰余金の分配の禁止', ['当法人は、剰余金の分配を行わない。'])

        draw_chapter('第六章　附則')
        draw_article('17', '最初の事業年度', [f'当法人の最初の事業年度は、当法人成立の日から{fiscal_end_str}までとする。'])
        draw_article('18', '設立時役員', ['当法人の設立時理事は、次のとおりとする。'] + rep_lines)
        draw_article('19', '附則', [f'当法人の定款は、{established_date}に作成した。'])

        check_page_break(60)
        set_y(get_y() - 20)
        c.setFont(font_name, 10.5)
        c.drawString(margin_left, get_y(), '以上、一般社団法人設立のため、この定款を作成し、設立時社員が記名押印する。')
        set_y(get_y() - 30)
        c.drawString(margin_left, get_y(), f'　　　　　　　　　　　　　　　　　　　　{established_date}')
        set_y(get_y() - 30)
        for m in members:
            check_page_break(20)
            c.drawString(margin_left + 20 * mm, get_y(), f'設立時社員　{m.get("name", "")}　　　　　　　印')
            set_y(get_y() - 25)

    c.save()
    buffer.seek(0)
    return buffer.read()


# ============================================================
# 登記書類作成 ルート
# ============================================================

@bp.route('/registration_docs')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def registration_docs():
    """登記書類作成画面"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    return render_template('teikan/registration_docs.html', data=data)


@bp.route('/registration_docs/preview/application')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def preview_registration_application():
    """設立登記申請書プレビュー"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    return render_template('teikan/registration_application_preview.html', data=data)


@bp.route('/registration_docs/download/application')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def download_registration_application():
    """設立登記申請書PDFダウンロード"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    try:
        pdf_bytes = generate_registration_application_pdf(data)
        company_type = data.get('company_type', '合同会社')
        company_name = data.get('company_name', '会社')
        filename = f"{company_type}{company_name}_設立登記申請書.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'PDF生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.registration_docs'))


@bp.route('/registration_docs/download/payment_certificate')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def download_payment_certificate():
    """払込証明書PDFダウンロード"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    try:
        pdf_bytes = generate_payment_certificate_pdf(data)
        company_type = data.get('company_type', '合同会社')
        company_name = data.get('company_name', '会社')
        filename = f"{company_type}{company_name}_払込証明書.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'PDF生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.registration_docs'))


@bp.route('/registration_docs/preview/payment_certificate')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def preview_payment_certificate():
    """払込証明書プレビュー"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    return render_template('teikan/payment_certificate_preview.html', data=data)


@bp.route('/registration_docs/download/capital_certificate')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def download_capital_certificate():
    """資本金の額の決定を証する書面PDFダウンロード"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    try:
        pdf_bytes = generate_capital_certificate_pdf(data)
        company_type = data.get('company_type', '合同会社')
        company_name = data.get('company_name', '会社')
        filename = f"{company_type}{company_name}_資本金の額の決定を証する書面.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'PDF生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.registration_docs'))


@bp.route('/registration_docs/download/office_location')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def download_office_location():
    """本店所在場所の決定を証する書面PDFダウンロード"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    try:
        pdf_bytes = generate_office_location_pdf(data)
        company_type = data.get('company_type', '合同会社')
        company_name = data.get('company_name', '会社')
        filename = f"{company_type}{company_name}_本店所在場所の決定を証する書面.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'PDF生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.registration_docs'))


@bp.route('/registration_docs/download/acceptance_letter')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def download_acceptance_letter():
    """就任承諾書PDFダウンロード"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    try:
        pdf_bytes = generate_acceptance_letter_pdf(data)
        company_type = data.get('company_type', '合同会社')
        company_name = data.get('company_name', '会社')
        filename = f"{company_type}{company_name}_就任承諾書.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'PDF生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.registration_docs'))


@bp.route('/registration_docs/download/founder_resolution')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def download_founder_resolution():
    """発起人の決定書 / 設立時社員の決議書PDFダウンロード"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    try:
        pdf_bytes = generate_founder_resolution_pdf(data)
        company_type = data.get('company_type', '株式会社')
        company_name = data.get('company_name', '会社')
        if company_type == '一般社団法人':
            doc_name = '設立時社員の決議書'
        else:
            doc_name = '発起人の決定書'
        filename = f"{company_type}{company_name}_{doc_name}.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'PDF生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.registration_docs'))


@bp.route('/registration_docs/download/seal_registration')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def download_seal_registration():
    """印鑑届出書PDFダウンロード"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    try:
        pdf_bytes = generate_seal_registration_pdf(data)
        company_type = data.get('company_type', '合同会社')
        company_name = data.get('company_name', '会社')
        filename = f"{company_type}{company_name}_印鑑届出書.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'PDF生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.registration_docs'))



@bp.route('/registration_docs/download/inkan_card')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def download_inkan_card():
    """印鑑カード交付申請書PDFダウンロード"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    try:
        pdf_bytes = generate_inkan_card_pdf(data)
        company_type = data.get('company_type', '合同会社')
        company_name = data.get('company_name', '会社')
        filename = f"{company_type}{company_name}_印鑑カード交付申請書.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'PDF生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.registration_docs'))


@bp.route('/registration_docs/download/stamp_duty_sheet')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def download_stamp_duty_sheet():
    """登録免許税納付用台紙をダウンロード"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    try:
        pdf_bytes = generate_stamp_duty_sheet_pdf(data)
        company_type = data.get('company_type', '合同会社')
        company_name = data.get('company_name', '会社')
        full_name = f"{company_type}{company_name}"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=f"{full_name}_登録免許税納付用台紙.pdf")
    except Exception as e:
        flash(f'PDF生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.registration_docs'))


@bp.route('/registration_docs/download/registration_items')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def download_registration_items():
    """別紙（登記すべき事項）をダウンロード"""
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    try:
        pdf_bytes = generate_registration_items_pdf(data)
        company_type = data.get('company_type', '合同会社')
        company_name = data.get('company_name', '会社')
        full_name = f"{company_type}{company_name}"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=f"{full_name}_別紙（登記すべき事項）.pdf")
    except Exception as e:
        flash(f'PDF生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.registration_docs'))


@bp.route('/registration_docs/download/all')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def download_all_docs():
    """全登記書類をZIPでダウンロード"""
    import zipfile
    data = get_session_data()
    if not data.get('company_name'):
        flash('最初から入力してください', 'warning')
        return redirect(url_for('teikan.step1'))
    try:
        company_type = data.get('company_type', '合同会社')
        company_name = data.get('company_name', '会社')
        full_name = f"{company_type}{company_name}"

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 定款
            teikan_pdf = generate_teikan_pdf(data)
            zf.writestr(f"{full_name}_定款.pdf", teikan_pdf)

            # 設立登記申請書
            app_pdf = generate_registration_application_pdf(data)
            zf.writestr(f"{full_name}_設立登記申請書.pdf", app_pdf)
            # 登録免許税納付用台紙
            stamp_duty_pdf = generate_stamp_duty_sheet_pdf(data)
            zf.writestr(f"{full_name}_登録免許税納付用台紙.pdf", stamp_duty_pdf)
            # 別紙（登記すべき事項）
            reg_items_pdf = generate_registration_items_pdf(data)
            zf.writestr(f"{full_name}_別紙（登記すべき事項）.pdf", reg_items_pdf)

            # 印鑑届出書
            seal_pdf = generate_seal_registration_pdf(data)
            zf.writestr(f"{full_name}_印鑑届出書.pdf", seal_pdf)

            # 印鑑カード交付申請書
            inkan_card_pdf = generate_inkan_card_pdf(data)
            zf.writestr(f"{full_name}_印鑑カード交付申請書.pdf", inkan_card_pdf)

            if company_type != '一般社団法人':
                # 払込証明書
                payment_pdf = generate_payment_certificate_pdf(data)
                zf.writestr(f"{full_name}_払込証明書.pdf", payment_pdf)

                # 資本金の額の決定を証する書面
                capital_pdf = generate_capital_certificate_pdf(data)
                zf.writestr(f"{full_name}_資本金の額の決定を証する書面.pdf", capital_pdf)

            if company_type == '合同会社':
                # 本店所在場所の決定を証する書面
                office_pdf = generate_office_location_pdf(data)
                zf.writestr(f"{full_name}_本店所在場所の決定を証する書面.pdf", office_pdf)

                # 就任承諾書
                accept_pdf = generate_acceptance_letter_pdf(data)
                zf.writestr(f"{full_name}_就任承諾書.pdf", accept_pdf)

            elif company_type in ['株式会社', '一般社団法人']:
                # 発起人の決定書 / 設立時社員の決議書
                resolution_pdf = generate_founder_resolution_pdf(data)
                doc_name = '設立時社員の決議書' if company_type == '一般社団法人' else '発起人の決定書'
                zf.writestr(f"{full_name}_{doc_name}.pdf", resolution_pdf)

                # 就任承諾書
                accept_pdf = generate_acceptance_letter_pdf(data)
                zf.writestr(f"{full_name}_就任承諾書.pdf", accept_pdf)

            # 綴じ方ガイドPDF
            import os
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))
            from generate_guides import generate_kk_guide, generate_gk_guide, generate_ippan_guide
            if company_type == '株式会社':
                guide_pdf = generate_kk_guide().read()
                guide_name = '綴じ方ガイド（株式会社版）.pdf'
            elif company_type == '合同会社':
                guide_pdf = generate_gk_guide().read()
                guide_name = '綴じ方ガイド（合同会社版）.pdf'
            else:
                guide_pdf = generate_ippan_guide().read()
                guide_name = '綴じ方ガイド（一般社団法人版）.pdf'
            zf.writestr(guide_name, guide_pdf)

        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip',
                         as_attachment=True,
                         download_name=f"{full_name}_登記書類一式.zip")
    except Exception as e:
        flash(f'ZIP生成エラー: {str(e)}', 'error')
        return redirect(url_for('teikan.registration_docs'))


# ============================================================
# PDF プレビュー API（PDF生成→画像変換→base64返却）
# ============================================================

def _pdf_to_preview_images(pdf_bytes, dpi=120):
    """PDFバイト列を画像のbase64リストに変換する"""
    import base64
    from io import BytesIO
    try:
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(pdf_bytes, dpi=dpi)
        result = []
        for img in images:
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            result.append(f'data:image/jpeg;base64,{b64}')
        return result
    except Exception as e:
        return {'error': str(e)}


@bp.route('/registration_docs/preview_pdf/<doc_type>')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def preview_pdf(doc_type):
    """書類のPDFを生成して画像プレビューをJSONで返す"""
    from flask import jsonify
    data = get_session_data()
    if not data.get('company_name'):
        return jsonify({'error': '最初から入力してください'}), 400
    try:
        if doc_type == 'teikan':
            pdf_bytes = generate_teikan_pdf(data)
        elif doc_type == 'application':
            pdf_bytes = generate_registration_application_pdf(data)
        elif doc_type == 'payment_certificate':
            pdf_bytes = generate_payment_certificate_pdf(data)
        elif doc_type == 'capital_certificate':
            pdf_bytes = generate_capital_certificate_pdf(data)
        elif doc_type == 'office_location':
            pdf_bytes = generate_office_location_pdf(data)
        elif doc_type == 'acceptance_letter':
            pdf_bytes = generate_acceptance_letter_pdf(data)
        elif doc_type == 'founder_resolution':
            pdf_bytes = generate_founder_resolution_pdf(data)
        elif doc_type == 'seal_registration':
            pdf_bytes = generate_seal_registration_pdf(data)
        elif doc_type == 'inkan_card':
            pdf_bytes = generate_inkan_card_pdf(data)
        elif doc_type == 'stamp_duty_sheet':
            pdf_bytes = generate_stamp_duty_sheet_pdf(data)
        elif doc_type == 'registration_items':
            pdf_bytes = generate_registration_items_pdf(data)
        else:
            return jsonify({'error': '不明な書類種別です'}), 400
        if isinstance(pdf_bytes, bytes):
            pass
        else:
            pdf_bytes = bytes(pdf_bytes)
        images = _pdf_to_preview_images(pdf_bytes)
        if isinstance(images, dict) and 'error' in images:
            return jsonify(images), 500
        return jsonify({'images': images, 'page_count': len(images)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# 登記書類 PDF生成関数
# ============================================================

def _setup_pdf_canvas():
    """ReportLab PDF生成の共通セットアップ"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    # フォントパスの候補（リポジトリ内 → システム）
    font_candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts', 'ipag.ttf'),
        '/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf',
        '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf',
    ]
    jp_font_path = None
    for candidate in font_candidates:
        if os.path.exists(candidate):
            jp_font_path = candidate
            break

    if jp_font_path:
        try:
            if 'JapaneseGothic' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('JapaneseGothic', jp_font_path))
            font_name = 'JapaneseGothic'
        except Exception:
            font_name = 'Helvetica'
    else:
        font_name = 'Helvetica'

    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin_left = 25 * mm
    margin_right = 25 * mm
    margin_top = 25 * mm
    margin_bottom = 20 * mm
    content_width = width - margin_left - margin_right

    return c, buffer, width, height, margin_left, margin_right, margin_top, margin_bottom, content_width, font_name, mm


def _get_full_company_name(data):
    """法人種別位置を考慮した完全な会社名を返す"""
    company_type = data.get('company_type', '合同会社')
    company_name = data.get('company_name', '')
    position = data.get('company_type_position', 'before')
    if position == 'before':
        return f"{company_type}{company_name}"
    else:
        return f"{company_name}{company_type}"


def generate_registration_application_pdf(data):  # noqa: C901
    """設立登記申請書PDFを生成する（法務局公式雛形準拠）"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import io
    import os

    buffer = io.BytesIO()
    width, height = A4

    # フォント設定
    fn = 'IPAGothic'
    font_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'fonts', 'ipag.ttf'),
        '/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf',
        '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf',
    ]
    for fp in font_paths:
        fp = os.path.normpath(fp)
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont(fn, fp))
            except Exception:
                pass
            break

    company_type = data.get('company_type', '合同会社')
    has_board = data.get('has_board_of_directors', 'false') == 'true'
    full_name = _get_full_company_name(data)
    company_name_kana = data.get('company_name_kana', '')
    address = data.get('address', '') + ((' ' + data.get('address_detail', '')) if data.get('address_detail') else '')
    capital = data.get('capital', '0')
    phone = data.get('phone', '')
    try:
        capital_int = int(str(capital).replace(',', '').replace('円', ''))
    except Exception:
        capital_int = 0
    members = data.get('members', [])
    rep_members = [m for m in members if m.get('is_representative')]
    if not rep_members and members:
        rep_members = [members[0]]
    rep = rep_members[0] if rep_members else {}
    established_date = data.get('established_date', '') or ''

    # 登録免許税計算
    if company_type == '株式会社':
        tax = max(150000, int(capital_int * 7 / 1000))
    elif company_type == '一般社団法人':
        tax = 60000
    else:
        tax = max(60000, int(capital_int * 7 / 1000))

    # ページ設定
    outer_left = 15 * mm
    outer_right = 15 * mm
    outer_top = 10 * mm

    def new_page(c):
        c.showPage()

    # ============================================================
    # ページ共通：テキスト描画ヘルパー
    # ============================================================
    def draw_text(c, x, y, text, size=10, bold=False):
        c.setFont(fn, size)
        c.drawString(x, y, text)

    def draw_text_center(c, y, text, size=10):
        c.setFont(fn, size)
        tw = c.stringWidth(text, fn, size)
        c.drawString((width - tw) / 2, y, text)

    def draw_multiline(c, x, y, text, size=9.5, max_width=None, line_height=14):
        """\u9577いテキストを折り返して描画する"""
        if max_width is None:
            max_width = width - outer_left - outer_right
        c.setFont(fn, size)
        line = ''
        lines = []
        for ch in text:
            test = line + ch
            if c.stringWidth(test, fn, size) <= max_width:
                line = test
            else:
                if line:
                    lines.append(line)
                line = ch
        if line:
            lines.append(line)
        cur_y = y
        for ln in lines:
            c.drawString(x, cur_y, ln)
            cur_y -= line_height
        return cur_y

    # ============================================================
    # ページ 1: 受付番号票貼付欄 + 申請書本体
    # ============================================================
    c = pdfcanvas.Canvas(buffer, pagesize=A4)

    # --- 受付番号票貼付欄（枚枠） ---
    ticket_left = outer_left
    ticket_right = width - outer_right
    ticket_top = height - outer_top
    ticket_bottom = ticket_top - 28 * mm
    c.setLineWidth(1)
    c.rect(ticket_left, ticket_bottom, ticket_right - ticket_left, ticket_top - ticket_bottom)
    draw_text_center(c, ticket_bottom + (ticket_top - ticket_bottom) / 2 - 3 * mm, '受付番号票貼付欄', size=11)

    # --- タイトル ---
    if company_type == '合同会社':
        title = '合同会社設立登記申請書'
    elif company_type == '株式会社':
        title = '株式会社設立登記申請書'
    else:
        title = '一般社団法人設立登記申請書'

    title_y = ticket_bottom - 14 * mm
    draw_text_center(c, title_y, title, size=16)

    cur_y = title_y - 12 * mm
    left_indent = outer_left + 10 * mm
    label_x = outer_left + 5 * mm

    def draw_item(c, label, value, kana=None):
        """1項目を描画する"""
        nonlocal cur_y
        if kana:
            draw_text(c, left_indent, cur_y, 'フリガナ', size=8)
            cur_y -= 10
            draw_text(c, left_indent, cur_y, kana, size=9.5)
            cur_y -= 12
        draw_text(c, label_x, cur_y, label, size=10.5)
        if value:
            draw_multiline(c, left_indent, cur_y, value, size=10.5,
                           max_width=width - left_indent - outer_right - 5 * mm)
        cur_y -= 16

    # 商号
    draw_item(c, '1．商　号', full_name, kana=company_name_kana if company_name_kana else None)
    cur_y -= 2

    # 本店
    draw_item(c, '1．本　店', address)
    cur_y -= 2

    # 登記の事由
    if established_date:
        jiyuu_text = f'令和{established_date}発起設立の手続終了'
    else:
        jiyuu_text = '令和　　年　　月　　日発起設立の手続終了'
    draw_text(c, label_x, cur_y, '1．登記の事由', size=10.5)
    draw_text(c, left_indent + 20 * mm, cur_y, jiyuu_text, size=10.5)
    cur_y -= 16
    cur_y -= 2

    # 登記すべき事項
    draw_text(c, label_x, cur_y, '1．登記すべき事項', size=10.5)
    cur_y -= 16
    cur_y -= 2

    # 課税標準金額
    draw_text(c, label_x, cur_y, '1．課税標準金額', size=10.5)
    draw_text(c, label_x + 28 * mm, cur_y, '金', size=10.5)
    draw_text(c, label_x + 33 * mm, cur_y, f'{capital_int:,}', size=10.5)
    draw_text(c, label_x + 33 * mm + c.stringWidth(f'{capital_int:,}', fn, 10.5) + 2 * mm, cur_y, '円', size=10.5)
    cur_y -= 16
    cur_y -= 2

    # 登録免許税
    draw_text(c, label_x, cur_y, '1．登録免許税', size=10.5)
    draw_text(c, label_x + 28 * mm, cur_y, '金', size=10.5)
    draw_text(c, label_x + 33 * mm, cur_y, f'{tax:,}', size=10.5)
    draw_text(c, label_x + 33 * mm + c.stringWidth(f'{tax:,}', fn, 10.5) + 2 * mm, cur_y, '円', size=10.5)
    cur_y -= 16
    cur_y -= 4

    # 添付書類
    draw_text(c, label_x - 5 * mm, cur_y, '1．添付書類', size=10.5)
    cur_y -= 14

    doc_indent = outer_left + 15 * mm
    right_num_x = width - outer_right - 18 * mm

    def draw_doc_line(c, doc_name, count_str):
        nonlocal cur_y
        c.setFont(fn, 9.5)
        c.drawString(doc_indent, cur_y, doc_name)
        c.drawRightString(right_num_x + 12 * mm, cur_y, count_str)
        cur_y -= 13

    # 添付書類リスト（会社種別・取締役会設置の有無により分岐）
    if company_type == '株式会社':
        if has_board:
            # 取締役会設置版
            draw_doc_line(c, '定款', '1通')
            draw_doc_line(c, '発起人の同意書', '通')
            draw_doc_line(c, '設立時代表取締役を選定したことを証する書面', '1通')
            draw_doc_line(c, '設立時取締役、設立時代表取締役及び設立時監査役の就任承諾書', '通')
            draw_doc_line(c, '印鑑証明書', '通')
            draw_doc_line(c, '本人確認証明書', '通')
            draw_doc_line(c, '設立時取締役及び設立時監査役の調査報告書及びその附属書類', '1通')
            draw_doc_line(c, '払込みを証する書面', '1通')
            draw_doc_line(c, '資本金の額の計上に関する設立時代表取締役の証明書', '1通')
            draw_doc_line(c, '委任状', '1通')
        else:
            # 取締役会非設置版
            draw_doc_line(c, '定款', '1通')
            draw_doc_line(c, '発起人の同意書', '通')
            draw_doc_line(c, '設立時代表取締役を選定したことを証する書面', '1通')
            draw_doc_line(c, '設立時取締役（及び設立時監査役）の就任承諾書', '通')
            draw_doc_line(c, '印鑑証明書', '通')
            draw_doc_line(c, '本人確認証明書', '通')
            draw_doc_line(c, '設立時取締役（及び設立時監査役）の調査報告書及びその附属書類', '1通')
            draw_doc_line(c, '払込みを証する書面', '1通')
            draw_doc_line(c, '資本金の額の計上に関する設立時代表取締役の証明書', '1通')
            draw_doc_line(c, '委任状', '1通')
    elif company_type == '合同会社':
        draw_doc_line(c, '定款', '1通')
        draw_doc_line(c, '発起人の同意書', '通')
        draw_doc_line(c, '代表社員・業務執行社員の就任承諾書', '通')
        draw_doc_line(c, '印鑑証明書', '通')
        draw_doc_line(c, '本人確認証明書', '通')
        draw_doc_line(c, '払込みを証する書面', '1通')
        draw_doc_line(c, '資本金の額の計上に関する証明書', '1通')
        draw_doc_line(c, '委任状', '1通')
    else:  # 一般社団法人
        draw_doc_line(c, '定款', '1通')
        draw_doc_line(c, '設立時社員の決議書', '1通')
        draw_doc_line(c, '設立時理事・代表理事の就任承諾書', '通')
        draw_doc_line(c, '印鑑証明書', '通')
        draw_doc_line(c, '本人確認証明書', '通')
        draw_doc_line(c, '委任状', '1通')

    cur_y -= 6

    # 「上記のとおり、登記の申請をします。」
    draw_text(c, outer_left, cur_y,
              '上記のとおり、登記の申請をします。', size=10.5)
    cur_y -= 16
    cur_y -= 4

    # 申請日
    if established_date:
        date_text = f'令和{established_date}'
    else:
        date_text = '令和　　年　　月　　日'
    draw_text(c, outer_left + 15 * mm, cur_y, date_text, size=10.5)
    cur_y -= 16
    cur_y -= 4

    # 申請人・代表取締役（取締役会設置版は1ページ目に記載）
    if company_type != '株式会社' or has_board:
        draw_text(c, outer_left + 15 * mm, cur_y, '申請人', size=10.5)
        cur_y -= 16
        cur_y -= 4
        draw_text(c, outer_left + 15 * mm, cur_y, '代表取締役　' + rep.get('name', ''), size=10.5)
        # 印鑑押印欄（点線丸）
        seal_cx = width - outer_right - 20 * mm
        seal_cy = cur_y + 5 * mm
        seal_r = 12 * mm
        c.setDash(3, 3)
        c.setLineWidth(0.8)
        c.setStrokeColorRGB(0.8, 0, 0)
        c.circle(seal_cx, seal_cy, seal_r, stroke=1, fill=0)
        c.setDash()
        c.setStrokeColorRGB(0, 0, 0)
        cur_y -= 16

    # 連絡先電話番号・法務局宛・封筒印鑑欄（取締役会設置版または株式会社以外のみ1ページ目に表示）
    if company_type != '株式会社' or has_board:
        cur_y -= 4
        draw_text(c, outer_left + 15 * mm, cur_y, '連絡先の電話番号　' + phone, size=10)
        cur_y -= 14

        draw_text(c, outer_left + 15 * mm, cur_y, '法務局　　　支　局　　御中', size=10.5)
        cur_y -= 12
        draw_text(c, outer_left + 15 * mm + 20 * mm, cur_y, '出張所', size=10.5)

        # 封筒印鑑押印欄（点線丸）
        seal2_cx = outer_left + 15 * mm
        seal2_cy = cur_y - 15 * mm
        seal2_r = 12 * mm
        c.setDash(3, 3)
        c.setLineWidth(0.8)
        c.setStrokeColorRGB(0.8, 0, 0)
        c.circle(seal2_cx, seal2_cy, seal2_r, stroke=1, fill=0)
        c.setDash()
        c.setStrokeColorRGB(0, 0, 0)

    # ============================================================
    # ページ 2: 取締役会非設置版の申請人欄（非設置版のみ）
    # ============================================================
    if company_type == '株式会社' and not has_board:
        c.showPage()
        cur_y2 = height - outer_top - 10 * mm

        draw_text(c, outer_left + 15 * mm, cur_y2, '申請人', size=10.5)
        cur_y2 -= 16
        cur_y2 -= 4
        draw_text(c, outer_left + 15 * mm, cur_y2, '代表取締役　' + rep.get('name', ''), size=10.5)
        # 印鑑押印欄（点線丸）
        seal_cx2 = width - outer_right - 20 * mm
        seal_cy2 = cur_y2 + 5 * mm
        seal_r2 = 12 * mm
        c.setDash(3, 3)
        c.setLineWidth(0.8)
        c.setStrokeColorRGB(0.8, 0, 0)
        c.circle(seal_cx2, seal_cy2, seal_r2, stroke=1, fill=0)
        c.setDash()
        c.setStrokeColorRGB(0, 0, 0)
        cur_y2 -= 16
        cur_y2 -= 4

        draw_text(c, outer_left + 15 * mm, cur_y2, '連絡先の電話番号　' + phone, size=10)
        cur_y2 -= 14

        draw_text(c, outer_left + 15 * mm, cur_y2, '法務局　　　支　局　　御中', size=10.5)
        cur_y2 -= 12
        draw_text(c, outer_left + 15 * mm + 20 * mm, cur_y2, '出張所', size=10.5)

        seal3_cx = outer_left + 15 * mm
        seal3_cy = cur_y2 - 15 * mm
        seal3_r = 12 * mm
        c.setDash(3, 3)
        c.setLineWidth(0.8)
        c.setStrokeColorRGB(0.8, 0, 0)
        c.circle(seal3_cx, seal3_cy, seal3_r, stroke=1, fill=0)
        c.setDash()
        c.setStrokeColorRGB(0, 0, 0)

    # ============================================================
    # 最終ページ: 収入印紙貼付台紙
    # ============================================================
    c.showPage()
    cur_y3 = height - outer_top - 5 * mm
    draw_text(c, outer_left, cur_y3, '収入印紙貼付台紙', size=10)
    cur_y3 -= 10 * mm

    # 印鑑押印欄（点線丸）
    seal4_cx = outer_left + 15 * mm
    seal4_cy = cur_y3 - 20 * mm
    seal4_r = 12 * mm
    c.setDash(3, 3)
    c.setLineWidth(0.8)
    c.setStrokeColorRGB(0.8, 0, 0)
    c.circle(seal4_cx, seal4_cy, seal4_r, stroke=1, fill=0)
    c.setDash()
    c.setStrokeColorRGB(0, 0, 0)

    # 収入印紙貼付欄（ギザギザ枚枠）
    stamp_left = width - outer_right - 30 * mm
    stamp_bottom = cur_y3 - 35 * mm
    stamp_w = 25 * mm
    stamp_h = 30 * mm
    # ギザギザ枚枠を描画
    c.setLineWidth(0.5)
    seg = 2 * mm
    sx, sy = stamp_left, stamp_bottom
    sw, sh = stamp_w, stamp_h
    # 上辺
    x = sx
    while x < sx + sw:
        c.line(x, sy + sh, min(x + seg, sx + sw), sy + sh)
        x += seg * 2
    # 下辺
    x = sx
    while x < sx + sw:
        c.line(x, sy, min(x + seg, sx + sw), sy)
        x += seg * 2
    # 左辺
    y2 = sy
    while y2 < sy + sh:
        c.line(sx, y2, sx, min(y2 + seg, sy + sh))
        y2 += seg * 2
    # 右辺
    y2 = sy
    while y2 < sy + sh:
        c.line(sx + sw, y2, sx + sw, min(y2 + seg, sy + sh))
        y2 += seg * 2
    # 収入印紙テキスト
    draw_text(c, stamp_left + 3 * mm, stamp_bottom + stamp_h / 2 + 2 * mm, '収　入', size=9)
    draw_text(c, stamp_left + 3 * mm, stamp_bottom + stamp_h / 2 - 8 * mm, '印　紙', size=9)

    c.save()
    buffer.seek(0)
    return buffer.read()


def generate_payment_certificate_pdf(data):
    """払込みがあったことを証する書面（払込証明書）PDFを生成する"""
    c, buffer, width, height, ml, mr, mt, mb, cw, fn, mm = _setup_pdf_canvas()

    company_type = data.get('company_type', '合同会社')
    full_name = _get_full_company_name(data)
    capital = data.get('capital', '0')
    try:
        capital_int = int(str(capital).replace(',', '').replace('円', ''))
        capital_str = f'金{capital_int:,}円'
    except Exception:
        capital_str = f'金{capital}円'
    members = data.get('members', [])
    rep_members = [m for m in members if m.get('is_representative')]
    if not rep_members and members:
        rep_members = [members[0]]
    established_date = data.get('established_date', '') or '令和　　年　　月　　日'

    y = height - mt

    # タイトル
    title = '払込みがあったことを証する書面'
    c.setFont(fn, 16)
    tw = c.stringWidth(title, fn, 16)
    c.drawString((width - tw) / 2, y, title)
    y -= 50

    # 本文
    c.setFont(fn, 10.5)
    lines = [
        f'　　当{("会社" if company_type != "一般社団法人" else "法人")}の設立に際して、',
        f'　　次のとおり出資の払込みがあったことを証明します。',
        '',
        f'　　払込みを受けた金額　　{capital_str}',
        '',
        f'　　　　　　　　　　　　　　　　{established_date}',
        '',
    ]
    for line in lines:
        c.drawString(ml, y, line)
        y -= 20

    # 会社名
    c.setFont(fn, 10.5)
    c.drawString(ml + 20 * mm, y, full_name)
    y -= 25

    # 代表者
    for m in rep_members:
        if company_type == '合同会社':
            role = '代表社員'
        elif company_type == '株式会社':
            role = '代表取締役'
        else:
            role = '代表理事'
        c.drawString(ml + 20 * mm, y, f'{role}　{m.get("name", "")}　　　　　　　　　印')
        y -= 30

    y -= 20
    # 払込明細
    c.setFont(fn, 10.5)
    c.drawString(ml, y, '【払込明細】')
    y -= 20
    c.setFont(fn, 9.5)
    for m in members:
        contrib = m.get('contribution', '0')
        try:
            contrib_str = f'金{int(str(contrib).replace(",","").replace("円","")):,}円'
        except Exception:
            contrib_str = f'金{contrib}円'
        c.drawString(ml + 5 * mm, y, f'{m.get("name", "")}　　{contrib_str}')
        y -= 18
    y -= 10
    c.setFont(fn, 9.5)
    c.drawString(ml, y, f'合計　{capital_str}')

    c.save()
    buffer.seek(0)
    return buffer.read()


def generate_capital_certificate_pdf(data):
    """資本金の額の決定を証する書面PDFを生成する"""
    c, buffer, width, height, ml, mr, mt, mb, cw, fn, mm = _setup_pdf_canvas()

    company_type = data.get('company_type', '合同会社')
    full_name = _get_full_company_name(data)
    capital = data.get('capital', '0')
    try:
        capital_int = int(str(capital).replace(',', '').replace('円', ''))
        capital_str = f'金{capital_int:,}円'
    except Exception:
        capital_str = f'金{capital}円'
    members = data.get('members', [])
    rep_members = [m for m in members if m.get('is_representative')]
    if not rep_members and members:
        rep_members = [members[0]]
    established_date = data.get('established_date', '') or '令和　　年　　月　　日'

    y = height - mt

    title = '資本金の額の決定を証する書面'
    c.setFont(fn, 16)
    tw = c.stringWidth(title, fn, 16)
    c.drawString((width - tw) / 2, y, title)
    y -= 50

    c.setFont(fn, 10.5)
    lines = [
        f'　　設立に際して出資される財産の価額　　{capital_str}',
        '',
        f'　　上記の額から資本金として計上した額　　{capital_str}',
        '',
        '　　上記のとおり資本金の額が会社法及び会社計算規則の規定に',
        '　　従って計上されたことを証明します。',
        '',
        f'　　　　　　　　　　　　　　　　{established_date}',
        '',
    ]
    for line in lines:
        c.drawString(ml, y, line)
        y -= 20

    c.drawString(ml + 20 * mm, y, full_name)
    y -= 25

    for m in rep_members:
        if company_type == '合同会社':
            role = '代表社員'
        elif company_type == '株式会社':
            role = '代表取締役'
        else:
            role = '代表理事'
        c.drawString(ml + 20 * mm, y, f'{role}　{m.get("name", "")}　　　　　　　　　印')
        y -= 30

    c.save()
    buffer.seek(0)
    return buffer.read()


def generate_office_location_pdf(data):
    """本店所在場所の決定を証する書面PDFを生成する（合同会社用）"""
    c, buffer, width, height, ml, mr, mt, mb, cw, fn, mm = _setup_pdf_canvas()

    full_name = _get_full_company_name(data)
    address = data.get('address', '') + ((' ' + data.get('address_detail', '')) if data.get('address_detail') else '')
    members = data.get('members', [])
    established_date = data.get('established_date', '') or '令和　　年　　月　　日'

    y = height - mt

    title = '本店所在場所の決定を証する書面'
    c.setFont(fn, 16)
    tw = c.stringWidth(title, fn, 16)
    c.drawString((width - tw) / 2, y, title)
    y -= 50

    c.setFont(fn, 10.5)
    lines = [
        f'　　{full_name}の設立に際し、',
        '　　社員全員の同意により本店の所在場所を次のとおり決定しました。',
        '',
        f'　　本店所在場所　　{address}',
        '',
        f'　　　　　　　　　　　　　　　　{established_date}',
        '',
        f'　　{full_name}',
        '',
    ]
    for line in lines:
        c.drawString(ml, y, line)
        y -= 20

    c.setFont(fn, 10.5)
    for m in members:
        c.drawString(ml + 5 * mm, y, f'社員　{m.get("name", "")}　　　　　　　　　　　　　印')
        y -= 28

    c.save()
    buffer.seek(0)
    return buffer.read()


def generate_acceptance_letter_pdf(data):
    """就任承諾書PDFを生成する（全社員分）"""
    c, buffer, width, height, ml, mr, mt, mb, cw, fn, mm = _setup_pdf_canvas()

    company_type = data.get('company_type', '合同会社')
    full_name = _get_full_company_name(data)
    members = data.get('members', [])
    established_date = data.get('established_date', '') or '令和　　年　　月　　日'

    if company_type == '合同会社':
        role = '代表社員兼業務執行社員'
    elif company_type == '株式会社':
        role = '設立時取締役'
    else:
        role = '設立時理事'

    first_page = True
    for m in members:
        if not first_page:
            c.showPage()
        first_page = False

        y = height - mt

        title = '就任承諾書'
        c.setFont(fn, 18)
        tw = c.stringWidth(title, fn, 18)
        c.drawString((width - tw) / 2, y, title)
        y -= 50

        c.setFont(fn, 10.5)
        lines = [
            f'　　私は、{full_name}の{role}に就任することを',
            '　　承諾します。',
            '',
            f'　　　　　　　　　　　　　　　　{established_date}',
            '',
        ]
        for line in lines:
            c.drawString(ml, y, line)
            y -= 20

        c.drawString(ml + 10 * mm, y, f'住所　{m.get("address", "")}')
        y -= 25
        c.drawString(ml + 10 * mm, y, f'氏名　{m.get("name", "")}　　　　　　　　　　　　　印')

        # 代表者の場合は代表就任承諾書も追加
        if m.get('is_representative'):
            c.showPage()
            y = height - mt

            if company_type == '合同会社':
                rep_role = '代表社員'
            elif company_type == '株式会社':
                rep_role = '設立時代表取締役'
            else:
                rep_role = '設立時代表理事'

            c.setFont(fn, 18)
            tw = c.stringWidth(title, fn, 18)
            c.drawString((width - tw) / 2, y, title)
            y -= 50

            c.setFont(fn, 10.5)
            lines = [
                f'　　私は、{full_name}の{rep_role}に就任することを',
                '　　承諾します。',
                '',
                f'　　　　　　　　　　　　　　　　{established_date}',
                '',
            ]
            for line in lines:
                c.drawString(ml, y, line)
                y -= 20

            c.drawString(ml + 10 * mm, y, f'住所　{m.get("address", "")}')
            y -= 25
            c.drawString(ml + 10 * mm, y, f'氏名　{m.get("name", "")}　　　　　　　　　　　　　印')

    c.save()
    buffer.seek(0)
    return buffer.read()


def generate_founder_resolution_pdf(data):
    """発起人の決定書（株式会社）/ 設立時社員の決議書（一般社団法人）PDFを生成する"""
    c, buffer, width, height, ml, mr, mt, mb, cw, fn, mm = _setup_pdf_canvas()

    company_type = data.get('company_type', '株式会社')
    full_name = _get_full_company_name(data)
    address = data.get('address', '') + ((' ' + data.get('address_detail', '')) if data.get('address_detail') else '')
    members = data.get('members', [])
    rep_members = [m for m in members if m.get('is_representative')]
    if not rep_members and members:
        rep_members = [members[0]]
    established_date = data.get('established_date', '') or '令和　　年　　月　　日'

    y = height - mt

    if company_type == '一般社団法人':
        title = '設立時社員の決議書'
        signer_role = '設立時社員'
        content_lines = [
            f'　　{full_name}の設立に際し、設立時社員全員の',
            '　　同意により次のとおり決議しました。',
            '',
            '　　記',
            '',
            f'　　１．本店所在場所を次のとおり定める。',
            f'　　　　{address}',
            '',
        ]
        for i, m in enumerate(rep_members):
            content_lines.append(f'　　２．設立時理事として次の者を選任する。')
            content_lines.append(f'　　　　{m.get("name", "")}')
            content_lines.append('')
        for i, m in enumerate(rep_members):
            content_lines.append(f'　　３．設立時代表理事として次の者を選定する。')
            content_lines.append(f'　　　　{m.get("name", "")}')
            content_lines.append('')
    else:
        title = '発起人の決定書'
        signer_role = '発起人'
        content_lines = [
            f'　　{full_name}の設立に際し、発起人全員の',
            '　　同意により次のとおり決定しました。',
            '',
            '　　記',
            '',
            f'　　１．本店所在場所を次のとおり定める。',
            f'　　　　{address}',
            '',
        ]
        for i, m in enumerate(rep_members):
            content_lines.append(f'　　２．設立時取締役として次の者を選任する。')
            content_lines.append(f'　　　　{m.get("name", "")}')
            content_lines.append('')
        for i, m in enumerate(rep_members):
            content_lines.append(f'　　３．設立時代表取締役として次の者を選定する。')
            content_lines.append(f'　　　　{m.get("name", "")}')
            content_lines.append('')

    c.setFont(fn, 16)
    tw = c.stringWidth(title, fn, 16)
    c.drawString((width - tw) / 2, y, title)
    y -= 40

    c.setFont(fn, 10.5)
    for line in content_lines:
        c.drawString(ml, y, line)
        y -= 18

    y -= 10
    c.drawString(ml, y, f'　　　　　　　　　　　　　　　　{established_date}')
    y -= 30
    c.drawString(ml + 20 * mm, y, full_name)
    y -= 25

    for m in members:
        c.drawString(ml + 20 * mm, y, f'{signer_role}　{m.get("name", "")}　　　　　　　　　印')
        y -= 28

    c.save()
    buffer.seek(0)
    return buffer.read()


def generate_seal_registration_pdf(data):  # noqa: C901
    """印鑑届出書PDFを生成する（PDFテンプレートオーバーレイ方式）"""
    import io
    import os
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import pypdf

    # フォント設定
    font_candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts', 'ipag.ttf'),
        '/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf',
        '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf',
    ]
    jp_font_path = None
    for candidate in font_candidates:
        if os.path.exists(candidate):
            jp_font_path = candidate
            break
    if jp_font_path:
        try:
            if 'JapaneseGothic' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('JapaneseGothic', jp_font_path))
            fn = 'JapaneseGothic'
        except Exception:
            fn = 'Helvetica'
    else:
        fn = 'Helvetica'

    # データ取得
    company_type = data.get('company_type', '合同会社')
    company_name = data.get('company_name', '')
    full_name = f"{company_type}{company_name}"
    address = data.get('address', '')
    members = data.get('members', [])
    rep_members = [m for m in members if m.get('is_representative')]
    rep = rep_members[0] if rep_members else {}

    if company_type == '合同会社':
        role = '代表社員'
    elif company_type == '株式会社':
        role = '代表取締役'
    else:
        role = '代表理事'

    # テンプレートPDFのパス
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'templates', 'teikan', 'inkan_todokede_template.pdf'
    )

    # オーバーレイPDFを作成
    overlay_buffer = io.BytesIO()
    c = rl_canvas.Canvas(overlay_buffer, pagesize=A4)
    width, height = A4  # 595.28 x 841.89 pt

    c.setFont(fn, 9)
    c.setFillColorRGB(0, 0, 0)

    # 商号・名称（ラベルy=719.6pt）
    c.drawString(330, 719.6, full_name)

    # 本店・主たる事務所（ラベルy=683.5pt）
    c.drawString(330, 683.5, address)

    # 資格（印鑑提出者）- 該当する資格を○で囲む
    # テンプレートの資格欄構造:
    # y=657.3: 「代表取締役・取締役・代表理事」(x=340.1)
    # y=639.3: 「理事 ・ (」(x=327.5) 〜 「)」(x=376.4)
    c.setLineWidth(1.0)
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    # 資格欄の構造（テンプレートの座標）:
    # y=657.3: 「代表取締役・取締役・代表理事」 (x=340.1から全体幅約170pt)
    # y=639.3: 「理事 ・ (」(x=327.5) 〜 「)」(x=376.4)、全体幅約540まで
    if company_type == '株式会社':
        # 「代表取締役」を○で囲む（x=340.1から始まる、幅約55pt）
        # 「代表取締役」: x=340.1, 文字幅約55pt
        c.ellipse(336, 653, 396, 668, stroke=1, fill=0)
    elif company_type == '一般社団法人' or company_type == '一般財団法人':
        # 「代表理事」を○で囲む（「代表理事」は行の右端部分）
        # 高解像度画像から計測・微調整: 「代」x≈460、「事」右端x≈520
        c.ellipse(460, 653, 520, 668, stroke=1, fill=0)
    else:
        # 合同会社など → 「理事 ・ (　)」の括弧内に役職名を書く（○不要）
        # テンプレート座標: 「（」x≈340pt、「）」x≈540pt、行中心y≈638pt
        # 括弧内中央に配置: (340+540)/2=440、4文字×7.5pt=30pt、開始x=425
        c.setFont(fn, 8)
        c.drawString(425, 638.0, role)

    # 氏名（印鑑提出者）（ラベルy=613pt）
    c.setFont(fn, 9)
    c.drawString(330, 613.0, rep.get('name', ''))

    # 住所（届出人）（ラベルy=458.6pt）- 郵便番号を除去してラベル右側に配置
    import re
    rep_address = rep.get('address', address)
    # 郵便番号（〒xxx-xxxx または xxx-xxxx 形式）を除去
    rep_address = re.sub(r'[〒]?\d{3}-\d{4}\s*', '', rep_address).strip()
    c.drawString(130, 458.6, rep_address)

    # 氏名（届出人）（ラベルy=413.6pt）- ラベル右側に配置
    c.drawString(130, 413.6, rep.get('name', ''))

    # チェックボックス: 「印鑑カードは引き継がない。」にレ点を入れる
    # テキスト「印鑑カードは引き継がない。」bbox: x0=82.56, y0=552.11, y1=563.06
    c.setFont(fn, 7)
    c.drawString(71.0, 554.5, '✓')

    # チェックボックス: 「印鑑提出者本人」にレ点を入れる
    # テキスト「印鑑提出者本人」bbox: x0=170.76, y0=483.35, y1=494.30
    c.setFont(fn, 8)
    c.drawString(159.0, 485.8, '✓')

    # フリガナ（届出人）（ラベルy=436.8pt）- ラベル右側に配置
    name_kana = rep.get('name_kana', '')
    if name_kana:
        c.setFont(fn, 8)
        c.drawString(130, 436.8, name_kana)
        c.setFont(fn, 9)

    # 生年月日（印鑑提出者）（y=581.6pt）
    # テンプレート: 「大・昭・平・西暦」(x=322〜400) 「年」(x=440〜455) 「月」(x=480〜495) 「日」(x=510〜520) 「生」(x=520〜530)
    birth_era = rep.get('birth_era', '')
    birth_year = rep.get('birth_year', '')
    birth_month = rep.get('birth_month', '')
    birth_day = rep.get('birth_day', '')
    if birth_era or birth_year:
        # 元号を○で囲む
        # 高解像度画像(600dpi)から計測した各元号の中心x座標
        # 「大・昭・平・西暦」はx=321.96から始まる
        # 各文字間隔: 大(325)・(中点)・昭(337)・(中点)・平(350)・(中点)・西暦(363-373)
        # 各元号の中心x座標（計算式: x=321.96 + i*8.82 + 4.41）
        era_positions = {
            '大正': (326.4, 584.0),   # 「大」の中心
            '昭和': (347.0, 584.0),   # 「昭」の中心（調整済み）
            '平成': (368.0, 584.0),   # 「平」の中心（微調整）
            '令和': (383.7, 584.0),   # 「令和」→テンプレートに「西暦」の位置に対応
            '西暦': (395.0, 584.0),   # 「西暦」の中心（調整済み）
        }
        if birth_era in era_positions:
            ex, ey = era_positions[birth_era]
            c.setLineWidth(0.8)
            # 元号文字の周りに楕円を描画
            w = 6 if birth_era != '西暦' else 11
            h = 6
            c.ellipse(ex - w, ey - h, ex + w, ey + h + 2, stroke=1, fill=0)
        # 年・月・日を入力（フォントサイズ9pt）
        c.setFont(fn, 9)
        # 高解像度画像(600dpi)から計測した正確なラベル位置:
        # 「年」左端x≈440pt、「月」左端x≈480pt、「日」左端x≈510pt
        # 数字1文字幅はフォントサイズの約0.6倍
        char_w = 5.4  # 9ptフォントの数字1文字幅
        # 年数: 「年」(x=440)の直前に右寄せ配置
        if birth_year:
            year_str = str(birth_year)
            x_year = 440.0 - len(year_str) * char_w
            c.drawString(x_year, 581.6, year_str)
        # 月数: 「月」(x=480)の直前に右寄せ配置
        if birth_month:
            month_str = str(birth_month)
            x_month = 480.0 - len(month_str) * char_w
            c.drawString(x_month, 581.6, month_str)
        # 日数: 「日」(x=510)の直前に右寄せ配置
        if birth_day:
            day_str = str(birth_day)
            x_day = 510.0 - len(day_str) * char_w
            c.drawString(x_day, 581.6, day_str)

    c.save()
    overlay_buffer.seek(0)

    # テンプレートPDFとオーバーレイを合成
    template_reader = pypdf.PdfReader(template_path)
    overlay_reader = pypdf.PdfReader(overlay_buffer)

    writer = pypdf.PdfWriter()
    template_page = template_reader.pages[0]
    overlay_page = overlay_reader.pages[0]

    template_page.merge_page(overlay_page)
    writer.add_page(template_page)

    output_buffer = io.BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)
    return output_buffer.read()


def generate_inkan_card_pdf(data):  # noqa: C901
    """印鑑カード交付申請書PDFを生成する（PDFテンプレートオーバーレイ方式）"""
    import os
    import re
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import pypdf

    # フォント設定
    font_candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts', 'ipag.ttf'),
        '/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf',
        '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf',
    ]
    jp_font_path = None
    for candidate in font_candidates:
        if os.path.exists(candidate):
            jp_font_path = candidate
            break
    if jp_font_path:
        try:
            if 'JapaneseGothic' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('JapaneseGothic', jp_font_path))
            fn = 'JapaneseGothic'
        except Exception:
            fn = 'Helvetica'
    else:
        fn = 'Helvetica'

    # データ取得
    company_type = data.get('company_type', '合同会社')
    full_name = _get_full_company_name(data)
    address = data.get('address', '') + ((' ' + data.get('address_detail', '')) if data.get('address_detail') else '')
    members = data.get('members', [])
    rep_members = [m for m in members if m.get('is_representative')]
    if not rep_members and members:
        rep_members = [members[0]]
    rep = rep_members[0] if rep_members else {}

    if company_type == '合同会社':
        role = '代表社員'
    elif company_type == '株式会社':
        role = '代表取締役'
    else:
        role = '代表理事'

    # テンプレートPDFのパス
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'templates', 'teikan', 'inkan_card_template.pdf'
    )

    # オーバーレイPDFを作成
    overlay_buffer = io.BytesIO()
    c = rl_canvas.Canvas(overlay_buffer, pagesize=A4)
    width, height = A4  # 595.28 x 841.89 pt
    c.setFont(fn, 9)
    c.setFillColorRGB(0, 0, 0)

    # 商号・名称（ラベルy=684.5pt）
    c.drawString(270, 684.5, full_name)

    # 本店・主たる事務所（ラベルy=641.2pt）
    c.drawString(270, 641.2, address)

    # 資格欄（印鑑提出者）
    # テンプレート座標:
    # y=611.9: 「代表取締役・取締役・代表社員・代表理事・理事・支配人」(x=264.7)
    # y=593.0: 「（」(x=268.6) 〜 「）」(x=268.6)
    # 各役職のx座標（300dpi画像から計測）:
    #   代表取締役: x≈265〜320 → 中心x≈292
    #   取締役: x≈325〜360 → 中心x≈342
    #   代表社員: x≈365〜410 → 中心x≈387
    #   代表理事: x≈415〜455 → 中心x≈435
    #   理事: x≈460〜480 → 中心x≈470
    c.setLineWidth(1.0)
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)

    if company_type == '株式会社':
        # 「代表取締役」を○で囲む (x=265〜320, y=611.9)
        c.ellipse(262, 607, 322, 620, stroke=1, fill=0)
    elif company_type == '一般社団法人' or company_type == '一般財団法人':
        # 「代表理事」を○で囲む (x=415〜455, y=611.9)
        c.ellipse(412, 607, 458, 620, stroke=1, fill=0)
    else:
        # 合同会社 → 「代表社員」を○で囲む (x=365〜410, y=611.9)
        c.ellipse(362, 607, 412, 620, stroke=1, fill=0)

    # 氏名（印鑑提出者）（ラベルy=561.6pt）
    c.setFont(fn, 9)
    c.drawString(270, 561.6, rep.get('name', ''))

    # 申請人欄 住所（ラベルy=402.3pt）
    rep_address = rep.get('address', address)
    rep_address = re.sub(r'[〒]?\d{3}-\d{4}\s*', '', rep_address).strip()
    c.drawString(130, 402.3, rep_address)

    # 申請人欄 フリガナ（ラベルy=380.9pt）
    name_kana = rep.get('name_kana', '')
    if name_kana:
        c.setFont(fn, 8)
        c.drawString(130, 380.9, name_kana)
        c.setFont(fn, 9)

    # 申請人欄 氏名（ラベルy=362.5pt）
    c.drawString(130, 362.5, rep.get('name', ''))

    # 生年月日（印鑑提出者）（y=516.5pt）
    # テンプレート: 「大・昭・平・西暦」(x=260.2) 「年」(x=345.8) 「月」(x=407.9) 「日生」(x=453.5)
    # 各元号の中心x座標（300dpi画像から計測）:
    #   大: x≈265, 昭: x≈285, 平: x≈305, 西暦: x≈340
    birth_era = rep.get('birth_era', '')
    birth_year = rep.get('birth_year', '')
    birth_month = rep.get('birth_month', '')
    birth_day = rep.get('birth_day', '')
    if birth_era or birth_year:
        era_positions = {
            '大正': (265.0, 516.5),
            '昭和': (291.0, 519.5),
            '平成': (308.0, 518.0),
            '令和': (325.0, 516.5),  # テンプレートに令和なし→西暦位置に近い箇所
            '西暦': (340.0, 516.5),
        }
        if birth_era in era_positions:
            ex, ey = era_positions[birth_era]
            c.setLineWidth(0.8)
            w = 6 if birth_era != '西暦' else 11
            h = 6
            c.ellipse(ex - w, ey - h, ex + w, ey + h + 2, stroke=1, fill=0)

        # 年・月・日を入力
        c.setFont(fn, 9)
        char_w = 5.4  # 9ptフォントの数字1文字幅
        # 複数候補比較テストで最適値を確認: 年=395, 月=440, 日=490
        if birth_year:
            year_str = str(birth_year)
            x_year = 395.0 - len(year_str) * char_w
            c.drawString(x_year, 517.0, year_str)
        if birth_month:
            month_str = str(birth_month)
            x_month = 440.0 - len(month_str) * char_w
            c.drawString(x_month, 517.0, month_str)
        if birth_day:
            day_str = str(birth_day)
            x_day = 490.0 - len(day_str) * char_w
            c.drawString(x_day, 517.0, day_str)

    c.save()
    overlay_buffer.seek(0)

    # テンプレートPDFとオーバーレイを合成
    template_reader = pypdf.PdfReader(template_path)
    overlay_reader = pypdf.PdfReader(overlay_buffer)
    writer = pypdf.PdfWriter()
    template_page = template_reader.pages[0]
    overlay_page = overlay_reader.pages[0]
    template_page.merge_page(overlay_page)
    writer.add_page(template_page)
    output_buffer = io.BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)
    return output_buffer.read()


def generate_stamp_duty_sheet_pdf(data):
    """登録免許税納付用台紙のPDFを生成する"""
    c, buffer, width, height, margin_left, margin_right, margin_top, margin_bottom, content_width, font_name, mm = _setup_pdf_canvas()
    company_type = data.get('company_type', '合同会社')
    # 登録免許税額を計算
    capital = data.get('capital_amount', 0)
    try:
        capital = int(str(capital).replace(',', '').replace('，', ''))
    except Exception:
        capital = 0
    if company_type == '株式会社':
        tax = max(150000, int(capital * 0.007))
    elif company_type == '合同会社':
        tax = max(60000, int(capital * 0.007))
    else:
        tax = 60000
    tax_str = f'{tax:,}'
    # タイトル
    c.setFont(font_name, 14)
    c.drawCentredString(width / 2, height - 30 * mm, '登録免許税納付用台紙')
    # 説明文
    c.setFont(font_name, 9)
    c.drawCentredString(width / 2, height - 42 * mm, f'登録免許税額：金{tax_str}円分の収入印紙を下の枠内に貼付してください。')
    c.drawCentredString(width / 2, height - 48 * mm, '（収入印紙に消印はしないでください。）')
    # 収入印紙貼付欄（大きな枠）
    box_x = margin_left + 10 * mm
    box_y = height - 200 * mm
    box_w = content_width - 20 * mm
    box_h = 130 * mm
    c.setLineWidth(1.5)
    c.rect(box_x, box_y, box_w, box_h)
    # 「収入印紙貼付欄」テキスト
    c.setFont(font_name, 11)
    c.drawCentredString(box_x + box_w / 2, box_y + box_h / 2 + 5 * mm, '収　入　印　紙　貼　付　欄')
    c.setFont(font_name, 9)
    c.drawCentredString(box_x + box_w / 2, box_y + box_h / 2 - 5 * mm, f'（金{tax_str}円）')
    # 注意書き
    c.setFont(font_name, 8)
    c.drawString(margin_left, box_y - 10 * mm, '※ 収入印紙は消印しないでください。')
    c.drawString(margin_left, box_y - 16 * mm, '※ この台紙は設立登記申請書に添付してください。')
    c.save()
    buffer.seek(0)
    return buffer.read()


def generate_registration_items_pdf(data):  # noqa: C901
    """別紙（登記すべき事項）のPDFを生成する（正式雛形）"""
    c, buffer, width, height, margin_left, margin_right, margin_top, margin_bottom, content_width, font_name, mm = _setup_pdf_canvas()

    # --- データ取得 ---
    full_name = _get_full_company_name(data)
    address = data.get('address', '') + data.get('address_detail', '')
    purposes = data.get('purposes', [])
    capital = data.get('capital', '0')
    try:
        capital_int = int(str(capital).replace(',', '').replace('，', ''))
        capital_str = f'{capital_int:,}'
    except (ValueError, TypeError):
        capital_str = str(capital)

    members = data.get('members', [])
    rep_members = [m for m in members if m.get('is_representative')]
    if not rep_members and members:
        rep_members = [members[0]]
    rep = rep_members[0] if rep_members else {}
    rep_name = rep.get('name', '')
    rep_address = rep.get('address', '')

    # --- 描画共通設定 ---
    c.setFillColorRGB(0, 0, 0)
    font_size = 10
    line_height = 30
    # 左右のマージン
    lx = 20 * mm
    rx = width - 20 * mm
    # コンテンツ開始位置（ページ上部から）
    y = height - 35 * mm

    # --- ヘッダー：「別紙」と「1/1頁」 ---
    c.setFont(font_name, 16)
    c.drawString(lx, y, "別紙")
    # 1/1頁を枠付きで描画
    page_label = "1／1　頁"
    page_label_width = 22 * mm
    page_label_height = 8 * mm
    page_box_x = rx - page_label_width
    page_box_y = y - 1 * mm
    c.setLineWidth(1)
    c.rect(page_box_x, page_box_y, page_label_width, page_label_height)
    c.setFont(font_name, 9)
    c.drawCentredString(page_box_x + page_label_width / 2, page_box_y + 2 * mm, page_label)

    y -= 12 * mm

    # --- 描画ヘルパー ---
    def draw_dotted_line(y_pos):
        """y_posに点線を描画"""
        c.setDash(1, 3)
        c.setLineWidth(0.5)
        c.line(lx, y_pos, rx, y_pos)
        c.setDash([])

    def draw_row(text, y_pos):
        """1行描画して次のyを返す"""
        c.setFont(font_name, font_size)
        # 文字を点線の中間に来るよう少し下げて描画
        c.drawString(lx, y_pos - 5, text)
        # 点線は文字の直下
        draw_dotted_line(y_pos - 14)
        return y_pos - line_height

    # --- 内容描画 ---
    y = draw_row(f'「商号」　{full_name}', y)
    y = draw_row(f'「本店」　{address}', y)
    y = draw_row('「公告をする方法」官報に掲載して行う。', y)
    y = draw_row('「目的」', y)
    for i, p in enumerate(purposes, 1):
        y = draw_row(f'（{i}）　{p}', y)
    y = draw_row(f'「資本金の額」金{capital_str}円', y)

    # 業務執行社員
    y = draw_row('「社員に関する事項」', y)
    for member in members:
        y = draw_row('「資格」　業務執行社員', y)
        y = draw_row(f'「氏名」　{member.get("name", "")}', y)

    # 代表社員
    y = draw_row('「社員に関する事項」', y)
    y = draw_row('「資格」　代表社員', y)
    y = draw_row(f'「住所」　{rep_address}', y)
    y = draw_row(f'「氏名」　{rep_name}', y)

    # 登記記録に関する事項
    y = draw_row('「登記記録に関する事項」　設立', y)

    # --- 申請人印（右下） ---
    seal_size = 20 * mm
    seal_x = rx - seal_size
    seal_y = 20 * mm
    c.setLineWidth(1)
    c.rect(seal_x, seal_y, seal_size, seal_size)
    c.setFont(font_name, 8)
    c.drawCentredString(seal_x + seal_size / 2, seal_y - 4 * mm, "申請人印")

    c.save()
    buffer.seek(0)
    return buffer.read()

