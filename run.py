#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
開発サーバー起動スクリプト
"""

from app import create_app

if __name__ == '__main__':
    app = create_app()
    print("✅ 起動: .env最優先（override） / PostgreSQL → SQLite フォールバック ｜ 4ロール・ログイン専用")
    app.run(debug=True, host='0.0.0.0', port=5000)
