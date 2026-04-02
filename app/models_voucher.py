# -*- coding: utf-8 -*-
"""
証憑データ化アプリ - DBモデル
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.sql import func
from app.db import Base


class TVoucher(Base):
    """証憑テーブル"""
    __tablename__ = 'T_証憑'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False, index=True, comment='テナントID')
    tenpo_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True, index=True, comment='店舗ID（店舗アプリの場合）')
    uploaded_by = Column(Integer, nullable=False, comment='アップロードした従業員ID')
    company_id = Column(Integer, nullable=True, comment='取引先会社ID（T_会社）')
    
    # 画像・OCR
    画像パス = Column(String(500), nullable=True, comment='アップロードされた画像ファイルのパス')
    OCR結果_生データ = Column(Text, nullable=True, comment='OCRで抽出された生テキスト')
    
    # 抽出データ
    電話番号 = Column(String(50), nullable=True, comment='抽出された電話番号')
    住所 = Column(String(500), nullable=True, comment='抽出された住所')
    郵便番号 = Column(String(20), nullable=True, comment='抽出された郵便番号')
    会社名 = Column(String(255), nullable=True, comment='抽出された会社名')
    金額 = Column(Float, nullable=True, comment='抽出された金額')
    日付 = Column(String(20), nullable=True, comment='抽出された日付（YYYY-MM-DD）')
    インボイス番号 = Column(String(50), nullable=True, comment='適格請求書発行事業者登録番号')
    法人番号 = Column(String(50), nullable=True, comment='法人番号（13桁）')
    
    # 編集可能フィールド
    摘要 = Column(String(500), nullable=True, comment='摘要・メモ')
    ステータス = Column(String(20), default='pending', comment='処理ステータス（pending/processing/completed）')
    
    # タイムスタンプ
    created_at = Column(DateTime, server_default=func.now(), comment='作成日時')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新日時')
    
    def __repr__(self):
        return f"<TVoucher(id={self.id}, 日付={self.日付}, 金額={self.金額})>"


class TCompany(Base):
    """取引先会社テーブル"""
    __tablename__ = 'T_会社'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False, index=True, comment='テナントID')
    
    # 基本情報
    会社名 = Column(String(255), nullable=False, comment='会社名')
    会社名_カナ = Column(String(255), nullable=True, comment='会社名カナ')
    法人番号 = Column(String(13), nullable=True, unique=True, index=True, comment='法人番号（13桁）')
    郵便番号 = Column(String(10), nullable=True, comment='郵便番号')
    住所 = Column(String(500), nullable=True, comment='住所')
    電話番号 = Column(String(50), nullable=True, comment='電話番号')
    
    # タイムスタンプ
    created_at = Column(DateTime, server_default=func.now(), comment='作成日時')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新日時')
    
    def __repr__(self):
        return f"<TCompany(id={self.id}, 会社名={self.会社名})>"
