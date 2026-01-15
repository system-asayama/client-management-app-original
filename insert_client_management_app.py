#!/usr/bin/env python3
"""
T_テナントアプリ設定に'client-management'を挿入するスクリプト
"""
from app import create_app
from app.models_login import TTenantAppSetting
from app.db import get_db

app = create_app()

with app.app_context():
    db = get_db()
    
    # 既存のレコードを確認
    existing = db.query(TTenantAppSetting).filter(
        TTenantAppSetting.tenant_id == 1,
        TTenantAppSetting.app_name == 'client-management'
    ).first()
    
    if existing:
        print(f"✅ Record already exists: tenant_id=1, app_name='client-management', enabled={existing.enabled}")
        if existing.enabled != 1:
            existing.enabled = 1
            db.commit()
            print("✅ Updated enabled to 1")
    else:
        # 新しいレコードを挿入
        new_setting = TTenantAppSetting(
            tenant_id=1,
            app_name='client-management',
            enabled=1
        )
        db.add(new_setting)
        db.commit()
        print("✅ Inserted new record: tenant_id=1, app_name='client-management', enabled=1")
    
    # 確認
    all_settings = db.query(TTenantAppSetting).all()
    print("\n現在のT_テナントアプリ設定:")
    for s in all_settings:
        print(f"  tenant_id={s.tenant_id}, app_name={s.app_name}, enabled={s.enabled}")
    
    db.close()
