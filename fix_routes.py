import re

# ファイルを読み込む
with open('app/blueprints/tenant_admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. admin_new -> tenant_admin_new に変更
content = content.replace(
    "@bp.route('/admins/new', methods=['GET', 'POST'])\n@require_roles(ROLES[\"TENANT_ADMIN\"], ROLES[\"SYSTEM_ADMIN\"])\ndef admin_new():\n    \"\"\"管理者新規作成\"\"\"",
    "@bp.route('/tenant_admins/new', methods=['GET', 'POST'])\n@require_roles(ROLES[\"TENANT_ADMIN\"], ROLES[\"SYSTEM_ADMIN\"])\ndef tenant_admin_new():\n    \"\"\"テナント管理者新規作成\"\"\""
)

# 2. tenant_admin_new関数内のroleをTENANT_ADMINに変更（最初の1つだけ）
lines = content.split('\n')
in_tenant_admin_new = False
role_changed = False
for i, line in enumerate(lines):
    if 'def tenant_admin_new():' in line:
        in_tenant_admin_new = True
    elif in_tenant_admin_new and 'def ' in line and 'tenant_admin_new' not in line:
        in_tenant_admin_new = False
    elif in_tenant_admin_new and not role_changed and 'role=ROLES["ADMIN"],' in line:
        lines[i] = line.replace('role=ROLES["ADMIN"],', 'role=ROLES["TENANT_ADMIN"],')
        role_changed = True

content = '\n'.join(lines)

# 3. tenant_admin_new関数内のredirectをtenant_adminsに変更
content = re.sub(
    r"(def tenant_admin_new\(\):.*?)(return redirect\(url_for\('tenant_admin\.admins'\)\))",
    lambda m: m.group(0).replace("url_for('tenant_admin.admins')", "url_for('tenant_admin.tenant_admins')"),
    content,
    flags=re.DOTALL,
    count=1
)

# ファイルに書き込む
with open('app/blueprints/tenant_admin.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("tenant_admin_new関数を修正しました")
