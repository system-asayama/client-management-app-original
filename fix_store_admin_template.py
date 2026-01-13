# ファイルを読み込む
with open('app/templates/tenant_store_admins.html', 'r', encoding='utf-8') as f:
    content = f.read()

# リンクを修正
replacements = [
    ("url_for('tenant_admin.admin_new')", "url_for('tenant_admin.store_admin_new')"),
    ("url_for('tenant_admin.admin_edit'", "url_for('tenant_admin.store_admin_edit'"),
    ("url_for('tenant_admin.admin_delete'", "url_for('tenant_admin.store_admin_delete'"),
    ("url_for('tenant_admin.admin_toggle_active'", "url_for('tenant_admin.store_admin_toggle_active'"),
    ("url_for('tenant_admin.toggle_admin_manage_permission'", "url_for('tenant_admin.store_admin_toggle_manage_permission'"),
]

for old, new in replacements:
    content = content.replace(old, new)

# ファイルに書き込む
with open('app/templates/tenant_store_admins.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("tenant_store_admins.htmlのリンクを修正しました")
