# ファイルを読み込む
with open('app/blueprints/tenant_admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 関数名を修正
replacements = [
    ("def admin_toggle_active(admin_id):", "def store_admin_toggle_active(admin_id):"),
    ("def admin_edit(admin_id):", "def store_admin_edit(admin_id):"),
    ("def admin_delete(admin_id):", "def store_admin_delete(admin_id):"),
    ("def toggle_admin_manage_permission(admin_id):", "def store_admin_toggle_manage_permission(admin_id):"),
]

for old, new in replacements:
    content = content.replace(old, new)

# ファイルに書き込む
with open('app/blueprints/tenant_admin.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("関数名を修正しました")
