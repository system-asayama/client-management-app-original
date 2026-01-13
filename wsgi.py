from app import create_app

# Gunicorn から参照されるアプリケーション本体
app = create_app()
