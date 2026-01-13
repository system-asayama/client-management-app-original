"""
マイグレーション用エンドポイント（本番環境でのみ使用）
"""

from flask import Blueprint, jsonify
from ..utils.db import get_db_connection

bp = Blueprint('migrate', __name__, url_prefix='/migrate')


@bp.route('/add_openai_key')
def add_openai_key():
    """openai_api_keyカラムを追加するマイグレーション"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # PostgreSQLかどうか確認
        is_pg = conn.__class__.__module__.startswith("psycopg2")
        
        if not is_pg:
            return jsonify({
                'status': 'error',
                'message': 'このマイグレーションはPostgreSQLのみ対応しています'
            }), 400
        
        # openai_api_keyカラムが存在するか確認
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'T_管理者' AND column_name = 'openai_api_key'
        """)
        
        if cur.fetchone():
            conn.close()
            return jsonify({
                'status': 'success',
                'message': 'openai_api_keyカラムは既に存在します'
            })
        
        # openai_api_keyカラムを追加
        cur.execute('''
            ALTER TABLE "T_管理者" 
            ADD COLUMN openai_api_key TEXT
        ''')
        
        conn.close()
        
        return jsonify({
            'status': 'success',
            'message': 'openai_api_keyカラムを追加しました'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'マイグレーション失敗: {str(e)}'
        }), 500



@bp.route('/init_all_tables')
def init_all_tables():
    """すべてのテーブルを作成するマイグレーション"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # PostgreSQLかどうか確認
        is_pg = conn.__class__.__module__.startswith("psycopg2")
        
        if not is_pg:
            return jsonify({
                'status': 'error',
                'message': 'このマイグレーションはPostgreSQLのみ対応しています'
            }), 400
        
        # init_schema()関数を呼び出してすべてのテーブルを作成
        from ..utils.db import init_schema
        init_schema(conn)
        
        conn.close()
        
        return jsonify({
            'status': 'success',
            'message': 'すべてのテーブルを作成しました'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'マイグレーション失敗: {str(e)}'
        }), 500


@bp.route('/add_admin_columns')
def add_admin_columns():
    """T_管理者テーブルにis_ownerとcan_manage_adminsカラムを追加"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # PostgreSQLかどうか確認
        is_pg = conn.__class__.__module__.startswith("psycopg2")
        
        if not is_pg:
            return jsonify({
                'status': 'error',
                'message': 'このマイグレーションはPostgreSQLのみ対応しています'
            }), 400
        
        # is_ownerカラムを追加
        cur.execute('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='T_管理者' AND column_name='is_owner'
        ''')
        if not cur.fetchone():
            cur.execute('ALTER TABLE "T_管理者" ADD COLUMN is_owner INTEGER DEFAULT 0')
            conn.commit()
        
        # can_manage_adminsカラムを追加
        cur.execute('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='T_管理者' AND column_name='can_manage_admins'
        ''')
        if not cur.fetchone():
            cur.execute('ALTER TABLE "T_管理者" ADD COLUMN can_manage_admins INTEGER DEFAULT 0')
            conn.commit()
        
        conn.close()
        
        return jsonify({
            'status': 'success',
            'message': 'is_ownerとcan_manage_adminsカラムを追加しました'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'マイグレーション失敗: {str(e)}'
        }), 500
