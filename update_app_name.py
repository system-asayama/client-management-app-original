#!/usr/bin/env python3
"""
T_テナントアプリ設定のapp_nameを'顧問先管理'から'client-management'に更新するスクリプト
"""
from app import create_app
from app.models_login import TTenantAppSetting
from app.db import get_db

app = create_app()

with app.app_context():
    db = get_db()
    
    # '顧問先管理'を'client-management'に更新
    setting = db.query(TTenantAppSetting).filter(
        TTenantAppSetting.app_name == '顧問先管理'
    ).first()
    
    if setting:
        setting.app_name = 'client-management'
        db.commit()
        print(f"✅ Updated app_name from '顧問先管理' to 'client-management' for tenant_id={setting.tenant_id}")
    else:
        print("⚠️ No record found with app_name='顧問先管理'")
    
    # 確認
    all_settings = db.query(TTenantAppSetting).all()
    print("\n現在のT_テナントアプリ設定:")
    for s in all_settings:
        print(f"  tenant_id={s.tenant_id}, app_name={s.app_name}, enabled={s.enabled}")
    
    db.close()
