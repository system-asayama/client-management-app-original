from app.db import SessionLocal
from app.models_login import TKanrisha, TTenantAdminTenant, TTenant

db = SessionLocal()

print("=== T_テナント管理者_テナント中間テーブル ===")
relations = db.query(TTenantAdminTenant).order_by(TTenantAdminTenant.admin_id, TTenantAdminTenant.tenant_id).all()
for rel in relations:
    tenant = db.query(TTenant).filter(TTenant.id == rel.tenant_id).first()
    admin = db.query(TKanrisha).filter(TKanrisha.id == rel.admin_id).first()
    print(f"admin_id: {rel.admin_id} ({admin.name if admin else '?'}), tenant_id: {rel.tenant_id} ({tenant.名称 if tenant else '?'}), is_owner: {rel.is_owner}")

print("\n=== 税理士法人OKS (tenant_id=2) の管理者 ===")
relations = db.query(TTenantAdminTenant).filter(TTenantAdminTenant.tenant_id == 2).all()
for rel in relations:
    admin = db.query(TKanrisha).filter(TKanrisha.id == rel.admin_id).first()
    if admin:
        print(f"admin_id: {rel.admin_id}, name: {admin.name}, role: {admin.role}, is_owner: {rel.is_owner}")

db.close()
