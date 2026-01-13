"""
マイグレーション: T_テナント管理者_テナント中間テーブルの作成と既存データの移行

実行方法:
    python3 migrations/add_tenant_admin_tenant_table.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models_login import Base, TKanrisha, TTenantAdminTenant
from app.db import engine, SessionLocal

def migrate():
    """マイグレーション実行"""
    print("=== マイグレーション開始 ===")
    
    # 1. 中間テーブルを作成
    print("1. T_テナント管理者_テナントテーブルを作成...")
    TTenantAdminTenant.__table__.create(engine, checkfirst=True)
    print("   ✓ テーブル作成完了")
    
    # 2. 既存データを移行
    print("2. 既存のテナント管理者データを移行...")
    db = SessionLocal()
    try:
        # テナント管理者を取得 (role=2)
        tenant_admins = db.query(TKanrisha).filter(
            TKanrisha.role == 2,
            TKanrisha.tenant_id.isnot(None)
        ).all()
        
        migrated_count = 0
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
        
        db.commit()
        print(f"   ✓ {migrated_count}件のデータを移行完了")
        
    except Exception as e:
        db.rollback()
        print(f"   ✗ エラー: {e}")
        raise
    finally:
        db.close()
    
    print("=== マイグレーション完了 ===")

if __name__ == '__main__':
    migrate()
