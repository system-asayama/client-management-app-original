import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
new_url = 'https://files.manuscdn.com/user_upload_by_module/session_file/310519663249566547/KsbkXMEuLVJtlUaq.apk'
new_ver = 'v1.0.2'
cur.execute("UPDATE t_テナント SET android_apk_url = %s, android_apk_version = %s", (new_url, new_ver))
conn.commit()
print('Updated rows:', cur.rowcount)
conn.close()
print('Done')
