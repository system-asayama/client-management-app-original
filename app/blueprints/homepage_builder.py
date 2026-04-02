"""
ホームページ制作アプリ blueprint

テナント単位でホームページのコンテンツを管理・編集・プレビューするアプリ。
/homepage/ 配下のすべてのルートを管理します。
"""
import json
from flask import (
    Blueprint, render_template, session, redirect, url_for,
    flash, request, jsonify, Response
)
from sqlalchemy import and_
from datetime import datetime

from app.db import SessionLocal
from app.models_login import TTenant
from app.models_homepage import THomepageSite, THomepageSection
from app.utils.decorators import require_roles, ROLES

bp = Blueprint('homepage_builder', __name__, url_prefix='/homepage')

# ─────────────────────────────────────────────
# セクション種別の定義
# ─────────────────────────────────────────────
SECTION_TYPES = [
    {'key': 'hero',     'label': 'ヒーロー（メインビジュアル）', 'icon': '🖼️'},
    {'key': 'about',    'label': '事務所紹介',                   'icon': '🏢'},
    {'key': 'services', 'label': 'サービス・業務内容',           'icon': '📋'},
    {'key': 'features', 'label': '特徴・強み',                   'icon': '⭐'},
    {'key': 'staff',    'label': 'スタッフ紹介',                 'icon': '👥'},
    {'key': 'news',     'label': 'お知らせ',                     'icon': '📰'},
    {'key': 'faq',      'label': 'よくある質問',                 'icon': '❓'},
    {'key': 'contact',  'label': 'お問い合わせ',                 'icon': '📧'},
    {'key': 'footer',   'label': 'フッター',                     'icon': '📌'},
    {'key': 'custom',   'label': 'カスタムセクション',           'icon': '✏️'},
]

SECTION_TYPE_MAP = {s['key']: s for s in SECTION_TYPES}


def _get_or_create_site(db, tenant_id):
    """テナントのサイト設定を取得または作成する"""
    site = db.query(THomepageSite).filter(
        THomepageSite.tenant_id == tenant_id
    ).first()
    if not site:
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        site_name = tenant.名称 if tenant else 'ホームページ'
        site = THomepageSite(
            tenant_id=tenant_id,
            site_name=site_name,
            primary_color='#2563a8',
            secondary_color='#1a3a5c',
            font_family='Noto Sans JP',
        )
        db.add(site)
        db.commit()
        db.refresh(site)
        # デフォルトセクションを作成
        default_sections = [
            THomepageSection(
                site_id=site.id, tenant_id=tenant_id,
                section_type='hero', title='ようこそ', subtitle='専門家があなたをサポートします',
                body='お気軽にご相談ください。', button_text='お問い合わせ', button_url='#contact',
                sort_order=1, visible=1
            ),
            THomepageSection(
                site_id=site.id, tenant_id=tenant_id,
                section_type='about', title='事務所紹介',
                body='私たちは長年の経験と専門知識を活かし、お客様の課題解決をサポートします。',
                sort_order=2, visible=1
            ),
            THomepageSection(
                site_id=site.id, tenant_id=tenant_id,
                section_type='services', title='サービス内容',
                body='税務申告・会計・経営コンサルティングなど幅広いサービスを提供しています。',
                sort_order=3, visible=1
            ),
            THomepageSection(
                site_id=site.id, tenant_id=tenant_id,
                section_type='contact', title='お問い合わせ',
                body='ご質問・ご相談はお気軽にお問い合わせください。',
                sort_order=4, visible=1
            ),
            THomepageSection(
                site_id=site.id, tenant_id=tenant_id,
                section_type='footer', title='',
                body='© 2025 All Rights Reserved.',
                sort_order=99, visible=1
            ),
        ]
        for s in default_sections:
            db.add(s)
        db.commit()
    return site


# ─────────────────────────────────────────────
# ダッシュボード
# ─────────────────────────────────────────────
@bp.route('/')
@bp.route('')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def index():
    """ホームページ制作アプリ トップ"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        site = _get_or_create_site(db, tenant_id)
        sections = db.query(THomepageSection).filter(
            THomepageSection.site_id == site.id
        ).order_by(THomepageSection.sort_order.asc()).all()
        return render_template(
            'homepage_builder_index.html',
            site=site,
            sections=sections,
            section_types=SECTION_TYPES,
            section_type_map=SECTION_TYPE_MAP,
        )
    finally:
        db.close()


# ─────────────────────────────────────────────
# サイト設定編集
# ─────────────────────────────────────────────
@bp.route('/settings', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def settings():
    """サイト全体設定の編集"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        site = _get_or_create_site(db, tenant_id)
        if request.method == 'POST':
            site.site_name = request.form.get('site_name', '').strip() or site.site_name
            site.site_tagline = request.form.get('site_tagline', '').strip()
            site.site_description = request.form.get('site_description', '').strip()
            site.logo_url = request.form.get('logo_url', '').strip()
            site.primary_color = request.form.get('primary_color', '#2563a8').strip()
            site.secondary_color = request.form.get('secondary_color', '#1a3a5c').strip()
            site.font_family = request.form.get('font_family', 'Noto Sans JP').strip()
            db.commit()
            flash('サイト設定を保存しました', 'success')
            return redirect(url_for('homepage_builder.index'))
        return render_template('homepage_builder_settings.html', site=site)
    finally:
        db.close()


# ─────────────────────────────────────────────
# セクション追加
# ─────────────────────────────────────────────
@bp.route('/section/add', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def section_add():
    """新しいセクションを追加する"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        site = _get_or_create_site(db, tenant_id)
        if request.method == 'POST':
            section_type = request.form.get('section_type', 'custom')
            # 現在の最大sort_orderを取得
            max_order_row = db.query(THomepageSection).filter(
                THomepageSection.site_id == site.id
            ).order_by(THomepageSection.sort_order.desc()).first()
            next_order = (max_order_row.sort_order + 1) if max_order_row else 1
            section = THomepageSection(
                site_id=site.id,
                tenant_id=tenant_id,
                section_type=section_type,
                title=request.form.get('title', '').strip(),
                subtitle=request.form.get('subtitle', '').strip(),
                body=request.form.get('body', '').strip(),
                image_url=request.form.get('image_url', '').strip(),
                button_text=request.form.get('button_text', '').strip(),
                button_url=request.form.get('button_url', '').strip(),
                sort_order=next_order,
                visible=1,
            )
            db.add(section)
            db.commit()
            flash('セクションを追加しました', 'success')
            return redirect(url_for('homepage_builder.index'))
        # GETの場合：section_typeをクエリパラメータから取得
        selected_type = request.args.get('type', 'custom')
        return render_template(
            'homepage_builder_section_form.html',
            site=site,
            section=None,
            section_types=SECTION_TYPES,
            selected_type=selected_type,
            form_action=url_for('homepage_builder.section_add'),
            page_title='セクションを追加',
        )
    finally:
        db.close()


# ─────────────────────────────────────────────
# セクション編集
# ─────────────────────────────────────────────
@bp.route('/section/<int:section_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def section_edit(section_id):
    """セクションを編集する"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        section = db.query(THomepageSection).filter(
            and_(THomepageSection.id == section_id, THomepageSection.tenant_id == tenant_id)
        ).first()
        if not section:
            flash('セクションが見つかりません', 'error')
            return redirect(url_for('homepage_builder.index'))
        site = db.query(THomepageSite).filter(THomepageSite.id == section.site_id).first()
        if request.method == 'POST':
            section.title = request.form.get('title', '').strip()
            section.subtitle = request.form.get('subtitle', '').strip()
            section.body = request.form.get('body', '').strip()
            section.image_url = request.form.get('image_url', '').strip()
            section.button_text = request.form.get('button_text', '').strip()
            section.button_url = request.form.get('button_url', '').strip()
            section.visible = 1 if request.form.get('visible') else 0
            db.commit()
            flash('セクションを保存しました', 'success')
            return redirect(url_for('homepage_builder.index'))
        return render_template(
            'homepage_builder_section_form.html',
            site=site,
            section=section,
            section_types=SECTION_TYPES,
            selected_type=section.section_type,
            form_action=url_for('homepage_builder.section_edit', section_id=section_id),
            page_title='セクションを編集',
        )
    finally:
        db.close()


# ─────────────────────────────────────────────
# セクション削除
# ─────────────────────────────────────────────
@bp.route('/section/<int:section_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def section_delete(section_id):
    """セクションを削除する"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        section = db.query(THomepageSection).filter(
            and_(THomepageSection.id == section_id, THomepageSection.tenant_id == tenant_id)
        ).first()
        if section:
            db.delete(section)
            db.commit()
            flash('セクションを削除しました', 'success')
        else:
            flash('セクションが見つかりません', 'error')
        return redirect(url_for('homepage_builder.index'))
    finally:
        db.close()


# ─────────────────────────────────────────────
# セクション表示/非表示切り替え（Ajax）
# ─────────────────────────────────────────────
@bp.route('/section/<int:section_id>/toggle', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def section_toggle(section_id):
    """セクションの表示/非表示を切り替える"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        section = db.query(THomepageSection).filter(
            and_(THomepageSection.id == section_id, THomepageSection.tenant_id == tenant_id)
        ).first()
        if not section:
            return jsonify({'ok': False, 'error': 'not found'}), 404
        section.visible = 0 if section.visible else 1
        db.commit()
        return jsonify({'ok': True, 'visible': section.visible})
    finally:
        db.close()


# ─────────────────────────────────────────────
# セクション並び順更新（Ajax）
# ─────────────────────────────────────────────
@bp.route('/section/reorder', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def section_reorder():
    """セクションの並び順を更新する"""
    tenant_id = session.get('tenant_id')
    data = request.get_json(silent=True) or {}
    order_list = data.get('order', [])  # [{id: 1, sort_order: 1}, ...]
    db = SessionLocal()
    try:
        for item in order_list:
            section = db.query(THomepageSection).filter(
                and_(THomepageSection.id == item['id'], THomepageSection.tenant_id == tenant_id)
            ).first()
            if section:
                section.sort_order = item['sort_order']
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


# ─────────────────────────────────────────────
# プレビュー
# ─────────────────────────────────────────────
@bp.route('/preview')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def preview():
    """ホームページのプレビューを表示する"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        site = _get_or_create_site(db, tenant_id)
        sections = db.query(THomepageSection).filter(
            and_(THomepageSection.site_id == site.id, THomepageSection.visible == 1)
        ).order_by(THomepageSection.sort_order.asc()).all()
        return render_template(
            'homepage_builder_preview.html',
            site=site,
            sections=sections,
            section_type_map=SECTION_TYPE_MAP,
        )
    finally:
        db.close()


# ─────────────────────────────────────────────
# HTMLエクスポート
# ─────────────────────────────────────────────
@bp.route('/export')
@require_roles(ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"])
def export_html():
    """ホームページのHTMLをエクスポートする"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    try:
        site = _get_or_create_site(db, tenant_id)
        sections = db.query(THomepageSection).filter(
            and_(THomepageSection.site_id == site.id, THomepageSection.visible == 1)
        ).order_by(THomepageSection.sort_order.asc()).all()
        html_content = render_template(
            'homepage_builder_export.html',
            site=site,
            sections=sections,
            section_type_map=SECTION_TYPE_MAP,
        )
        # 保存
        site.published_html = html_content
        site.published = 1
        db.commit()
        filename = f"homepage_{site.site_name}_{datetime.now().strftime('%Y%m%d')}.html"
        return Response(
            html_content,
            mimetype='text/html',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    finally:
        db.close()
