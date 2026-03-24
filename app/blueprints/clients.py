"""
顧問先管理ブループリント（SQLAlchemy版）
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.db import SessionLocal
from app.models_clients import TClient, TTaxRecord, TTaxRecordPrefecture, TTaxRecordMunicipality, TFilingOfficeTaxOffice, TFilingOfficePrefecture, TFilingOfficeMunicipality
from flask import jsonify
from app.models_login import TTenant, TKanrisha
from app.utils.decorators import require_roles, ROLES
from sqlalchemy import and_
from datetime import date, datetime

bp = Blueprint('clients', __name__, url_prefix='/clients')


def _get_profession(tenant_id):
    """テナントの士業種別を取得"""
    db = SessionLocal()
    try:
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        return getattr(tenant, 'profession', None) or ''
    finally:
        db.close()


PROFESSION_LABELS = {
    'tax': '税理士',
    'legal': '弁護士',
    'accounting': '公認会計士',
    'sr': '社労士',
}


@bp.route('/')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def clients_root():
    """顧問先ルート → ホームにリダイレクト"""
    return redirect(url_for('clients.home'))


@bp.route('/home')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def home():
    """テナントマイページ（顧問先管理ホーム）"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        profession = getattr(tenant, 'profession', None) or '' if tenant else ''

        # 顧問先統計
        all_clients = db.query(TClient).filter(TClient.tenant_id == tenant_id).all()
        client_count = len(all_clients)
        corp_count = sum(1 for c in all_clients if c.type == '法人')
        ind_count = sum(1 for c in all_clients if c.type == '個人')

        # スタッフ数（テナントに紐づく管理者）
        staff_count = db.query(TKanrisha).filter(
            TKanrisha.tenant_id == tenant_id,
            TKanrisha.active == 1
        ).count()

        return render_template('client_home.html',
                               tenant=tenant,
                               profession=profession,
                               profession_label=PROFESSION_LABELS.get(profession, ''),
                               client_count=client_count,
                               corp_count=corp_count,
                               ind_count=ind_count,
                               staff_count=staff_count)
    finally:
        db.close()


@bp.route('/list')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def clients():
    """顧問先一覧"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        clients = db.query(TClient).filter(TClient.tenant_id == tenant_id).order_by(TClient.id.desc()).all()
        profession = _get_profession(tenant_id)
        return render_template('clients.html', clients=clients, profession=profession,
                               profession_label=PROFESSION_LABELS.get(profession, ''))
    finally:
        db.close()


@bp.route('/add', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def add_client():
    """顧問先追加"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    profession = _get_profession(tenant_id)
    
    if request.method == 'POST':
        client_type = request.form.get('type')
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        notes = request.form.get('notes')
        
        db = SessionLocal()
        try:
            new_client = TClient(
                tenant_id=tenant_id,
                type=client_type,
                name=name,
                email=email,
                phone=phone,
                notes=notes,
                # 共通追加情報
                address=request.form.get('address') or None,
                industry=request.form.get('industry') or None,
                fiscal_year_end=request.form.get('fiscal_year_end') or None,
                contract_start_date=request.form.get('contract_start_date') or None,
            )
            # 士業固有フィールド
            if profession == 'tax':
                new_client.tax_accountant_code = request.form.get('tax_accountant_code') or None
                new_client.tax_id_number = request.form.get('tax_id_number') or None
            elif profession == 'legal':
                new_client.case_number = request.form.get('case_number') or None
                new_client.case_type = request.form.get('case_type') or None
                new_client.opposing_party = request.form.get('opposing_party') or None
            elif profession == 'accounting':
                new_client.audit_type = request.form.get('audit_type') or None
                new_client.listed = int(request.form.get('listed', 0))
            elif profession == 'sr':
                emp = request.form.get('employee_count')
                new_client.employee_count = int(emp) if emp and emp.isdigit() else None
                new_client.labor_insurance_number = request.form.get('labor_insurance_number') or None
                new_client.social_insurance_number = request.form.get('social_insurance_number') or None
                new_client.payroll_closing_day = request.form.get('payroll_closing_day') or None

            db.add(new_client)
            db.commit()
            flash('顧問先を追加しました', 'success')
            return redirect(url_for('clients.clients'))
        except Exception as e:
            db.rollback()
            flash(f'エラーが発生しました: {str(e)}', 'error')
        finally:
            db.close()
    
    return render_template('add_client.html', profession=profession,
                           profession_label=PROFESSION_LABELS.get(profession, ''))


@bp.route('/<int:client_id>')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def client_info(client_id):
    """顧問先詳細"""
    from app.models_company import TCompanyInfo
    
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        
        # 会社基本情報を取得
        company = db.query(TCompanyInfo).filter(TCompanyInfo.顧問先ID == client_id).first()
        profession = _get_profession(tenant_id)
        
        return render_template('client_info.html', client=client, company=company,
                               profession=profession,
                               profession_label=PROFESSION_LABELS.get(profession, ''))
    finally:
        db.close()


@bp.route('/<int:client_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def edit_client(client_id):
    """顧問先編集"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    profession = _get_profession(tenant_id)
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        if request.method == 'POST':
            client.type = request.form.get('type') or client.type
            client.name = request.form.get('name') or client.name
            client.email = request.form.get('email') or None
            client.phone = request.form.get('phone') or None
            client.notes = request.form.get('notes') or None
            client.address = request.form.get('address') or None
            client.industry = request.form.get('industry') or None
            client.fiscal_year_end = request.form.get('fiscal_year_end') or None
            client.contract_start_date = request.form.get('contract_start_date') or None

            if profession == 'tax':
                client.tax_accountant_code = request.form.get('tax_accountant_code') or None
                client.tax_id_number = request.form.get('tax_id_number') or None
            elif profession == 'legal':
                client.case_number = request.form.get('case_number') or None
                client.case_type = request.form.get('case_type') or None
                client.opposing_party = request.form.get('opposing_party') or None
            elif profession == 'accounting':
                client.audit_type = request.form.get('audit_type') or None
                client.listed = int(request.form.get('listed', 0))
            elif profession == 'sr':
                emp = request.form.get('employee_count')
                client.employee_count = int(emp) if emp and emp.isdigit() else None
                client.labor_insurance_number = request.form.get('labor_insurance_number') or None
                client.social_insurance_number = request.form.get('social_insurance_number') or None
                client.payroll_closing_day = request.form.get('payroll_closing_day') or None

            db.commit()
            flash('顧問先情報を更新しました', 'success')
            return redirect(url_for('clients.client_info', client_id=client_id))

        return render_template('edit_client.html', client=client, profession=profession,
                               profession_label=PROFESSION_LABELS.get(profession, ''))
    finally:
        db.close()


@bp.route('/<int:client_id>/chat')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def client_chat(client_id):
    """顧問先チャット"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        
        return render_template('client_chat.html', client=client, messages=[])
    finally:
        db.close()


# ========================================
# 会社基本情報管理機能
# ========================================


@bp.route('/company/<int:company_id>')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def company_info(company_id):
    """会社基本情報詳細"""
    from app.models_company import TCompanyInfo, TCompanyBranch

    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        company = db.query(TCompanyInfo).filter(TCompanyInfo.id == company_id).first()

        if not company:
            flash('会社基本情報が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        # テナントIDの検証（顧問先経由）
        client = db.query(TClient).filter(TClient.id == company.顧問先ID).first()
        if not client or client.tenant_id != tenant_id:
            flash('アクセス権限がありません', 'error')
            return redirect(url_for('clients.clients'))

        branches = db.query(TCompanyBranch).filter(
            TCompanyBranch.company_id == company_id
        ).order_by(TCompanyBranch.sort_order, TCompanyBranch.id).all()

        return render_template('company_info_company.html', company=company, branches=branches)
    finally:
        db.close()


@bp.route('/company/create/<int:client_id>', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def company_create(client_id):
    """会社基本情報新規登録"""
    from app.models_company import TCompanyInfo
    
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        # 顧問先の存在確認とテナントID検証
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        
        # 既に会社基本情報が登録されているかチェック
        existing_company = db.query(TCompanyInfo).filter(
            TCompanyInfo.顧問先ID == client_id
        ).first()
        
        if existing_company:
            flash('この顧問先の会社基本情報は既に登録されています', 'info')
            return redirect(url_for('clients.company_info', company_id=existing_company.id))
        
        if request.method == 'POST':
            new_company = TCompanyInfo(
                顧問先ID=client_id,
                会社名=request.form.get('会社名'),
                郵便番号=request.form.get('郵便番号'),
                都道府県=request.form.get('都道府県'),
                市区町村番地=request.form.get('市区町村番地'),
                建物名部屋番号=request.form.get('建物名部屋番号'),
                電話番号1=request.form.get('電話番号1'),
                電話番号2=request.form.get('電話番号2'),
                ファックス番号=request.form.get('ファックス番号'),
                メールアドレス=request.form.get('メールアドレス'),
                担当者名=request.form.get('担当者名'),
                業種=request.form.get('業種'),
                従業員数=int(request.form.get('従業員数')) if request.form.get('従業員数') else None,
                法人番号=request.form.get('法人番号')
            )
            db.add(new_company)
            db.commit()
            flash('会社基本情報を登録しました', 'success')
            return redirect(url_for('clients.client_info', client_id=client_id))
        
        return render_template('company_create.html', client=client)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('clients.client_info', client_id=client_id))
    finally:
        db.close()


@bp.route('/company/<int:company_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def company_edit(company_id):
    """会社基本情報編集"""
    from app.models_company import TCompanyInfo
    
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        company = db.query(TCompanyInfo).filter(TCompanyInfo.id == company_id).first()
        
        if not company:
            flash('会社基本情報が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        
        # テナントIDの検証
        client = db.query(TClient).filter(TClient.id == company.顧問先ID).first()
        if not client or client.tenant_id != tenant_id:
            flash('アクセス権限がありません', 'error')
            return redirect(url_for('clients.clients'))
        
        if request.method == 'POST':
            company.会社名 = request.form.get('会社名')
            company.郵便番号 = request.form.get('郵便番号')
            company.都道府県 = request.form.get('都道府県')
            company.市区町村番地 = request.form.get('市区町村番地')
            company.建物名部屋番号 = request.form.get('建物名部屋番号')
            company.電話番号1 = request.form.get('電話番号1')
            company.電話番号2 = request.form.get('電話番号2')
            company.ファックス番号 = request.form.get('ファックス番号')
            company.メールアドレス = request.form.get('メールアドレス')
            company.担当者名 = request.form.get('担当者名')
            company.業種 = request.form.get('業種')
            company.従業員数 = int(request.form.get('従業員数')) if request.form.get('従業員数') else None
            company.法人番号 = request.form.get('法人番号')
            
            db.commit()
            flash('会社基本情報を更新しました', 'success')
            return redirect(url_for('clients.company_info', company_id=company_id))
        
        clients_list = db.query(TClient).filter(TClient.tenant_id == tenant_id).all()
        return render_template('company_edit.html', company=company, clients=clients_list)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('clients.company_info', company_id=company_id))
    finally:
        db.close()


@bp.route('/company/<int:company_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def company_delete(company_id):
    """会社基本情報削除"""
    from app.models_company import TCompanyInfo
    
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    try:
        company = db.query(TCompanyInfo).filter(TCompanyInfo.id == company_id).first()
        
        if not company:
            flash('会社基本情報が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        
        # テナントIDの検証
        client = db.query(TClient).filter(TClient.id == company.顧問先ID).first()
        if not client or client.tenant_id != tenant_id:
            flash('アクセス権限がありません', 'error')
            return redirect(url_for('clients.clients'))
        
        client_id = company.顧問先ID
        db.delete(company)
        db.commit()
        flash('会社基本情報を削除しました', 'success')
        return redirect(url_for('clients.client_info', client_id=client_id))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('clients.clients'))
    finally:
        db.close()


# ========================================
# 会社拠点情報（本店・支店）管理
# ========================================

@bp.route('/company/<int:company_id>/branches/<int:branch_id>')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def branch_info(company_id, branch_id):
    """拠点情報（本店・支店）詳細"""
    from app.models_company import TCompanyInfo, TCompanyBranch

    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        company = db.query(TCompanyInfo).filter(TCompanyInfo.id == company_id).first()
        if not company:
            flash('会社基本情報が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        client = db.query(TClient).filter(TClient.id == company.顧問先ID).first()
        if not client or client.tenant_id != tenant_id:
            flash('アクセス権限がありません', 'error')
            return redirect(url_for('clients.clients'))

        branch = db.query(TCompanyBranch).filter(
            TCompanyBranch.id == branch_id,
            TCompanyBranch.company_id == company_id
        ).first()
        if not branch:
            flash('拠点情報が見つかりません', 'error')
            return redirect(url_for('clients.company_info', company_id=company_id))

        return render_template('company_branch_info.html', company=company, branch=branch)
    finally:
        db.close()


@bp.route('/company/<int:company_id>/branches/add', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def branch_add(company_id):
    """拠点情報（本店・支店）追加"""
    from app.models_company import TCompanyInfo, TCompanyBranch

    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        company = db.query(TCompanyInfo).filter(TCompanyInfo.id == company_id).first()
        if not company:
            flash('会社基本情報が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        client = db.query(TClient).filter(TClient.id == company.顧問先ID).first()
        if not client or client.tenant_id != tenant_id:
            flash('アクセス権限がありません', 'error')
            return redirect(url_for('clients.clients'))

        if request.method == 'POST':
            emp_str = request.form.get('当拠点従業員数', '').strip()
            emp_count = int(emp_str) if emp_str.isdigit() else None
            branch = TCompanyBranch(
                company_id=company_id,
                branch_type=request.form.get('branch_type', '支店'),
                branch_name=request.form.get('branch_name', '').strip() or None,
                郵便番号=request.form.get('郵便番号', '').strip() or None,
                都道府県=request.form.get('都道府県', '').strip() or None,
                市区町村番地=request.form.get('市区町村番地', '').strip() or None,
                建物名部屋番号=request.form.get('建物名部屋番号', '').strip() or None,
                電話番号1=request.form.get('電話番号1', '').strip() or None,
                電話番号2=request.form.get('電話番号2', '').strip() or None,
                ファックス番号=request.form.get('ファックス番号', '').strip() or None,
                メールアドレス=request.form.get('メールアドレス', '').strip() or None,
                担当者名=request.form.get('担当者名', '').strip() or None,
                当拠点従業員数=emp_count,
            )
            db.add(branch)
            db.commit()
            flash('拠点情報を追加しました', 'success')
            return redirect(url_for('clients.company_info', company_id=company_id))

        branches = db.query(TCompanyBranch).filter(
            TCompanyBranch.company_id == company_id).all()
        return render_template('company_branch_edit.html',
                               company=company, branch=None, branches=branches)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('clients.company_info', company_id=company_id))
    finally:
        db.close()


@bp.route('/company/<int:company_id>/branches/<int:branch_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def branch_edit(company_id, branch_id):
    """拠点情報（本店・支店）編集"""
    from app.models_company import TCompanyInfo, TCompanyBranch

    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        company = db.query(TCompanyInfo).filter(TCompanyInfo.id == company_id).first()
        if not company:
            flash('会社基本情報が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        client = db.query(TClient).filter(TClient.id == company.顧問先ID).first()
        if not client or client.tenant_id != tenant_id:
            flash('アクセス権限がありません', 'error')
            return redirect(url_for('clients.clients'))

        branch = db.query(TCompanyBranch).filter(
            TCompanyBranch.id == branch_id,
            TCompanyBranch.company_id == company_id
        ).first()
        if not branch:
            flash('拠点情報が見つかりません', 'error')
            return redirect(url_for('clients.company_info', company_id=company_id))

        if request.method == 'POST':
            branch.branch_type = request.form.get('branch_type', '支店')
            branch.branch_name = request.form.get('branch_name', '').strip() or None
            branch.郵便番号 = request.form.get('郵便番号', '').strip() or None
            branch.都道府県 = request.form.get('都道府県', '').strip() or None
            branch.市区町村番地 = request.form.get('市区町村番地', '').strip() or None
            branch.建物名部屋番号 = request.form.get('建物名部屋番号', '').strip() or None
            branch.電話番号1 = request.form.get('電話番号1', '').strip() or None
            branch.電話番号2 = request.form.get('電話番号2', '').strip() or None
            branch.ファックス番号 = request.form.get('ファックス番号', '').strip() or None
            branch.メールアドレス = request.form.get('メールアドレス', '').strip() or None
            branch.担当者名 = request.form.get('担当者名', '').strip() or None
            emp_str = request.form.get('当拠点従業員数', '').strip()
            branch.当拠点従業員数 = int(emp_str) if emp_str.isdigit() else None
            db.commit()
            flash('拠点情報を更新しました', 'success')
            return redirect(url_for('clients.company_info', company_id=company_id))

        return render_template('company_branch_edit.html',
                               company=company, branch=branch, branches=[])
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('clients.company_info', company_id=company_id))
    finally:
        db.close()


@bp.route('/company/<int:company_id>/branches/<int:branch_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def branch_delete(company_id, branch_id):
    """拠点情報（本店・支店）削除"""
    from app.models_company import TCompanyInfo, TCompanyBranch

    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        company = db.query(TCompanyInfo).filter(TCompanyInfo.id == company_id).first()
        if not company:
            flash('会社基本情報が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        client = db.query(TClient).filter(TClient.id == company.顧問先ID).first()
        if not client or client.tenant_id != tenant_id:
            flash('アクセス権限がありません', 'error')
            return redirect(url_for('clients.clients'))

        branch = db.query(TCompanyBranch).filter(
            TCompanyBranch.id == branch_id,
            TCompanyBranch.company_id == company_id
        ).first()
        if branch:
            db.delete(branch)
            db.commit()
            flash('拠点情報を削除しました', 'success')
        else:
            flash('拠点情報が見つかりません', 'error')
        return redirect(url_for('clients.company_info', company_id=company_id))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('clients.company_info', company_id=company_id))
    finally:
        db.close()


# ========================================
# 拠点情報から申告先情報を自動登録
# ========================================

@bp.route('/company/<int:company_id>/branches/<int:branch_id>/auto_register_filing', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def branch_auto_register_filing(company_id, branch_id):
    """拠点情報から申告先情報（税務署・都道府県・市区町村）を自動登録"""
    import requests as http_requests
    from bs4 import BeautifulSoup
    import re
    from app.models_company import TCompanyInfo, TCompanyBranch
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        company = db.query(TCompanyInfo).filter(TCompanyInfo.id == company_id).first()
        if not company:
            flash('会社基本情報が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        client = db.query(TClient).filter(TClient.id == company.顧問先ID).first()
        if not client or client.tenant_id != tenant_id:
            flash('アクセス権限がありません', 'error')
            return redirect(url_for('clients.clients'))
        branch = db.query(TCompanyBranch).filter(
            TCompanyBranch.id == branch_id,
            TCompanyBranch.company_id == company_id
        ).first()
        if not branch:
            flash('拠点情報が見つかりません', 'error')
            return redirect(url_for('clients.company_info', company_id=company_id))
        client_id = company.顧問先ID
        registered = []
        skipped = []
        errors = []
        # 1. 税務署を郵便番号から自動取得
        tax_office_name = None
        zipcode = branch.郵便番号
        if zipcode:
            zipcode_clean = zipcode.replace('-', '').replace('ー', '').replace('－', '').replace(' ', '').replace('　', '')
            if len(zipcode_clean) == 7 and zipcode_clean.isdigit():
                try:
                    data = {
                        'KSTYPE': 'ksz',
                        'TODOFUKEN_TO_ASCII': '',
                        'ADDR_TO_ASCII': '',
                        'kszc1': zipcode_clean[:3],
                        'kszc2': zipcode_clean[3:],
                        'ksaTodofuken': '',
                        'ksaddr': '',
                    }
                    headers = {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Referer': 'https://www.nta.go.jp/about/organization/access/map.htm',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    resp = http_requests.post(
                        'https://www.nta.go.jp/cgi-bin/zeimusho/kensaku/kensakuprocess.php',
                        data=data, headers=headers, timeout=10
                    )
                    text = resp.content.decode('utf-8', errors='replace')
                    soup = BeautifulSoup(text, 'html.parser')
                    full_text = soup.get_text()
                    matches = re.findall(r'を管轄する税務署[\s\n]*([^\s電話\n]+)', full_text)
                    if matches:
                        tax_office_name = matches[0]
                    else:
                        errors.append('税務署が見つかりませんでした（国税庁サービスへの接続に失敗した可能性があります）')
                except Exception as e:
                    errors.append(f'税務署の自動取得に失敗しました: {str(e)}')
            else:
                errors.append('郵便番号の形式が正しくないため、税務署を自動取得できませんでした')
        else:
            errors.append('郵便番号が未登録のため、税務署を自動取得できませんでした')
        # 2. 税務署を申告先に登録
        if tax_office_name:
            existing = db.query(TFilingOfficeTaxOffice).filter(
                TFilingOfficeTaxOffice.client_id == client_id,
                TFilingOfficeTaxOffice.tax_office_name == tax_office_name
            ).first()
            if existing:
                skipped.append(f'税務署「{tax_office_name}」は既に登録済みのためスキップしました')
            else:
                obj = TFilingOfficeTaxOffice(client_id=client_id, tax_office_name=tax_office_name)
                db.add(obj)
                registered.append(f'税務署「{tax_office_name}」を登録しました')
        # 3. 都道府県を申告先に登録
        pref_name = branch.都道府県
        if pref_name:
            existing = db.query(TFilingOfficePrefecture).filter(
                TFilingOfficePrefecture.client_id == client_id,
                TFilingOfficePrefecture.prefecture_name == pref_name
            ).first()
            if existing:
                skipped.append(f'都道府県「{pref_name}」は既に登録済みのためスキップしました')
            else:
                obj = TFilingOfficePrefecture(client_id=client_id, prefecture_name=pref_name)
                db.add(obj)
                registered.append(f'都道府県「{pref_name}」を登録しました')
        else:
            errors.append('都道府県が未登録のため、都道府県を自動登録できませんでした')
        # 4. 市区町村を申告先に登録（市区町村番地から市区町村名を抽出）
        addr = branch.市区町村番地
        if addr:
            # 市区町村名を抽出（「市」「区」「町」「村」で区切る）
            muni_match = re.match(r'^([^\d０-９]+?[市区町村郡](?:[^\d０-９]+?[区町村])?)', addr)
            if muni_match:
                muni_name = muni_match.group(1)
            else:
                muni_name = addr
            existing = db.query(TFilingOfficeMunicipality).filter(
                TFilingOfficeMunicipality.client_id == client_id,
                TFilingOfficeMunicipality.municipality_name == muni_name
            ).first()
            if existing:
                skipped.append(f'市区町村「{muni_name}」は既に登録済みのためスキップしました')
            else:
                obj = TFilingOfficeMunicipality(client_id=client_id, municipality_name=muni_name)
                db.add(obj)
                registered.append(f'市区町村「{muni_name}」を登録しました')
        else:
            errors.append('市区町村番地が未登録のため、市区町村を自動登録できませんでした')
        db.commit()
        # フラッシュメッセージ
        for msg in registered:
            flash(msg, 'success')
        for msg in skipped:
            flash(msg, 'info')
        for msg in errors:
            flash(msg, 'warning')
        if not registered and not skipped and not errors:
            flash('登録できる情報がありませんでした', 'warning')
        return redirect(url_for('clients.branch_info', company_id=company_id, branch_id=branch_id))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('clients.branch_info', company_id=company_id, branch_id=branch_id))
    finally:
        db.close()


# ========================================
# クライアントアカウント管理（税理士事務所側）
# ========================================

@bp.route('/<int:client_id>/accounts')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def client_accounts(client_id):
    """顧問先のクライアントアカウント一覧"""
    from app.models_client_users import TClientUser
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        users = db.query(TClientUser).filter(
            TClientUser.client_id == client_id
        ).order_by(TClientUser.id.asc()).all()
        return render_template('client_accounts.html', client=client, users=users)
    finally:
        db.close()


@bp.route('/<int:client_id>/accounts/issue', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def issue_client_account(client_id):
    """クライアント初期アカウント発行"""
    import secrets
    from datetime import date, datetime, timedelta
    from app.models_client_users import TClientUser, TClientInvitation
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        invite_url = None
        if request.method == 'POST':
            issue_type = request.form.get('issue_type', 'invite')  # invite or direct

            if issue_type == 'invite':
                # 招待リンク方式
                email = (request.form.get('email') or '').strip()
                role = request.form.get('role') or 'client_admin'
                if role not in ('client_admin', 'client_employee'):
                    role = 'client_admin'
                token = secrets.token_urlsafe(32)
                expires_at = datetime.utcnow() + timedelta(days=7)
                invitation = TClientInvitation(
                    client_id=client_id,
                    token=token,
                    email=email if email else None,
                    role=role,
                    invited_by_role=session.get('role'),
                    invited_by_id=session.get('user_id'),
                    used=0,
                    expires_at=expires_at
                )
                db.add(invitation)
                db.commit()
                from flask import url_for as _url_for
                invite_url = _url_for('client_auth.accept_invite', token=token, _external=True)
                flash('招待リンクを作成しました。', 'success')
            else:
                # 直接アカウント作成方式
                from werkzeug.security import generate_password_hash
                login_id = (request.form.get('login_id') or '').strip()
                name = (request.form.get('name') or '').strip()
                email = (request.form.get('email') or '').strip()
                password = request.form.get('password') or ''
                role = request.form.get('role') or 'client_admin'
                if role not in ('client_admin', 'client_employee'):
                    role = 'client_admin'

                if not login_id or not name or not email or not password:
                    flash('すべての項目を入力してください。', 'error')
                    return render_template('issue_client_account.html', client=client, invite_url=None)

                existing = db.query(TClientUser).filter(TClientUser.login_id == login_id).first()
                if existing:
                    flash('このログインIDはすでに使用されています。', 'error')
                    return render_template('issue_client_account.html', client=client, invite_url=None)

                new_user = TClientUser(
                    client_id=client_id,
                    login_id=login_id,
                    name=name,
                    email=email,
                    password_hash=generate_password_hash(password),
                    role=role,
                    active=1
                )
                db.add(new_user)
                db.commit()
                flash(f'クライアントアカウントを作成しました。ログインID: {login_id}', 'success')
                return redirect(url_for('clients.client_accounts', client_id=client_id))

        return render_template('issue_client_account.html', client=client, invite_url=invite_url)
    finally:
        db.close()


@bp.route('/<int:client_id>/accounts/<int:user_id>/toggle', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def toggle_client_account(client_id, user_id):
    """クライアントアカウントの有効/無効切り替え"""
    from app.models_client_users import TClientUser
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        user = db.query(TClientUser).filter(
            TClientUser.id == user_id,
            TClientUser.client_id == client_id
        ).first()
        if user:
            user.active = 0 if user.active == 1 else 1
            db.commit()
            status = '有効' if user.active == 1 else '無効'
            flash(f'{user.name} を{status}にしました。', 'success')
        else:
            flash('ユーザーが見つかりません。', 'error')
    finally:
        db.close()
    return redirect(url_for('clients.client_accounts', client_id=client_id))


# ========================================
# ストレージフォルダパス設定
# ========================================

@bp.route('/<int:client_id>/storage_folder', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def client_storage_folder(client_id):
    """顧問先のストレージ保存先フォルダパス設定"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        if request.method == 'POST':
            folder_path = request.form.get('storage_folder_path', '').strip()
            # 先頭の/を保証し、末尾の/を除去
            if folder_path and not folder_path.startswith('/'):
                folder_path = '/' + folder_path
            folder_path = folder_path.rstrip('/')
            client.storage_folder_path = folder_path if folder_path else None
            db.commit()
            flash('ストレージフォルダパスを保存しました', 'success')
            return redirect(url_for('clients.client_info', client_id=client_id))

        # ストレージが設定されている場合はルートフォルダ一覧を取得
        storage_folders = []
        storage_configured = False
        try:
            from app.utils.tenant_storage_adapter import get_storage_adapter
            adapter = get_storage_adapter(tenant_id)
            storage_folders = adapter.list_folders('/')  # ルートのフォルダ一覧
            storage_configured = True
        except Exception:
            pass

        return render_template(
            'client_storage_folder.html',
            client=client,
            storage_folders=storage_folders,
            storage_configured=storage_configured
        )
    finally:
        db.close()


# ========================================
# チャット機能
# ========================================

@bp.route('/chat', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def chat():
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    
    from datetime import date, datetime
    from app.utils.db import get_db, _sql
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        if request.method == 'POST':
            sender = session.get('username', 'Unknown')
            message = request.form.get('message', '')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            sql = _sql(conn, 'INSERT INTO "T_メッセージ" (sender, message, timestamp) VALUES (%s, %s, %s)')
            cur.execute(sql, (sender, message, timestamp))
            # autocommit=Trueのためconn.commit()は不要
            return redirect(url_for('clients.chat'))
        
        sql = _sql(conn, 'SELECT * FROM "T_メッセージ" ORDER BY id DESC LIMIT 20')
        cur.execute(sql)
        messages = cur.fetchall()
        return render_template('chat.html', messages=list(reversed(messages)))
    finally:
        conn.close()


# ========================================
# ファイル共有機能
# ========================================

@bp.route('/files', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def files():
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    
    from datetime import date, datetime
    from app.utils.db import get_db, _sql
    from app.utils.storage import storage_manager
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        if request.method == 'POST':
            f = request.files.get('file')
            if f and f.filename:
                uploader = session.get('username', 'Unknown')
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # S3にアップロード
                if storage_manager.is_enabled():
                    result = storage_manager.upload_file(f, f.filename)
                    if result['success']:
                        # filenameにS3のURLを保存
                        sql = _sql(conn, 'INSERT INTO "T_ファイル" (filename, uploader, timestamp) VALUES (%s, %s, %s)')
                        cur.execute(sql, (result['url'], uploader, timestamp))
                        flash('ファイルをアップロードしました', 'success')
                    else:
                        flash(f'アップロードエラー: {result["error"]}', 'error')
                else:
                    flash('ストレージ連携が設定されていません。環境変数を確認してください。', 'error')
                
                return redirect(url_for('clients.files'))
        
        sql = _sql(conn, 'SELECT * FROM "T_ファイル" ORDER BY id DESC')
        cur.execute(sql)
        files_list = cur.fetchall()
        return render_template('files.html', files=files_list)
    finally:
        conn.close()


# ========================================
# 士業固有情報管理
# ========================================
@bp.route('/<int:client_id>/profession_info')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def profession_info(client_id):
    """士業固有情報詳細ページ"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        profession = _get_profession(tenant_id)
        return render_template('client_profession_info.html', client=client,
                               profession=profession,
                               profession_label=PROFESSION_LABELS.get(profession, ''))
    finally:
        db.close()


@bp.route('/<int:client_id>/profession_info/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def edit_profession_info(client_id):
    """士業固有情報編集ページ"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        profession = _get_profession(tenant_id)

        if request.method == 'POST':
            client.contract_start_date = request.form.get('contract_start_date') or None
            client.fiscal_year_end = request.form.get('fiscal_year_end') or None
            if profession == 'tax':
                client.tax_accountant_code = request.form.get('tax_accountant_code') or None
                client.tax_id_number = request.form.get('tax_id_number') or None
            elif profession == 'legal':
                client.case_number = request.form.get('case_number') or None
                client.case_type = request.form.get('case_type') or None
                client.opposing_party = request.form.get('opposing_party') or None
            elif profession == 'accounting':
                client.audit_type = request.form.get('audit_type') or None
                client.listed = int(request.form.get('listed', 0))
            elif profession == 'sr':
                emp = request.form.get('employee_count')
                client.employee_count = int(emp) if emp and emp.isdigit() else None
                client.labor_insurance_number = request.form.get('labor_insurance_number') or None
                client.social_insurance_number = request.form.get('social_insurance_number') or None
                client.payroll_closing_day = request.form.get('payroll_closing_day') or None
            db.commit()
            flash('業務情報を更新しました', 'success')
            return redirect(url_for('clients.profession_info', client_id=client_id))

        return render_template('client_profession_info_edit.html', client=client,
                               profession=profession,
                               profession_label=PROFESSION_LABELS.get(profession, ''))
    finally:
        db.close()


# ===== 受託業務管理 =====

@bp.route('/<int:client_id>/commissioned_works')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def commissioned_works(client_id):
    """受託業務一覧ページ"""
    from app.models_clients import TCommissionedWork
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        works = db.query(TCommissionedWork).filter(
            and_(TCommissionedWork.client_id == client_id,
                 TCommissionedWork.tenant_id == tenant_id)
        ).order_by(TCommissionedWork.start_date).all()
        profession = _get_profession(tenant_id)
        return render_template('client_commissioned_works.html',
                               client=client, works=works,
                               profession=profession,
                               profession_label=PROFESSION_LABELS.get(profession, ''))
    finally:
        db.close()


@bp.route('/<int:client_id>/commissioned_works/add', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def add_commissioned_work(client_id):
    """受託業務追加"""
    from app.models_clients import TCommissionedWork
    from datetime import date, datetime
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        profession = _get_profession(tenant_id)
        if request.method == 'POST':
            work_name = request.form.get('work_name', '').strip()
            if not work_name:
                flash('業務名は必須です', 'error')
                return render_template('client_commissioned_work_form.html',
                                       client=client, work=None,
                                       profession=profession,
                                       profession_label=PROFESSION_LABELS.get(profession, ''))
            fee_str = request.form.get('fee', '').strip()
            fee = int(fee_str) if fee_str.isdigit() else None
            work = TCommissionedWork(
                client_id=client_id,
                tenant_id=tenant_id,
                work_name=work_name,
                start_date=request.form.get('start_date') or None,
                fee=fee,
                fee_cycle=request.form.get('fee_cycle') or None,
                notes=request.form.get('notes') or None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(work)
            db.commit()
            flash('受託業務を追加しました', 'success')
            return redirect(url_for('clients.commissioned_works', client_id=client_id))
        return render_template('client_commissioned_work_form.html',
                               client=client, work=None,
                               profession=profession,
                               profession_label=PROFESSION_LABELS.get(profession, ''))
    finally:
        db.close()


@bp.route('/<int:client_id>/commissioned_works/<int:work_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def edit_commissioned_work(client_id, work_id):
    """受託業務編集"""
    from app.models_clients import TCommissionedWork
    from datetime import date, datetime
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        work = db.query(TCommissionedWork).filter(
            and_(TCommissionedWork.id == work_id,
                 TCommissionedWork.client_id == client_id,
                 TCommissionedWork.tenant_id == tenant_id)
        ).first()
        if not work:
            flash('受託業務が見つかりません', 'error')
            return redirect(url_for('clients.commissioned_works', client_id=client_id))
        profession = _get_profession(tenant_id)
        if request.method == 'POST':
            work_name = request.form.get('work_name', '').strip()
            if not work_name:
                flash('業務名は必須です', 'error')
                return render_template('client_commissioned_work_form.html',
                                       client=client, work=work,
                                       profession=profession,
                                       profession_label=PROFESSION_LABELS.get(profession, ''))
            fee_str = request.form.get('fee', '').strip()
            work.work_name = work_name
            work.start_date = request.form.get('start_date') or None
            work.fee = int(fee_str) if fee_str.isdigit() else None
            work.fee_cycle = request.form.get('fee_cycle') or None
            work.notes = request.form.get('notes') or None
            work.updated_at = datetime.utcnow()
            db.commit()
            flash('受託業務を更新しました', 'success')
            return redirect(url_for('clients.commissioned_works', client_id=client_id))
        return render_template('client_commissioned_work_form.html',
                               client=client, work=work,
                               profession=profession,
                               profession_label=PROFESSION_LABELS.get(profession, ''))
    finally:
        db.close()


@bp.route('/<int:client_id>/commissioned_works/<int:work_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def delete_commissioned_work(client_id, work_id):
    """受託業務削除"""
    from app.models_clients import TCommissionedWork
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        work = db.query(TCommissionedWork).filter(
            and_(TCommissionedWork.id == work_id,
                 TCommissionedWork.client_id == client_id,
                 TCommissionedWork.tenant_id == tenant_id)
        ).first()
        if work:
            db.delete(work)
            db.commit()
            flash('受託業務を削除しました', 'success')
        else:
            flash('受託業務が見つかりません', 'error')
        return redirect(url_for('clients.commissioned_works', client_id=client_id))
    finally:
        db.close()


# ===== 税務申告基本情報 =====

@bp.route('/<int:client_id>/tax_info')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def tax_info(client_id):
    """税務申告基本情報詳細ページ"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        profession = _get_profession(tenant_id)
        filing_tax_offices = db.query(TFilingOfficeTaxOffice).filter(
            TFilingOfficeTaxOffice.client_id == client_id).all()
        filing_prefectures = db.query(TFilingOfficePrefecture).filter(
            TFilingOfficePrefecture.client_id == client_id).all()
        filing_municipalities = db.query(TFilingOfficeMunicipality).filter(
            TFilingOfficeMunicipality.client_id == client_id).all()
        return render_template('client_tax_info.html', client=client,
                               profession=profession,
                               profession_label=PROFESSION_LABELS.get(profession, ''),
                               filing_tax_offices=filing_tax_offices,
                               filing_prefectures=filing_prefectures,
                               filing_municipalities=filing_municipalities)
    finally:
        db.close()


@bp.route('/<int:client_id>/tax_info/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def edit_tax_info(client_id):
    """税務申告基本情報編集ページ"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))
        profession = _get_profession(tenant_id)
        if request.method == 'POST':
            fy_start = request.form.get('fiscal_year_start_month', '').strip()
            fy_end = request.form.get('fiscal_year_end_month', '').strip()
            client.fiscal_year_start_month = int(fy_start) if fy_start.isdigit() else None
            client.fiscal_year_end_month = int(fy_end) if fy_end.isdigit() else None
            client.established_date = request.form.get('established_date') or None
            client.establishment_notification = int(request.form.get('establishment_notification', 0))
            client.blue_return = int(request.form.get('blue_return', 0))
            client.consumption_tax_payer = int(request.form.get('consumption_tax_payer', 0))
            if client.consumption_tax_payer:
                client.consumption_tax_method = request.form.get('consumption_tax_method') or None
                if client.consumption_tax_method == 'standard':
                    client.consumption_tax_calc = request.form.get('consumption_tax_calc') or None
                else:
                    client.consumption_tax_calc = None
            else:
                client.consumption_tax_method = None
                client.consumption_tax_calc = None
            client.qualified_invoice_registered = int(request.form.get('qualified_invoice_registered', 0))
            if client.qualified_invoice_registered:
                client.qualified_invoice_number = request.form.get('qualified_invoice_number') or None
            else:
                client.qualified_invoice_number = None
            client.salary_office_notification = int(request.form.get('salary_office_notification', 0))
            client.withholding_tax_special = int(request.form.get('withholding_tax_special', 0))
            client.corp_tax_extension = int(request.form.get('corp_tax_extension', 0))
            client.consumption_tax_extension = int(request.form.get('consumption_tax_extension', 0))
            client.prefectural_tax_extension = int(request.form.get('prefectural_tax_extension', 0))
            client.municipal_tax_extension = int(request.form.get('municipal_tax_extension', 0))
            client.has_fixed_asset_tax = int(request.form.get('has_fixed_asset_tax', 0))
            client.has_depreciable_asset_tax = int(request.form.get('has_depreciable_asset_tax', 0))
            db.commit()
            flash('税務申告基本情報を更新しました', 'success')
            return redirect(url_for('clients.tax_info', client_id=client_id))
        filing_tax_offices = db.query(TFilingOfficeTaxOffice).filter(
            TFilingOfficeTaxOffice.client_id == client_id).all()
        filing_prefectures = db.query(TFilingOfficePrefecture).filter(
            TFilingOfficePrefecture.client_id == client_id).all()
        filing_municipalities = db.query(TFilingOfficeMunicipality).filter(
            TFilingOfficeMunicipality.client_id == client_id).all()
        return render_template('client_tax_info_edit.html', client=client,
                               profession=profession,
                               profession_label=PROFESSION_LABELS.get(profession, ''),
                               filing_tax_offices=filing_tax_offices,
                               filing_prefectures=filing_prefectures,
                               filing_municipalities=filing_municipalities)
    finally:
        db.close()


@bp.route('/<int:client_id>/filing_offices/add', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def add_filing_office(client_id):
    """申告先を追加（AJAX）"""
    tenant_id = session.get('tenant_id')
    data = request.get_json()
    office_type = data.get('office_type')
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': '名前が空です'})
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            return jsonify({'success': False, 'error': '顧問先が見つかりません'})
        if office_type == 'tax_office':
            obj = TFilingOfficeTaxOffice(client_id=client_id, tax_office_name=name)
        elif office_type == 'prefecture':
            obj = TFilingOfficePrefecture(client_id=client_id, prefecture_name=name)
        elif office_type == 'municipality':
            obj = TFilingOfficeMunicipality(client_id=client_id, municipality_name=name)
        else:
            return jsonify({'success': False, 'error': '不正なタイプです'})
        db.add(obj)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        db.close()


@bp.route('/<int:client_id>/filing_offices/delete/<office_type>/<int:office_id>')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def delete_filing_office(client_id, office_type, office_id):
    """申告先を削除"""
    db = SessionLocal()
    try:
        if office_type == 'tax_office':
            obj = db.query(TFilingOfficeTaxOffice).filter(
                TFilingOfficeTaxOffice.id == office_id,
                TFilingOfficeTaxOffice.client_id == client_id).first()
        elif office_type == 'prefecture':
            obj = db.query(TFilingOfficePrefecture).filter(
                TFilingOfficePrefecture.id == office_id,
                TFilingOfficePrefecture.client_id == client_id).first()
        elif office_type == 'municipality':
            obj = db.query(TFilingOfficeMunicipality).filter(
                TFilingOfficeMunicipality.id == office_id,
                TFilingOfficeMunicipality.client_id == client_id).first()
        else:
            obj = None
        if obj:
            db.delete(obj)
            db.commit()
    finally:
        db.close()
    return redirect(url_for('clients.edit_tax_info', client_id=client_id))

# ─────────────────────────────────────────────
# 申告先情報用拠点一覧・税務署自動取得 API
# ─────────────────────────────────────────────
@bp.route('/<int:client_id>/branches_for_filing')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def branches_for_filing(client_id):
    """申告先情報登録用の拠点一覧をJSONで返す"""
    from app.models_company import TCompanyInfo, TCompanyBranch
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': '未認証'}), 401
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            return jsonify({'error': '顧問先が見つかりません'}), 404
        company = db.query(TCompanyInfo).filter(TCompanyInfo.顧問先ID == client_id).first()
        if not company:
            return jsonify({'branches': []})
        branches = db.query(TCompanyBranch).filter(
            TCompanyBranch.company_id == company.id
        ).order_by(TCompanyBranch.branch_type).all()
        result = []
        for b in branches:
            result.append({
                'id': b.id,
                'branch_type': b.branch_type,
                'branch_name': b.branch_name or '',
                '郵便番号': b.郵便番号 or '',
                '都道府県': b.都道府県 or '',
                '市区町村番地': b.市区町村番地 or '',
            })
        return jsonify({'branches': result})
    finally:
        db.close()


@bp.route('/<int:client_id>/get_tax_office_by_zipcode')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def get_tax_office_by_zipcode(client_id):
    """郵便番号から国税庁サービスで税務署名を取得"""
    import requests as http_requests
    from bs4 import BeautifulSoup
    import re
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': '未認証'}), 401
    zipcode = request.args.get('zipcode', '').strip()
    if not zipcode:
        return jsonify({'error': '郵便番号が指定されていません'})
    zipcode_clean = zipcode.replace('-', '').replace('ー', '').replace('－', '').replace(' ', '').replace('　', '')
    if len(zipcode_clean) != 7 or not zipcode_clean.isdigit():
        return jsonify({'error': '郵便番号の形式が正しくありません（7桁の数字）'})
    try:
        data = {
            'KSTYPE': 'ksz',
            'TODOFUKEN_TO_ASCII': '',
            'ADDR_TO_ASCII': '',
            'kszc1': zipcode_clean[:3],
            'kszc2': zipcode_clean[3:],
            'ksaTodofuken': '',
            'ksaddr': '',
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://www.nta.go.jp/about/organization/access/map.htm',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = http_requests.post(
            'https://www.nta.go.jp/cgi-bin/zeimusho/kensaku/kensakuprocess.php',
            data=data, headers=headers, timeout=10
        )
        text = resp.content.decode('utf-8', errors='replace')
        soup = BeautifulSoup(text, 'html.parser')
        full_text = soup.get_text()
        matches = re.findall(r'を管轄する税務署[\s\n]*([^\s電話\n]+)', full_text)
        if matches:
            return jsonify({'tax_office_name': matches[0]})
        else:
            return jsonify({'error': '税務署が見つかりませんでした。郵便番号を確認してください。'})
    except Exception as e:
        return jsonify({'error': f'国税庁サービスへの接続に失敗しました: {str(e)}'})


# ─────────────────────────────────────────────
# 税務年間カレンダー（全顧問先）
# ─────────────────────────────────────────────
@bp.route('/tax_calendar')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def tax_calendar():
    """全顧問先の税務年間カレンダー"""
    from app.tax_calendar import get_all_deadlines_for_client, group_by_month
    db = SessionLocal()
    try:
        tenant_id = session['tenant_id']
        profession = _get_profession(tenant_id)

        show_corporate = request.args.get('corporate', '1') == '1'
        show_individual = request.args.get('individual', '1') == '1'
        year = int(request.args.get('year', date.today().year))

        clients_q = db.query(TClient).filter(TClient.tenant_id == tenant_id).all()

        all_deadlines = []
        for client in clients_q:
            if client.type == '法人' and not show_corporate:
                continue
            if client.type == '個人' and not show_individual:
                continue
            deadlines = get_all_deadlines_for_client(client, year)
            all_deadlines.extend(deadlines)

        all_deadlines = [d for d in all_deadlines if d['date'].year == year]
        all_deadlines.sort(key=lambda x: x['date'])
        grouped = group_by_month(all_deadlines)

        today = date.today()
        return render_template('tax_calendar.html',
                               grouped=grouped,
                               year=year,
                               today=today,
                               show_corporate=show_corporate,
                               show_individual=show_individual,
                               profession=profession,
                               clients=clients_q)
    finally:
        db.close()


# ─────────────────────────────────────────────
# 税務年間カレンダー（顧問先個別）
# ─────────────────────────────────────────────
@bp.route('/<int:client_id>/tax_calendar')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def client_tax_calendar(client_id):
    """顧問先個別の税務年間カレンダー"""
    from app.tax_calendar import get_all_deadlines_for_client, group_by_month
    db = SessionLocal()
    try:
        tenant_id = session['tenant_id']
        profession = _get_profession(tenant_id)
        client = db.query(TClient).filter(
            TClient.id == client_id,
            TClient.tenant_id == tenant_id
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        year = int(request.args.get('year', date.today().year))
        show_corporate = request.args.get('corporate', '1') == '1'
        show_individual = request.args.get('individual', '1') == '1'

        deadlines = get_all_deadlines_for_client(client, year, db_session=db)
        deadlines = [d for d in deadlines if d['date'].year == year]
        deadlines.sort(key=lambda x: x['date'])
        grouped = group_by_month(deadlines)

        today = date.today()
        return render_template('client_tax_calendar.html',
                               client=client,
                               grouped=grouped,
                               year=year,
                               today=today,
                               show_corporate=show_corporate,
                               show_individual=show_individual,
                               profession=profession)
    finally:
        db.close()


# ========================================
# 納税実績
# ========================================
@bp.route('/<int:client_id>/tax_records')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def tax_records(client_id):
    """納税実績一覧ページ"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        recs = db.query(TTaxRecord).filter(
            TTaxRecord.client_id == client_id
        ).order_by(TTaxRecord.fiscal_year.desc(), TTaxRecord.fiscal_end_month.desc()).all()

        # 都道府県・市区町村を各レコードに付加
        for rec in recs:
            rec.prefectures = db.query(TTaxRecordPrefecture).filter(
                TTaxRecordPrefecture.tax_record_id == rec.id
            ).all()
            rec.municipalities = db.query(TTaxRecordMunicipality).filter(
                TTaxRecordMunicipality.tax_record_id == rec.id
            ).all()

        return render_template('client_tax_records.html', client=client, records=recs)
    finally:
        db.close()


@bp.route('/<int:client_id>/tax_records/add', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def add_tax_record(client_id):
    """納税実績追加"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        if request.method == 'POST':
            fiscal_year = request.form.get('fiscal_year', type=int)
            fiscal_end_month = request.form.get('fiscal_end_month', type=int)
            if not fiscal_year or not fiscal_end_month:
                flash('決算年度と決算月は必須です', 'error')
                return redirect(request.url)

            rec = TTaxRecord(
                client_id=client_id,
                fiscal_year=fiscal_year,
                fiscal_end_month=fiscal_end_month,
                corporate_tax=request.form.get('corporate_tax', type=int),
                local_corporate_tax=request.form.get('local_corporate_tax', type=int),
                consumption_tax=request.form.get('consumption_tax', type=int),
                local_consumption_tax=request.form.get('local_consumption_tax', type=int),
            )
            db.add(rec)
            db.flush()  # IDを取得

            # 都道府県
            pref_count = request.form.get('pref_count', type=int) or 0
            for i in range(pref_count):
                pref_name = request.form.get(f'pref_name_{i}', '').strip()
                if pref_name:
                    pref = TTaxRecordPrefecture(
                        tax_record_id=rec.id,
                        prefecture_name=pref_name,
                        equal_levy=request.form.get(f'pref_equal_{i}', type=int),
                        income_levy=request.form.get(f'pref_income_{i}', type=int),
                        business_tax=request.form.get(f'pref_business_{i}', type=int),
                        special_business_tax=request.form.get(f'pref_special_{i}', type=int),
                    )
                    db.add(pref)

            # 市区町村
            muni_count = request.form.get('muni_count', type=int) or 0
            for i in range(muni_count):
                muni_name = request.form.get(f'muni_name_{i}', '').strip()
                if muni_name:
                    muni = TTaxRecordMunicipality(
                        tax_record_id=rec.id,
                        municipality_name=muni_name,
                        equal_levy=request.form.get(f'muni_equal_{i}', type=int),
                        corporate_tax_levy=request.form.get(f'muni_corp_{i}', type=int),
                    )
                    db.add(muni)

            db.commit()
            flash(f'{fiscal_year}年{fiscal_end_month}月期の納税実績を追加しました', 'success')
            return redirect(url_for('clients.tax_records', client_id=client_id))

        # GET
        client_fiscal_month = int(client.fiscal_year_end or client.fiscal_year_end_month or 3)
        filing_prefectures = db.query(TFilingOfficePrefecture).filter(
            TFilingOfficePrefecture.client_id == client_id).all()
        filing_municipalities = db.query(TFilingOfficeMunicipality).filter(
            TFilingOfficeMunicipality.client_id == client_id).all()
        return render_template('client_tax_record_edit.html', client=client,
                               record=None, client_fiscal_month=client_fiscal_month,
                               filing_prefectures=filing_prefectures,
                               filing_municipalities=filing_municipalities,
                               enumerate=enumerate)
    finally:
        db.close()


@bp.route('/<int:client_id>/tax_records/<int:record_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def edit_tax_record(client_id, record_id):
    """納税実績編集"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            flash('顧問先が見つかりません', 'error')
            return redirect(url_for('clients.clients'))

        rec = db.query(TTaxRecord).filter(
            and_(TTaxRecord.id == record_id, TTaxRecord.client_id == client_id)
        ).first()
        if not rec:
            flash('納税実績が見つかりません', 'error')
            return redirect(url_for('clients.tax_records', client_id=client_id))

        if request.method == 'POST':
            rec.fiscal_year = request.form.get('fiscal_year', type=int)
            rec.fiscal_end_month = request.form.get('fiscal_end_month', type=int)
            rec.corporate_tax = request.form.get('corporate_tax', type=int)
            rec.local_corporate_tax = request.form.get('local_corporate_tax', type=int)
            rec.consumption_tax = request.form.get('consumption_tax', type=int)
            rec.local_consumption_tax = request.form.get('local_consumption_tax', type=int)
            rec.updated_at = datetime.utcnow()

            # 都道府県：既存を削除して再登録
            db.query(TTaxRecordPrefecture).filter(
                TTaxRecordPrefecture.tax_record_id == rec.id
            ).delete()
            pref_count = request.form.get('pref_count', type=int) or 0
            for i in range(pref_count):
                pref_name = request.form.get(f'pref_name_{i}', '').strip()
                if pref_name:
                    pref = TTaxRecordPrefecture(
                        tax_record_id=rec.id,
                        prefecture_name=pref_name,
                        equal_levy=request.form.get(f'pref_equal_{i}', type=int),
                        income_levy=request.form.get(f'pref_income_{i}', type=int),
                        business_tax=request.form.get(f'pref_business_{i}', type=int),
                        special_business_tax=request.form.get(f'pref_special_{i}', type=int),
                    )
                    db.add(pref)

            # 市区町村：既存を削除して再登録
            db.query(TTaxRecordMunicipality).filter(
                TTaxRecordMunicipality.tax_record_id == rec.id
            ).delete()
            muni_count = request.form.get('muni_count', type=int) or 0
            for i in range(muni_count):
                muni_name = request.form.get(f'muni_name_{i}', '').strip()
                if muni_name:
                    muni = TTaxRecordMunicipality(
                        tax_record_id=rec.id,
                        municipality_name=muni_name,
                        equal_levy=request.form.get(f'muni_equal_{i}', type=int),
                        corporate_tax_levy=request.form.get(f'muni_corp_{i}', type=int),
                    )
                    db.add(muni)

            db.commit()
            flash('納税実績を更新しました', 'success')
            return redirect(url_for('clients.tax_records', client_id=client_id))

        # GET
        rec.prefectures = db.query(TTaxRecordPrefecture).filter(
            TTaxRecordPrefecture.tax_record_id == rec.id
        ).all()
        rec.municipalities = db.query(TTaxRecordMunicipality).filter(
            TTaxRecordMunicipality.tax_record_id == rec.id
        ).all()
        client_fiscal_month = int(client.fiscal_year_end or client.fiscal_year_end_month or 3)
        filing_prefectures = db.query(TFilingOfficePrefecture).filter(
            TFilingOfficePrefecture.client_id == client_id).all()
        filing_municipalities = db.query(TFilingOfficeMunicipality).filter(
            TFilingOfficeMunicipality.client_id == client_id).all()
        return render_template('client_tax_record_edit.html', client=client,
                               record=rec, client_fiscal_month=client_fiscal_month,
                               filing_prefectures=filing_prefectures,
                               filing_municipalities=filing_municipalities,
                               enumerate=enumerate)
    finally:
        db.close()


@bp.route('/<int:client_id>/tax_records/<int:record_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def delete_tax_record(client_id, record_id):
    """納税実績削除"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))

    db = SessionLocal()
    try:
        rec = db.query(TTaxRecord).filter(
            and_(TTaxRecord.id == record_id, TTaxRecord.client_id == client_id)
        ).first()
        if rec:
            db.query(TTaxRecordPrefecture).filter(
                TTaxRecordPrefecture.tax_record_id == rec.id
            ).delete()
            db.query(TTaxRecordMunicipality).filter(
                TTaxRecordMunicipality.tax_record_id == rec.id
            ).delete()
            db.delete(rec)
            db.commit()
            flash('納税実績を削除しました', 'success')
        else:
            flash('納税実績が見つかりません', 'error')
        return redirect(url_for('clients.tax_records', client_id=client_id))
    finally:
        db.close()
