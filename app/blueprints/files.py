"""
ファイル共有機能ブループリント
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
from app.db import SessionLocal
from app.utils.tenant_storage_adapter import get_storage_adapter
from app.utils.decorators import require_roles, ROLES
from app.models_clients import TClient, TFile
from sqlalchemy import and_

bp = Blueprint('files', __name__, url_prefix='/files')


@bp.route('/client/<int:client_id>', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def client_files(client_id):
    """顧問先ごとのファイル共有"""
    tenant_id = session.get('tenant_id')
    user_name = session.get('user_name', '匿名')
    
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
            f = request.files.get('file')
            subfolder = request.form.get('subfolder', '').strip()
            if f and f.filename:
                try:
                    adapter = get_storage_adapter(tenant_id)
                    client_folder = getattr(client, 'storage_folder_path', None)
                    file_url = adapter.upload(
                        f.stream, f.filename, client_id,
                        client_folder_path=client_folder,
                        subfolder=subfolder if subfolder else None
                    )
                    new_file = TFile(
                        client_id=client_id,
                        filename=f.filename,
                        file_url=file_url,
                        uploader=user_name,
                        timestamp=datetime.now()
                    )
                    db.add(new_file)
                    # ファイル共有通知をチャットに追加
                    from app.models_clients import TMessage
                    notify_msg = TMessage(
                        client_id=client_id,
                        sender=user_name,
                        sender_type='staff',
                        message=f'ファイルが共有されました: {f.filename}',
                        message_type='file_notify',
                        file_url=file_url,
                        file_name=f.filename,
                        timestamp=datetime.now()
                    )
                    db.add(notify_msg)
                    db.commit()
                    flash(f'ファイル「{f.filename}」をアップロードしました', 'success')
                except RuntimeError as e:
                    flash(f'エラー: {str(e)}', 'error')
                    if 'ストレージが設定されていません' in str(e):
                        flash('テナント管理画面でストレージ連携を設定してください', 'warning')
                except Exception as e:
                    flash(f'アップロードエラー: {str(e)}', 'error')
                    db.rollback()
                return redirect(url_for('files.client_files', client_id=client_id))
        
        files = db.query(TFile).filter(
            TFile.client_id == client_id
        ).order_by(TFile.timestamp.desc()).all()
        
        # ストレージが設定されている場合はフォルダ一覧を取得
        folders = []
        client_folder = getattr(client, 'storage_folder_path', None)
        storage_configured = False
        if client_folder:
            try:
                adapter = get_storage_adapter(tenant_id)
                folders = adapter.list_folders(client_folder)
                storage_configured = True
            except Exception:
                pass
        
        return render_template(
            'client_files.html',
            client=client,
            files=files,
            folders=folders,
            storage_configured=storage_configured
        )
        
    finally:
        db.close()


@bp.route('/client/<int:client_id>/folders', methods=['GET'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def list_folders(client_id):
    """フォルダ一覧をJSON形式で返す（Ajax用）"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'テナントが選択されていません'}), 403
    
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            return jsonify({'error': '顧問先が見つかりません'}), 404
        
        client_folder = getattr(client, 'storage_folder_path', None)
        if not client_folder:
            return jsonify({'folders': [], 'message': 'フォルダパスが設定されていません'})
        
        adapter = get_storage_adapter(tenant_id)
        folders = adapter.list_folders(client_folder)
        return jsonify({'folders': folders})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/client/<int:client_id>/folders/create', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def create_folder(client_id):
    """新しいフォルダを作成する（Ajax用）"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'テナントが選択されていません'}), 403
    
    folder_name = request.json.get('folder_name', '').strip() if request.is_json else request.form.get('folder_name', '').strip()
    if not folder_name:
        return jsonify({'error': 'フォルダ名を入力してください'}), 400
    
    db = SessionLocal()
    try:
        client = db.query(TClient).filter(
            and_(TClient.id == client_id, TClient.tenant_id == tenant_id)
        ).first()
        if not client:
            return jsonify({'error': '顧問先が見つかりません'}), 404
        
        client_folder = getattr(client, 'storage_folder_path', None)
        if not client_folder:
            return jsonify({'error': 'フォルダパスが設定されていません'}), 400
        
        adapter = get_storage_adapter(tenant_id)
        adapter.create_folder(client_folder, folder_name)
        return jsonify({'success': True, 'folder_name': folder_name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@bp.route('/client/folders/create_root', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"], ROLES["ADMIN"], ROLES["EMPLOYEE"])
def create_root_folder():
    """ストレージのルートに新しいフォルダを作成する（ストレージフォルダ設定ページ用）"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return jsonify({'error': 'テナントが選択されていません'}), 403

    folder_name = request.json.get('folder_name', '').strip() if request.is_json else request.form.get('folder_name', '').strip()
    if not folder_name:
        return jsonify({'error': 'フォルダ名を入力してください'}), 400

    try:
        adapter = get_storage_adapter(tenant_id)
        adapter.create_folder('/', folder_name)
        return jsonify({'success': True, 'folder_path': '/' + folder_name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
