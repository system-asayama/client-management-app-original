# -*- coding: utf-8 -*-
"""
財務管理（準備中）
"""

from flask import Blueprint, render_template, session
from ..utils.decorators import ROLES, require_roles

bp = Blueprint('finance', __name__, url_prefix='/finance')


@bp.route('/')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"], ROLES["APP_MANAGER"])
def index():
    """財務管理トップ（準備中）"""
    tenant_id = session.get('tenant_id')
    return render_template('finance_coming_soon.html', tenant_id=tenant_id)
