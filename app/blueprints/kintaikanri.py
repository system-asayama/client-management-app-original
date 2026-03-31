"""
勤怠管理システム blueprint

スタッフGPS勤怠管理アプリへのポータルページを提供します。
"""
from flask import Blueprint, render_template, session, redirect, url_for

bp = Blueprint('kintaikanri', __name__, url_prefix='/kintaikanri')


@bp.route('/')
@bp.route('')
def index():
    """勤怠管理システム トップページ"""
    # ログイン済みかチェック
    if not session.get('user_id') and not session.get('staff_id'):
        return redirect(url_for('auth.login'))

    return render_template('kintaikanri_index.html')
