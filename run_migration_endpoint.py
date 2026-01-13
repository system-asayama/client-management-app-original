"""
一時的なマイグレーション実行エンドポイント
使用後は削除すること
"""
from flask import Blueprint, jsonify
from app.database import SessionLocal
from app.models_login import TKanrisha, TTenantAdminTenant

bp = Blueprint('migration', __name__)

@bp.route('/run-migration-temp-12345')
def run_migration():
    """マイグレーション実行（一時エンドポイント）"""
    db = SessionLocal()
    try:
        # テナント管理者を取得 (role=2)
        tenant_admins = db.query(TKanrisha).filter(
            TKanrisha.role == 2,
            TKanrisha.tenant_id.isnot(None)
        ).all()
        
        migrated_count = 0
        results = []
        
        for admin in tenant_admins:
            # 既に中間テーブルにデータがあるかチェック
            existing = db.query(TTenantAdminTenant).filter(
                TTenantAdminTenant.admin_id == admin.id,
                TTenantAdminTenant.tenant_id == admin.tenant_id
            ).first()
            
            if not existing:
                # 中間テーブルにデータを追加
                relation = TTenantAdminTenant(
                    admin_id=admin.id,
                    tenant_id=admin.tenant_id,
                    is_owner=admin.is_owner if admin.is_owner else 0
                )
                db.add(relation)
                migrated_count += 1
                results.append(f"Migrated: admin_id={admin.id}, tenant_id={admin.tenant_id}, is_owner={admin.is_owner}")
            else:
                results.append(f"Already exists: admin_id={admin.id}, tenant_id={admin.tenant_id}")
        
        db.commit()
        
        return jsonify({
            'status': 'success',
            'migrated_count': migrated_count,
            'total_admins': len(tenant_admins),
            'details': results
        })
        
    except Exception as e:
        db.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        db.close()
