# -*- coding: utf-8 -*-
"""
デバッグ用ルート
"""
from flask import Blueprint, jsonify
from app.utils.db import get_db, _is_pg

debug_bp = Blueprint('debug', __name__, url_prefix='/debug')

@debug_bp.route('/check_tables')
def check_tables():
    """データベーステーブルの存在確認"""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        if _is_pg(conn):
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)
        else:
            cur.execute("""
                SELECT name 
                FROM sqlite_master 
                WHERE type='table' 
                ORDER BY name
            """)
        
        tables = [row[0] for row in cur.fetchall()]
        
        return jsonify({
            'status': 'success',
            'total_tables': len(tables),
            'tables': tables,
            'has_message_table': 'T_メッセージ' in tables,
            'has_file_table': 'T_ファイル' in tables
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500
    finally:
        conn.close()
