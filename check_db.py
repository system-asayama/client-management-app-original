import os
from app.db import SessionLocal
from app.models_login import TKanrisha, TTenantAdminTenant, TTenant

db = SessionLocal()

print("=== テナント管理者一覧 ===")
admins = db.query(TKanrisha).filter(TKanrisha.role == 'tenant_admin').order_by(TKanrisha.id).all()
for admin in admins:
    print(f"ID: {admin.id}, ログインID: {admin.login_id}, 氏名: {admin.name}, tenant_id: {admin.tenant_id}, is_owner: {admin.is_owner}")

print("\n=== T_テナント管理者_テナント中間テーブル ===")
relations = db.query(TTenantAdminTenant).order_by(TTenantAdminTenant.admin_id, TTenantAdminTenant.tenant_id).all()
for rel in relations:
    tenant = db.query(TTenant).filter(TTenant.id == rel.tenant_id).first()
    admin = db.query(TKanrisha).filter(TKanrisha.id == rel.admin_id).first()
    print(f"admin_id: {rel.admin_id} ({admin.name if admin else '?'}), tenant_id: {rel.tenant_id} ({tenant.名称 if tenant else '?'}), is_owner: {rel.is_owner}")

db.close()
