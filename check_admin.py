import os
from app.db import SessionLocal
from app.models_login import TKanrisha, TKanrishaTenpo
from sqlalchemy import and_

db = SessionLocal()

try:
    # 店舗管理者（role=3）を取得
    admins = db.query(TKanrisha).filter(TKanrisha.role == 3).all()
    
    print("=== 店舗管理者一覧 ===")
    for admin in admins:
        print(f"ID: {admin.id}, ログインID: {admin.login_id}, 氏名: {admin.name}, テナントID: {admin.tenant_id}")
        
        # 所属店舗を取得
        store_relations = db.query(TKanrishaTenpo).filter(TKanrishaTenpo.admin_id == admin.id).all()
        if store_relations:
            print(f"  所属店舗ID: {[rel.store_id for rel in store_relations]}")
        else:
            print(f"  所属店舗: なし")
        print()
finally:
    db.close()
