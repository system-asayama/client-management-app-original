# -*- coding: utf-8 -*-
"""
従業員マイページ（SQLAlchemy版）
"""

from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import SessionLocal
from app.models_login import TJugyoin, TTenant, TTenpo, TJugyoinTenpo, TTenpoAppSetting, TTenantAppSetting
from app.models_truck import TruckDriver
from sqlalchemy import func, and_, or_
from ..utils.decorators import ROLES
from ..utils.decorators import require_roles

bp = Blueprint('employee', __name__, url_prefix='/employee')


@bp.route('/dashboard')
@require_roles(ROLES["EMPLOYEE"], ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def dashboard():
    """従業員ダッシュボード → マイページにリダイレクト"""
    return redirect(url_for('employee.mypage'))


@bp.route('/driver_mypage')
@require_roles(ROLES["EMPLOYEE"], ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def driver_mypage():
    """従業員からドライバーマイページへ自動ログイン中継"""
    user_id = session.get('user_id')
    db = SessionLocal()
    try:
        employee = db.query(TJugyoin).filter(TJugyoin.id == user_id).first()
        if not employee:
            flash('ユーザー情報が見つかりません', 'error')
            return redirect(url_for('employee.mypage'))
        # 従業員のlogin_idと同じlogin_idを持つTruckDriverを検索
        driver = db.query(TruckDriver).filter(
            TruckDriver.login_id == employee.login_id,
            TruckDriver.active == True
        ).first()
        if not driver:
            flash('ドライバーとして登録されていません。管理者にお問い合わせください。', 'warning')
            return redirect(url_for('employee.mypage'))
        # ドライバーセッションをセット（再ログイン不要）
        session['truck_driver_id'] = driver.id
        session['truck_driver_name'] = driver.name
        return redirect(url_for('truck.driver_dashboard'))
    finally:
        db.close()


@bp.route('/mypage', methods=['GET', 'POST'])
@require_roles(ROLES["EMPLOYEE"], ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def mypage():
    """従業員マイページ"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # ユーザー情報を取得
        employee = db.query(TJugyoin).filter(TJugyoin.id == user_id).first()
        
        if not employee:
            flash('ユーザー情報が見つかりません', 'error')
            return redirect(url_for('employee.dashboard'))
        
        user = {
            'id': employee.id,
            'login_id': employee.login_id,
            'name': employee.name,
            'email': employee.email,
            'created_at': employee.created_at,
            'updated_at': employee.updated_at
        }
        
        # テナント名を取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        tenant_name = tenant_obj.名称 if tenant_obj else '不明'
        
        # 所属店舗を取得
        store_relations = db.query(TJugyoinTenpo).filter(
            TJugyoinTenpo.employee_id == user_id
        ).all()
        
        stores = []
        store_list = []
        for rel in store_relations:
            store = db.query(TTenpo).filter(TTenpo.id == rel.store_id).first()
            if store:
                stores.append(store.名称)
                store_list.append({'id': store.id, 'name': store.名称})
        
        # POSTリクエスト（プロフィール編集またはパスワード変更）
        if request.method == 'POST':
            action = request.form.get('action', '')
            
            if action == 'update_profile':
                # プロフィール編集
                login_id = request.form.get('login_id', '').strip()
                name = request.form.get('name', '').strip()
                email = request.form.get('email', '').strip()
                
                if not login_id or not name:
                    flash('ログインIDと氏名は必須です', 'error')
                    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
                
                # ログインID重複チェック（自分以外）
                existing = db.query(TJugyoin).filter(
                    and_(TJugyoin.login_id == login_id, TJugyoin.id != user_id)
                ).first()
                if existing:
                    flash('このログインIDは既に使用されています', 'error')
                    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
                
                # プロフィール更新
                employee.login_id = login_id
                employee.name = name
                employee.email = email
                db.commit()
                
                flash('プロフィールを更新しました', 'success')
                return redirect(url_for('employee.mypage'))
            
            elif action == 'change_password':
                # パスワード変更
                current_password = request.form.get('current_password', '')
                new_password = request.form.get('new_password', '')
                confirm_password = request.form.get('confirm_password', '')
                
                if not current_password or not new_password or not confirm_password:
                    flash('全ての項目を入力してください', 'error')
                    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
                
                # 現在のパスワードを確認
                if not employee.password_hash or not check_password_hash(employee.password_hash, current_password):
                    flash('現在のパスワードが正しくありません', 'error')
                    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
                
                # 新しいパスワードの確認
                if new_password != confirm_password:
                    flash('新しいパスワードが一致しません', 'error')
                    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
                
                if len(new_password) < 8:
                    flash('パスワードは8文字以上にしてください', 'error')
                    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
                
                # パスワード更新
                employee.password_hash = generate_password_hash(new_password)
                db.commit()
                
                flash('パスワードを変更しました', 'success')
                return redirect(url_for('employee.mypage'))
            
            elif action == 'select_store':
                # 店舗選択
                store_id = request.form.get('store_id', type=int)
                if store_id:
                    # 選択した店舗が自分の所属店舗かチェック
                    relation = db.query(TJugyoinTenpo).filter(
                        and_(
                            TJugyoinTenpo.employee_id == user_id,
                            TJugyoinTenpo.store_id == store_id
                        )
                    ).first()
                    
                    if relation:
                        session['store_id'] = store_id
                        flash('店舗を選択しました', 'success')
                    else:
                        flash('指定された店舗にアクセスする権限がありません', 'error')
                
                return redirect(url_for('employee.mypage'))
        
        # ドライバー登録チェック（同じlogin_idのTruckDriverが存在するか）
        is_driver = db.query(TruckDriver).filter(
            TruckDriver.login_id == employee.login_id,
            TruckDriver.active == True
        ).first() is not None

        return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list, is_driver=is_driver)
    finally:
        db.close()


@bp.route('/profile')
@require_roles(ROLES["EMPLOYEE"], ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def profile():
    """従業員プロフィール表示"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # ユーザー情報を取得
        employee = db.query(TJugyoin).filter(TJugyoin.id == user_id).first()
        
        if not employee:
            flash('ユーザー情報が見つかりません', 'error')
            return redirect(url_for('employee.dashboard'))
        
        user = {
            'id': employee.id,
            'login_id': employee.login_id,
            'name': employee.name,
            'email': employee.email,
            'created_at': employee.created_at,
            'updated_at': employee.updated_at
        }
        
        # テナント名を取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        tenant_name = tenant_obj.名称 if tenant_obj else '不明'
        
        # 所属店舗を取得
        store_relations = db.query(TJugyoinTenpo).filter(
            TJugyoinTenpo.employee_id == user_id
        ).all()
        
        stores = []
        for rel in store_relations:
            store = db.query(TTenpo).filter(TTenpo.id == rel.store_id).first()
            if store:
                stores.append(store.名称)
        
        return render_template('employee_profile.html', user=user, tenant_name=tenant_name, stores=stores)
    finally:
        db.close()


@bp.route('/mypage/profile', methods=['GET', 'POST'])
@require_roles(ROLES["EMPLOYEE"], ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"])
def mypage_profile():
    """従業員プロフィール設定ページ"""
    from sqlalchemy import func as sqlfunc
    user_id = session.get('user_id')
    db = SessionLocal()
    try:
        employee = db.query(TJugyoin).filter(TJugyoin.id == user_id).first()
        if not employee:
            flash('ユーザー情報が見つかりません', 'error')
            return redirect(url_for('employee.mypage'))

        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'update_profile':
                login_id = request.form.get('login_id', '').strip()
                name = request.form.get('name', '').strip()
                email = request.form.get('email', '').strip() or None
                if not login_id or not name:
                    flash('ログインIDと氏名は必須です', 'error')
                else:
                    # ログインID重複チェック（自分以外）
                    from sqlalchemy import and_
                    existing = db.query(TJugyoin).filter(
                        and_(TJugyoin.login_id == login_id, TJugyoin.id != user_id)
                    ).first()
                    if existing:
                        flash('このログインIDは既に使用されています', 'error')
                    else:
                        employee.login_id = login_id
                        employee.name = name
                        employee.email = email
                        if hasattr(employee, 'updated_at'):
                            employee.updated_at = sqlfunc.now()
                        db.commit()
                        flash('プロフィール情報を更新しました', 'success')
                        return redirect(url_for('employee.mypage_profile'))
            elif action == 'change_password':
                current_password = request.form.get('current_password', '').strip()
                new_password = request.form.get('new_password', '').strip()
                new_password_confirm = request.form.get('new_password_confirm', '').strip()
                if new_password != new_password_confirm:
                    flash('パスワードが一致しません', 'error')
                elif not employee.password_hash or not check_password_hash(employee.password_hash, current_password):
                    flash('現在のパスワードが正しくありません', 'error')
                elif len(new_password) < 8:
                    flash('パスワードは8文字以上にしてください', 'error')
                else:
                    employee.password_hash = generate_password_hash(new_password)
                    if hasattr(employee, 'updated_at'):
                        employee.updated_at = sqlfunc.now()
                    db.commit()
                    flash('パスワードを変更しました', 'success')
                    return redirect(url_for('employee.mypage_profile'))

        user = {
            'id': employee.id,
            'login_id': employee.login_id,
            'name': employee.name,
            'email': getattr(employee, 'email', None),
        }
        return render_template('employee_mypage_profile.html', user=user)
    finally:
        db.close()
