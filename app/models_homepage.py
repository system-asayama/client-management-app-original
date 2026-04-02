"""
ホームページ制作アプリ用のSQLAlchemyモデル
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from app.db import Base


class THomepageSite(Base):
    """ホームページサイト設定テーブル（テナント単位）"""
    __tablename__ = 'T_ホームページサイト'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    site_name = Column(String(255), nullable=False, default='', comment='サイト名')
    site_tagline = Column(String(500), nullable=True, comment='キャッチコピー')
    site_description = Column(Text, nullable=True, comment='サイト説明文')
    logo_url = Column(Text, nullable=True, comment='ロゴ画像URL')
    favicon_url = Column(Text, nullable=True, comment='ファビコンURL')
    primary_color = Column(String(20), nullable=False, default='#2563a8', comment='メインカラー')
    secondary_color = Column(String(20), nullable=False, default='#1a3a5c', comment='サブカラー')
    font_family = Column(String(100), nullable=False, default='Noto Sans JP', comment='フォント')
    published = Column(Integer, default=0, comment='公開フラグ（1=公開）')
    published_html = Column(Text, nullable=True, comment='公開済みHTML')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class THomepageSection(Base):
    """ホームページセクションテーブル"""
    __tablename__ = 'T_ホームページセクション'

    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(Integer, ForeignKey('T_ホームページサイト.id'), nullable=False)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    section_type = Column(String(50), nullable=False, comment='セクション種別: hero/about/services/features/contact/footer/custom')
    title = Column(String(500), nullable=True, comment='タイトル')
    subtitle = Column(String(500), nullable=True, comment='サブタイトル')
    body = Column(Text, nullable=True, comment='本文')
    image_url = Column(Text, nullable=True, comment='画像URL')
    button_text = Column(String(100), nullable=True, comment='ボタンテキスト')
    button_url = Column(String(500), nullable=True, comment='ボタンリンク先')
    sort_order = Column(Integer, default=0, comment='表示順')
    visible = Column(Integer, default=1, comment='表示フラグ（1=表示）')
    extra_json = Column(Text, nullable=True, comment='追加設定JSON')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
