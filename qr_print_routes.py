"""QRコード印刷ページのルート"""
from flask import render_template, g
from app.utils.decorators import require_roles, ROLES
import store_db

def register_qr_print_routes(app):
    """QRコード印刷ページのルートを登録"""
    
    @app.route('/admin/store/<int:store_id>/qr_print')
    @require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
    def qr_print(store_id):
        """QRコード印刷ページ（3つのバージョン）"""
        from flask import session
        from app.utils.db import get_db_connection, _sql
        
        tenant_id = session.get('tenant_id')
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 店舗情報を取得
        cur.execute(_sql(conn, 'SELECT id, 名称, slug FROM "T_店舗" WHERE id = %s AND tenant_id = %s'), 
                   (store_id, tenant_id))
        store_row = cur.fetchone()
        conn.close()
        
        if not store_row:
            return "店舗が見つかりません", 404
        
        store = {
            'id': store_row[0],
            'name': store_row[1],
            'slug': store_row[2]
        }
        
        # アンケートページのURL
        from flask import request
        base_url = request.url_root.rstrip('/')
        survey_url = f"{base_url}/store/{store['slug']}"
        
        return render_template('qr_print.html', store=store, survey_url=survey_url)
