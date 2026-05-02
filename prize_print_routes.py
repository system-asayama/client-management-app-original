"""景品一覧印刷ページのルート"""
from flask import render_template, session
from app.utils.decorators import require_roles, ROLES
from app.utils.db import get_db_connection, _sql
import json

def register_prize_print_routes(app):
    """景品一覧印刷ページのルートを登録"""
    
    @app.route('/admin/store/<int:store_id>/print_prizes')
    @require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
    def prize_print(store_id):
        """景品一覧印刷ページ"""
        try:
            print(f"[DEBUG] prize_print: store_id={store_id}")
            tenant_id = session.get('tenant_id')
            conn = get_db_connection()
            cur = conn.cursor()
            
            # 店舗情報を取得
            cur.execute(_sql(conn, 'SELECT id, 名称, slug FROM "T_店舗" WHERE id = %s AND tenant_id = %s'), 
                       (store_id, tenant_id))
            store_row = cur.fetchone()
            print(f"[DEBUG] prize_print: store_row={store_row}")
            
            if not store_row:
                conn.close()
                return "店舗が見つかりません", 404
            
            store = {
                'id': store_row[0],
                'name': store_row[1],
                'slug': store_row[2]
            }
            
            # 景品設定を取得
            cur.execute(_sql(conn, 'SELECT prizes_json FROM "T_店舗_景品設定" WHERE store_id = %s'), (store_id,))
            prizes_row = cur.fetchone()
            print(f"[DEBUG] prize_print: prizes_row={prizes_row}")
            
            if prizes_row and prizes_row[0]:
                try:
                    prizes = json.loads(prizes_row[0])
                    print(f"[DEBUG] prize_print: prizes loaded from DB, count={len(prizes)}")
                except Exception as e:
                    print(f"[ERROR] prize_print: JSON parse error: {e}")
                    prizes = []
            else:
                prizes = [
                    {"min_score": 500, "rank": "🎁 特賞", "name": "特別景品"},
                    {"min_score": 250, "max_score": 499, "rank": "🏆 1等", "name": "1等景品"},
                    {"min_score": 150, "max_score": 249, "rank": "🥈 2等", "name": "2等景品"},
                    {"min_score": 100, "max_score": 149, "rank": "🥉 3等", "name": "3等景品"},
                    {"min_score": 0, "max_score": 99, "rank": "🎊 参加賞", "name": "参加賞"}
                ]
                print(f"[DEBUG] prize_print: using default prizes")
            
            conn.close()
            print(f"[DEBUG] prize_print: rendering template")
            
            return render_template('print_prizes.html', store=store, prizes=prizes)
        except Exception as e:
            print(f"[ERROR] prize_print: {e}")
            import traceback
            traceback.print_exc()
            return f"Error: {e}", 500
