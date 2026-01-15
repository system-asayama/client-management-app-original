# models_company.py - 会社基本情報モデル
from sqlalchemy import Column, Integer, String, ForeignKey
from app.db import Base

class TCompanyInfo(Base):
    """会社基本情報モデル"""
    __tablename__ = 'T_会社基本情報'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    顧問先ID = Column('顧問先ID', Integer, ForeignKey('T_顧問先.id'), nullable=False)
    会社名 = Column('会社名', String(255))
    郵便番号 = Column('郵便番号', String(20))
    都道府県 = Column('都道府県', String(50))
    市区町村番地 = Column('市区町村番地', String(255))
    建物名部屋番号 = Column('建物名部屋番号', String(255))
    電話番号1 = Column('電話番号1', String(50))
    電話番号2 = Column('電話番号2', String(50))
    ファックス番号 = Column('ファックス番号', String(50))
    メールアドレス = Column('メールアドレス', String(255))
    担当者名 = Column('担当者名', String(100))
    業種 = Column('業種', String(100))
    従業員数 = Column('従業員数', Integer)
    法人番号 = Column('法人番号', String(50))
