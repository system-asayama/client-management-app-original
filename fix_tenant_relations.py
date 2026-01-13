"""
中間テーブルのデータを修正するスクリプト
浅山弘志さん（admin_id=13）をテストテナント（tenant_id=1）から削除
"""
from app.db import SessionLocal
from app.models_login import TTenantAdminTenant

db = SessionLocal()

try:
    print("=== 修正前の中間テーブルデータ ===")
    relations = db.query(TTenantAdminTenant).order_by(TTenantAdminTenant.admin_id, TTenantAdminTenant.tenant_id).all()
    for rel in relations:
        print(f"admin_id: {rel.admin_id}, tenant_id: {rel.tenant_id}, is_owner: {rel.is_owner}")
    
    print("\n=== 浅山弘志さん（admin_id=13）をテストテナント（tenant_id=1）から削除 ===")
    deleted_count = db.query(TTenantAdminTenant).filter(
        TTenantAdminTenant.admin_id == 13,
        TTenantAdminTenant.tenant_id == 1
    ).delete()
    
    db.commit()
    print(f"削除したレコード数: {deleted_count}")
    
    print("\n=== 修正後の中間テーブルデータ ===")
    relations = db.query(TTenantAdminTenant).order_by(TTenantAdminTenant.admin_id, TTenantAdminTenant.tenant_id).all()
    for rel in relations:
        print(f"admin_id: {rel.admin_id}, tenant_id: {rel.tenant_id}, is_owner: {rel.is_owner}")
    
    print("\n✅ 修正完了")
except Exception as e:
    print(f"❌ エラー: {e}")
    db.rollback()
finally:
    db.close()
