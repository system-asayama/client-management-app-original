# ファイルを読み込む
with open('app/blueprints/tenant_admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

# /admins/ を /store_admins/ に変更（ただし /tenant_admins/ は除外）
replacements = [
    ("@bp.route('/admins/<int:admin_id>/toggle_active'", "@bp.route('/store_admins/<int:admin_id>/toggle_active'"),
    ("@bp.route('/admins/<int:admin_id>/edit'", "@bp.route('/store_admins/<int:admin_id>/edit'"),
    ("@bp.route('/admins/<int:admin_id>/delete'", "@bp.route('/store_admins/<int:admin_id>/delete'"),
    ("@bp.route('/admins/<int:admin_id>/toggle_manage_permission'", "@bp.route('/store_admins/<int:admin_id>/toggle_manage_permission'"),
]

for old, new in replacements:
    content = content.replace(old, new)

# ファイルに書き込む
with open('app/blueprints/tenant_admin.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("店舗管理者ルートを修正しました")
