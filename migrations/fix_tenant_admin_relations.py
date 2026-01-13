"""
中間テーブルのデータを修正するマイグレーション
浅山弘志さん（admin_id=13）をテストテナント（tenant_id=1）から削除
"""
import os
import sys

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models_login import TTenantAdminTenant, TKanrisha, TTenant

def main():
    db = SessionLocal()
    
    try:
        print("=== 修正前の中間テーブルデータ ===")
        relations = db.query(TTenantAdminTenant).order_by(
            TTenantAdminTenant.admin_id, 
            TTenantAdminTenant.tenant_id
        ).all()
        
        for rel in relations:
            admin = db.query(TKanrisha).filter(TKanrisha.id == rel.admin_id).first()
            tenant = db.query(TTenant).filter(TTenant.id == rel.tenant_id).first()
            print(f"admin_id: {rel.admin_id} ({admin.name if admin else '?'}), "
                  f"tenant_id: {rel.tenant_id} ({tenant.名称 if tenant else '?'}), "
                  f"is_owner: {rel.is_owner}")
        
        print("\n=== 浅山弘志さん（admin_id=13）をテストテナント（tenant_id=1）から削除 ===")
        deleted_count = db.query(TTenantAdminTenant).filter(
            TTenantAdminTenant.admin_id == 13,
            TTenantAdminTenant.tenant_id == 1
        ).delete()
        
        db.commit()
        print(f"削除したレコード数: {deleted_count}")
        
        print("\n=== 修正後の中間テーブルデータ ===")
        relations = db.query(TTenantAdminTenant).order_by(
            TTenantAdminTenant.admin_id, 
            TTenantAdminTenant.tenant_id
        ).all()
        
        for rel in relations:
            admin = db.query(TKanrisha).filter(TKanrisha.id == rel.admin_id).first()
            tenant = db.query(TTenant).filter(TTenant.id == rel.tenant_id).first()
            print(f"admin_id: {rel.admin_id} ({admin.name if admin else '?'}), "
                  f"tenant_id: {rel.tenant_id} ({tenant.名称 if tenant else '?'}), "
                  f"is_owner: {rel.is_owner}")
        
        print("\n✅ 修正完了")
        
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == '__main__':
    main()
