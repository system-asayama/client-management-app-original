# -*- coding: utf-8 -*-
"""VTUBER 運営アプリ Blueprint

VTUBER 事務所向け運営システム。所属タレント (VTUBER) 管理・配信スケジュール・
案件・収益・グッズ・ファンクラブを一元管理する。

URL prefix: /vtuber
ロール: SYSTEM_ADMIN / APP_MANAGER / TENANT_ADMIN / ADMIN / EMPLOYEE

スタータ実装:
  - /vtuber/             → ダッシュボード (主要 KPI と各機能への入口)
  - /vtuber/talents      → 所属 VTUBER 一覧 (プレースホルダ)
  - /vtuber/schedule     → 配信スケジュール (プレースホルダ)
  - /vtuber/projects     → 案件管理 (プレースホルダ)
  - /vtuber/revenue      → 収益管理 (プレースホルダ)

具体的なテーブル設計 / 入力フォーム / API は別 PR で順次追加していく。
このファイルは「アプリ一覧から開ける入口」を最小コストで通すための
スターター。
"""
from __future__ import annotations

from flask import Blueprint, render_template, session

from ..utils.decorators import require_roles, ROLES

bp = Blueprint('vtuber', __name__, url_prefix='/vtuber')

VTUBER_ROLES = (
    ROLES["SYSTEM_ADMIN"],
    ROLES["APP_MANAGER"],
    ROLES["TENANT_ADMIN"],
    ROLES["ADMIN"],
    ROLES["EMPLOYEE"],
)


@bp.route('/')
@require_roles(*VTUBER_ROLES)
def dashboard():
    """VTUBER 運営アプリのトップ。主要 KPI と各機能への入口。"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    # 将来: ここで「今月の配信時間合計」「案件数」「収益サマリ」等を集計して
    # テンプレに渡す。スターターでは静的なメニューだけ。
    return render_template(
        'vtuber/dashboard.html',
        user_id=user_id,
        tenant_id=tenant_id,
    )


@bp.route('/talents')
@require_roles(*VTUBER_ROLES)
def talents():
    """所属 VTUBER 一覧 (プレースホルダ)。"""
    return render_template('vtuber/talents.html')


@bp.route('/schedule')
@require_roles(*VTUBER_ROLES)
def schedule():
    """配信スケジュール (プレースホルダ)。"""
    return render_template('vtuber/schedule.html')


@bp.route('/projects')
@require_roles(*VTUBER_ROLES)
def projects():
    """案件管理 (プレースホルダ)。"""
    return render_template('vtuber/projects.html')


@bp.route('/revenue')
@require_roles(*VTUBER_ROLES)
def revenue():
    """収益管理 (プレースホルダ)。"""
    return render_template('vtuber/revenue.html')
