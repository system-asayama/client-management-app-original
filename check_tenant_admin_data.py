import os
import sys

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models_login import TKanrisha, TTenantAdminTenant, TTenant

db = SessionLocal()

try:
    print("=== T_管理者 テーブル ===")
    admins = db.query(TKanrisha).filter(TKanrisha.role == 2).all()
    for admin in admins:
        print(f"ID: {admin.id}, ログインID: {admin.login_id}, 氏名: {admin.name}, tenant_id: {admin.tenant_id}")
    
    print("\n=== T_テナント管理者_テナント 中間テーブル ===")
    relations = db.query(TTenantAdminTenant).all()
    for rel in relations:
        print(f"admin_id: {rel.admin_id}, tenant_id: {rel.tenant_id}, is_owner: {rel.is_owner}")
    
    print("\n=== T_テナント テーブル ===")
    tenants = db.query(TTenant).all()
    for tenant in tenants:
        print(f"ID: {tenant.id}, 名称: {tenant['名称']}")
    
finally:
    db.close()
