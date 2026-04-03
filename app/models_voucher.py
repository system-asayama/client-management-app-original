# -*- coding: utf-8 -*-
"""
証憑データ化アプリ - DBモデル
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.sql import func
from app.db import Base


class TVoucher(Base):
    """証憑テーブル（レシート・領収書モード）"""
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


class TBankStatement(Base):
    """通帳明細テーブル（通帳モード - 1ファイル1レコード）"""
    __tablename__ = 'T_通帳明細'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False, index=True)
    tenpo_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True, index=True)
    uploaded_by = Column(Integer, nullable=False, comment='アップロードしたユーザーID')

    # 画像・原始データ
    画像パス = Column(String(500), nullable=True)
    OCR結果_生データ = Column(Text, nullable=True)

    # 口座情報
    銀行名 = Column(String(255), nullable=True, comment='銀行名・金融機関名')
    支店名 = Column(String(255), nullable=True, comment='支店名')
    口座種別 = Column(String(50), nullable=True, comment='普通・当座・定期等')
    口座番号 = Column(String(50), nullable=True, comment='口座番号')
    口座名義 = Column(String(255), nullable=True, comment='口座名義')
    期間_開始 = Column(String(20), nullable=True, comment='明細期間開始日')
    期間_終了 = Column(String(20), nullable=True, comment='明細期間終了日')

    ステータス = Column(String(20), default='pending')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<TBankStatement(id={self.id}, 銀行名={self.銀行名})>"


class TBankTransaction(Base):
    """通帳明細行（通帳モード - 1明細1行）"""
    __tablename__ = 'T_通帳明細行'

    id = Column(Integer, primary_key=True, autoincrement=True)
    statement_id = Column(Integer, ForeignKey('T_通帳明細.id'), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False, index=True)

    日付 = Column(String(20), nullable=True, comment='取引日付')
    摘要 = Column(String(500), nullable=True, comment='摘要・取引内容')
    入金 = Column(Float, nullable=True, comment='入金額')
    出金 = Column(Float, nullable=True, comment='出金額')
    残高 = Column(Float, nullable=True, comment='残高')
    備考 = Column(String(500), nullable=True, comment='備考')
    行番号 = Column(Integer, nullable=True, comment='行番号')

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<TBankTransaction(id={self.id}, 日付={self.日付}, 摘要={self.摘要})>"


class TBankColumnTemplate(Base):
    """通帳列定義テンプレート（テナントごとに保存・再利用可能）"""
    __tablename__ = 'T_通帳列定義テンプレート'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False, index=True)
    テンプレート名 = Column(String(255), nullable=False, comment='テンプレート名（例：岡山銀行通帳）')
    銀行名 = Column(String(255), nullable=True, comment='対象銀行名')
    # 列定義（列番号と役割のマッピング）
    列1_役割 = Column(String(50), nullable=True, default='date', comment='列1の役割')
    列1_名称 = Column(String(100), nullable=True, default='年月日', comment='列1の表示名')
    列2_役割 = Column(String(50), nullable=True, default='code', comment='列2の役割')
    列2_名称 = Column(String(100), nullable=True, default='記号', comment='列2の表示名')
    列3_役割 = Column(String(50), nullable=True, default='withdrawal', comment='列3の役割')
    列3_名称 = Column(String(100), nullable=True, default='お払戻し金額（出金）', comment='列3の表示名')
    列4_役割 = Column(String(50), nullable=True, default='deposit', comment='列4の役割')
    列4_名称 = Column(String(100), nullable=True, default='お預り金額/お利息（入金）', comment='列4の表示名')
    列5_役割 = Column(String(50), nullable=True, default='balance', comment='列5の役割')
    列5_名称 = Column(String(100), nullable=True, default='差引残高', comment='列5の表示名')
    列6_役割 = Column(String(50), nullable=True, default='note', comment='列6の役割')
    列6_名称 = Column(String(100), nullable=True, default='備考', comment='列6の表示名')
    # 追加メモ（GPT-4oへの補足指示）
    補足指示 = Column(Text, nullable=True, comment='GPT-4oへの補足指示（例：*は金額修飾記号）')
    is_default = Column(Boolean, default=False, comment='デフォルトテンプレートとして使用するか')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<TBankColumnTemplate(id={self.id}, テンプレート名={self.テンプレート名})>"


class TCreditStatement(Base):
    """クレジット明細テーブル（クレジット明細モード - 1ファイル1レコード）"""
    __tablename__ = 'T_クレジット明細'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False, index=True)
    tenpo_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=True, index=True)
    uploaded_by = Column(Integer, nullable=False)

    # 画像・原始データ
    画像パス = Column(String(500), nullable=True)
    OCR結果_生データ = Column(Text, nullable=True)

    # カード情報
    カード会社名 = Column(String(255), nullable=True, comment='カード会社名')
    カード名 = Column(String(255), nullable=True, comment='カード名・品名')
    会員名 = Column(String(255), nullable=True, comment='会員名義')
    明細年月 = Column(String(20), nullable=True, comment='明細年月（YYYY-MM）')
    支払日 = Column(String(20), nullable=True, comment='支払日')
    利用総額 = Column(Float, nullable=True, comment='利用総額')

    ステータス = Column(String(20), default='pending')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<TCreditStatement(id={self.id}, カード会社名={self.カード会社名})>"


class TBankDescriptionLearning(Base):
    """通帳摘要学習テーブル（手動修正した摘要の対応関係を学習）"""
    __tablename__ = 'T_通帳摘要学習'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False, index=True)

    # OCRが読み取った元の摘要（正規化済み）
    元摘要 = Column(String(500), nullable=False, comment='OCR読み取り元の摘要（正規化済み）', index=True)
    # 手動修正後の摘要
    修正摘要 = Column(String(500), nullable=False, comment='手動修正後の摘要')
    # 適用回数（同じ修正が繰り返されるほど信頼度が上がる）
    適用回数 = Column(Integer, default=1, comment='この修正が適用された回数')
    # 最終更新日時
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<TBankDescriptionLearning(id={self.id}, 元摘要={self.元摘要}, 修正摘要={self.修正摘要})>"


class TCreditTransaction(Base):
    """クレジット明細行（クレジット明細モード - 1明細1行）"""
    __tablename__ = 'T_クレジット明細行'

    id = Column(Integer, primary_key=True, autoincrement=True)
    statement_id = Column(Integer, ForeignKey('T_クレジット明細.id'), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False, index=True)

    利用日 = Column(String(20), nullable=True, comment='利用日付')
    利用店名 = Column(String(500), nullable=True, comment='利用店名・内容')
    利用者 = Column(String(255), nullable=True, comment='利用者名')
    利用金額 = Column(Float, nullable=True, comment='利用金額')
    分割回数 = Column(String(50), nullable=True, comment='分割回数・支払方法')
    備考 = Column(String(500), nullable=True, comment='備考')
    行番号 = Column(Integer, nullable=True, comment='行番号')

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<TCreditTransaction(id={self.id}, 利用日={self.利用日}, 利用店名={self.利用店名})>"
