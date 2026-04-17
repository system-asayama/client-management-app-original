"""
不動産管理アプリ用のSQLAlchemyモデル
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Numeric, Date
from sqlalchemy.sql import func
from app.db import Base


class TBukken(Base):
    """T_物件テーブル"""
    __tablename__ = 'T_物件'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    物件名 = Column(String(255), nullable=False)
    物件種別 = Column(String(50), nullable=True)
    郵便番号 = Column(String(10), nullable=True)
    住所 = Column(String(500), nullable=True)
    建築年月 = Column(Date, nullable=True)
    延床面積 = Column(Numeric(10, 2), nullable=True)
    構造 = Column(String(50), nullable=True)
    階数 = Column(Integer, nullable=True)
    部屋数 = Column(Integer, nullable=True)
    取得価額 = Column(Numeric(15, 2), nullable=True)
    取得年月日 = Column(Date, nullable=True)
    耐用年数 = Column(Integer, nullable=True)
    償却方法 = Column(String(20), nullable=True)
    残存価額 = Column(Numeric(15, 2), nullable=True)
    備考 = Column(Text, nullable=True)
    # 建物付属設備
    付属設備_取得価額 = Column(Numeric(15, 2), nullable=True)
    付属設備_取得年月日 = Column(Date, nullable=True)
    付属設備_耐用年数 = Column(Integer, nullable=True, default=15)
    付属設備_償却方法 = Column(String(20), nullable=True, default='定額法')
    付属設備_残存価額 = Column(Numeric(15, 2), nullable=True, default=0)
    付属設備_備考 = Column(Text, nullable=True)
    # 構築物
    構築物_取得価額 = Column(Numeric(15, 2), nullable=True)
    構築物_取得年月日 = Column(Date, nullable=True)
    構築物_耐用年数 = Column(Integer, nullable=True, default=15)
    構築物_償却方法 = Column(String(20), nullable=True, default='定額法')
    構築物_残存価額 = Column(Numeric(15, 2), nullable=True, default=0)
    構築物_備考 = Column(Text, nullable=True)
    有効 = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class THeya(Base):
    """T_部屋テーブル"""
    __tablename__ = 'T_部屋'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    property_id = Column(Integer, ForeignKey('T_物件.id'), nullable=False)
    部屋番号 = Column(String(50), nullable=False)
    間取り = Column(String(50), nullable=True)
    専有面積 = Column(Numeric(10, 2), nullable=True)
    賃料 = Column(Numeric(10, 0), nullable=True)
    管理費 = Column(Numeric(10, 0), nullable=True)
    敷金 = Column(Numeric(10, 0), nullable=True)
    礼金 = Column(Numeric(10, 0), nullable=True)
    入居状況 = Column(String(20), default='空室')
    備考 = Column(Text, nullable=True)
    有効 = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TNyukyosha(Base):
    """T_入居者テーブル"""
    __tablename__ = 'T_入居者'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    氏名 = Column(String(255), nullable=False)
    フリガナ = Column(String(255), nullable=True)
    生年月日 = Column(Date, nullable=True)
    電話番号 = Column(String(20), nullable=True)
    メールアドレス = Column(String(255), nullable=True)
    緊急連絡先名 = Column(String(255), nullable=True)
    緊急連絡先電話番号 = Column(String(20), nullable=True)
    備考 = Column(Text, nullable=True)
    有効 = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TKeiyaku(Base):
    """T_契約テーブル"""
    __tablename__ = 'T_契約'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey('T_部屋.id'), nullable=False)
    tenant_person_id = Column(Integer, ForeignKey('T_入居者.id'), nullable=False)
    契約開始日 = Column(Date, nullable=False)
    契約終了日 = Column(Date, nullable=True)
    月額賃料 = Column(Numeric(10, 0), nullable=False)
    月額管理費 = Column(Numeric(10, 0), nullable=True)
    敷金 = Column(Numeric(10, 0), nullable=True)
    礼金 = Column(Numeric(10, 0), nullable=True)
    契約状況 = Column(String(20), default='契約中')
    備考 = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TYachinShushi(Base):
    """T_家賃収支テーブル"""
    __tablename__ = 'T_家賃収支'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    contract_id = Column(Integer, ForeignKey('T_契約.id'), nullable=False)
    対象年月 = Column(String(7), nullable=False)
    賃料 = Column(Numeric(10, 0), nullable=False)
    管理費 = Column(Numeric(10, 0), nullable=True)
    入金日 = Column(Date, nullable=True)
    入金状況 = Column(String(20), default='未入金')
    備考 = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TGenkashokaku(Base):
    """T_減価償却テーブル"""
    __tablename__ = 'T_減価償却'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    property_id = Column(Integer, ForeignKey('T_物件.id'), nullable=False)
    年度 = Column(Integer, nullable=False)
    期首帳簿価額 = Column(Numeric(15, 2), nullable=False)
    償却額 = Column(Numeric(15, 2), nullable=False)
    期末帳簿価額 = Column(Numeric(15, 2), nullable=False)
    備考 = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TSimulation(Base):
    """T_シミュレーションテーブル"""
    __tablename__ = 'T_シミュレーション'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    名称 = Column(String(255), nullable=False)
    
    # シミュレーション種別
    シミュレーション種別 = Column(String(20), nullable=False, server_default='物件ベース')
    
    # 物件ベースシミュレーション用
    物件id = Column(Integer, ForeignKey('T_物件.id'), nullable=True)
    
    # 独立シミュレーション用
    年間家賃収入 = Column(Numeric(15, 2), nullable=True)
    部屋数 = Column(Integer, nullable=True)
    開始年度 = Column(Integer, nullable=False)
    期間 = Column(Integer, nullable=False)
    稼働率 = Column(Numeric(5, 2), default=95.00)
    管理費率 = Column(Numeric(5, 2), default=5.00)
    修繕費率 = Column(Numeric(5, 2), default=5.00)
    固定資産税 = Column(Numeric(15, 2), default=0)
    損害保険料 = Column(Numeric(15, 2), default=0)
    ローン残高 = Column(Numeric(15, 2), default=0)
    ローン金利 = Column(Numeric(5, 2), default=0)
    ローン年間返済額 = Column(Numeric(15, 2), default=0)
    ローン計算モード = Column(Integer, default=1)  # 1:簡易モード, 2:詳細モード
    
    # ローン詳細情報（自動計算用）
    借入金額 = Column(Numeric(15, 2), nullable=True)
    返済期間_年 = Column(Integer, nullable=True)
    返済方法 = Column(String(20), nullable=True)  # '元利均等' or '元金均等'
    返済開始日 = Column(Date, nullable=True)
    その他収入 = Column(Numeric(15, 2), default=0)
    その他経費 = Column(Numeric(15, 2), default=0)
    減価償却費 = Column(Numeric(15, 2), default=0)
    その他所得 = Column(Numeric(15, 2), default=0)
    税率 = Column(Numeric(5, 2), nullable=True)
    
    # 減価償却設定（建物部分）
    建物_取得価額 = Column(Numeric(15, 2), nullable=True, default=0)
    建物_耐用年数 = Column(Integer, nullable=True, default=47)
    建物_償却方法 = Column(String(20), nullable=True, default='定額法')
    建物_残存価額 = Column(Numeric(15, 2), nullable=True, default=0)
    
    # 減価償却設定（建物付属設備）
    付属設備_取得価額 = Column(Numeric(15, 2), nullable=True, default=0)
    付属設備_耐用年数 = Column(Integer, nullable=True, default=15)
    付属設備_償却方法 = Column(String(20), nullable=True, default='定額法')
    付属設備_残存価額 = Column(Numeric(15, 2), nullable=True, default=0)
    
    # 減価償却設定（構築物）
    構築物_取得価額 = Column(Numeric(15, 2), nullable=True, default=0)
    構築物_耐用年数 = Column(Integer, nullable=True, default=20)
    構築物_償却方法 = Column(String(20), nullable=True, default='定額法')
    構築物_残存価額 = Column(Numeric(15, 2), nullable=True, default=0)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TSimulationResult(Base):
    """T_シミュレーション結果テーブル"""
    __tablename__ = 'T_シミュレーション結果'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    シミュレーションid = Column(Integer, ForeignKey('T_シミュレーション.id'), nullable=False)
    年度 = Column(Integer, nullable=False)
    家賃収入 = Column(Numeric(15, 2), default=0)
    その他収入 = Column(Numeric(15, 2), default=0)
    総収入 = Column(Numeric(15, 2), default=0)
    管理費 = Column(Numeric(15, 2), default=0)
    修繕費 = Column(Numeric(15, 2), default=0)
    固定資産税 = Column(Numeric(15, 2), default=0)
    損害保険料 = Column(Numeric(15, 2), default=0)
    借入金利息 = Column(Numeric(15, 2), default=0)
    減価償却費 = Column(Numeric(15, 2), default=0)
    その他経費 = Column(Numeric(15, 2), default=0)
    総経費 = Column(Numeric(15, 2), default=0)
    不動産所得 = Column(Numeric(15, 2), default=0)
    税金 = Column(Numeric(15, 2), default=0)
    キャッシュフロー = Column(Numeric(15, 2), default=0)
    ローン残高 = Column(Numeric(15, 2), default=0)
    created_at = Column(DateTime, server_default=func.now())


class TBukkenKeihi(Base):
    """T_物件経費テーブル"""
    __tablename__ = 'T_物件経費'
    
    物件経貿id = Column(Integer, primary_key=True, autoincrement=True)
    物件id = Column(Integer, ForeignKey('T_物件.id'), nullable=False)
    経費名 = Column(String(100), nullable=False)
    経費カテゴリ = Column(String(50), nullable=False)
    金額 = Column(Numeric(15, 2), nullable=False)
    発生日 = Column(Date, nullable=False)
    支払日 = Column(Date, nullable=True)
    支払方法 = Column(String(50), nullable=True)
    備考 = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class THeyaKeihi(Base):
    """T_部屋経費テーブル"""
    __tablename__ = 'T_部屋経費'
    
    部屋経貿id = Column(Integer, primary_key=True, autoincrement=True)
    部屋id = Column(Integer, ForeignKey('T_部屋.id'), nullable=False)
    経費名 = Column(String(100), nullable=False)
    経費カテゴリ = Column(String(50), nullable=False)
    金額 = Column(Numeric(15, 2), nullable=False)
    発生日 = Column(Date, nullable=False)
    支払日 = Column(Date, nullable=True)
    支払方法 = Column(String(50), nullable=True)
    備考 = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TLoanCondition(Base):
    """T_ローン条件テーブル（詳細モード用）"""
    __tablename__ = 'T_ローン条件'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    シミュレーションid = Column(Integer, ForeignKey('T_シミュレーション.id'), nullable=False)
    借入日 = Column(Date, nullable=False)
    返済日 = Column(Integer, nullable=False)  # 毎月の返済日(1-31)
    返済開始年月 = Column(String(7), nullable=False)  # YYYY-MM形式
    据置期間終了年月 = Column(String(7), nullable=True)  # YYYY-MM形式、NULLの場合は据置なし
    初回利息支払方法 = Column(Integer, nullable=False, default=1)  # 1:初回にまとめて, 2:月末に支払, 3:無視
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TLoanInterestSchedule(Base):
    """T_ローン金利スケジュールテーブル（詳細モード用）"""
    __tablename__ = 'T_ローン金利スケジュール'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    シミュレーションid = Column(Integer, ForeignKey('T_シミュレーション.id'), nullable=False)
    開始年月 = Column(String(7), nullable=False)  # YYYY-MM形式
    終了年月 = Column(String(7), nullable=True)  # YYYY-MM形式、NULLは最終年度まで
    金利 = Column(Numeric(5, 3), nullable=False)  # 年利率(%)
    備考 = Column(String(200), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
