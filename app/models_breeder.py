# -*- coding: utf-8 -*-
"""
ブリーダー管理システム用 SQLAlchemy モデル
"""
from __future__ import annotations
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date,
    ForeignKey, Numeric, Enum as SAEnum
)
from sqlalchemy.sql import func
from app.db import Base


# ─────────────────────────────────────────────
# 犬（親犬・外部犬）
# ─────────────────────────────────────────────
class Dog(Base):
    """親犬・外部犬テーブル"""
    __tablename__ = 'dogs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment='犬名（通称）')
    registration_name = Column(String(200), nullable=True, comment='登録名')
    breed = Column(String(100), nullable=False, comment='犬種')
    gender = Column(SAEnum('male', 'female', name='dog_gender'), nullable=False)
    birth_date = Column(Date, nullable=True)
    color = Column(String(100), nullable=True, comment='毛色')
    microchip_number = Column(String(50), nullable=True, comment='マイクロチップ番号')
    pedigree_number = Column(String(50), nullable=True, comment='血統書番号')
    dog_type = Column(SAEnum('parent', 'external', name='dog_type'), nullable=False, default='parent')
    status = Column(SAEnum('active', 'retired', 'transferred', 'deceased', name='dog_status'), nullable=False, default='active')
    photo_url = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 子犬
# ─────────────────────────────────────────────
class Puppy(Base):
    """子犬テーブル"""
    __tablename__ = 'puppies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=True, comment='子犬名')
    breed = Column(String(100), nullable=False)
    gender = Column(SAEnum('male', 'female', name='puppy_gender'), nullable=False)
    birth_date = Column(Date, nullable=True)
    color = Column(String(100), nullable=True)
    microchip_number = Column(String(50), nullable=True)
    pedigree_number = Column(String(50), nullable=True)
    birth_id = Column(Integer, ForeignKey('births.id'), nullable=True)
    mother_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    father_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    status = Column(SAEnum('available', 'reserved', 'sold', 'transferred', 'deceased', name='puppy_status'), nullable=False, default='available')
    price = Column(Numeric(10, 0), nullable=True)
    photo_url = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# ヒート（発情）管理
# ─────────────────────────────────────────────
class Heat(Base):
    """ヒート管理テーブル"""
    __tablename__ = 'heats'

    id = Column(Integer, primary_key=True, autoincrement=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=False)
    start_date = Column(Date, nullable=True)
    last_confirmed_date = Column(Date, nullable=True)
    next_predicted_date = Column(Date, nullable=True)
    status = Column(SAEnum('unregistered', 'upcoming', 'imminent', 'active', 'completed', name='heat_status'), nullable=False, default='unregistered')
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 交配管理
# ─────────────────────────────────────────────
class Mating(Base):
    """交配管理テーブル"""
    __tablename__ = 'matings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mother_id = Column(Integer, ForeignKey('dogs.id'), nullable=False)
    father_id = Column(Integer, ForeignKey('dogs.id'), nullable=False)
    heat_id = Column(Integer, ForeignKey('heats.id'), nullable=True)
    mating_date = Column(Date, nullable=False)
    method = Column(SAEnum('natural', 'ai', 'frozen', name='mating_method'), nullable=False, default='natural')
    expected_birth_date = Column(Date, nullable=True)
    status = Column(SAEnum('mated', 'pregnant', 'birthed', 'failed', name='mating_status'), nullable=False, default='mated')
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 出産管理
# ─────────────────────────────────────────────
class Birth(Base):
    """出産管理テーブル"""
    __tablename__ = 'births'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mating_id = Column(Integer, ForeignKey('matings.id'), nullable=True)
    mother_id = Column(Integer, ForeignKey('dogs.id'), nullable=False)
    father_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    birth_date = Column(Date, nullable=False)
    total_count = Column(Integer, default=0)
    alive_count = Column(Integer, default=0)
    male_count = Column(Integer, default=0)
    female_count = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# Todo
# ─────────────────────────────────────────────
class Todo(Base):
    """Todoテーブル"""
    __tablename__ = 'todos'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(SAEnum('pending', 'completed', name='todo_status'), nullable=False, default='pending')
    category = Column(String(50), nullable=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# コンタクト（顧客）
# ─────────────────────────────────────────────
class Contact(Base):
    """コンタクト（顧客）テーブル"""
    __tablename__ = 'contacts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(320), nullable=True)
    phone = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 商談管理
# ─────────────────────────────────────────────
class Negotiation(Base):
    """商談管理テーブル"""
    __tablename__ = 'negotiations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(Integer, ForeignKey('contacts.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    status = Column(SAEnum('inquiry', 'negotiating', 'reserved', 'contracted', 'completed', 'cancelled', name='negotiation_status'), nullable=False, default='inquiry')
    price = Column(Numeric(10, 0), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# ライフログ
# ─────────────────────────────────────────────
class LifeLog(Base):
    """ライフログテーブル"""
    __tablename__ = 'life_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    contact_id = Column(Integer, ForeignKey('contacts.id'), nullable=True)
    log_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    logged_at = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())


# ─────────────────────────────────────────────
# 申請管理（血統書・チップ）
# ─────────────────────────────────────────────
class PedigreeApplication(Base):
    """血統書申請テーブル"""
    __tablename__ = 'pedigree_applications'

    id = Column(Integer, primary_key=True, autoincrement=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    application_date = Column(Date, nullable=True)
    status = Column(SAEnum('pending', 'submitted', 'approved', 'rejected', name='pedigree_app_status'), nullable=False, default='pending')
    pedigree_number = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ChipApplication(Base):
    """チップ申請テーブル"""
    __tablename__ = 'chip_applications'

    id = Column(Integer, primary_key=True, autoincrement=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    application_date = Column(Date, nullable=True)
    status = Column(SAEnum('pending', 'submitted', 'approved', 'rejected', name='chip_app_status'), nullable=False, default='pending')
    chip_number = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 健康管理
# ─────────────────────────────────────────────
class WeightRecord(Base):
    """体重記録テーブル"""
    __tablename__ = 'weight_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    weight = Column(Numeric(6, 2), nullable=False)
    recorded_at = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class VaccineRecord(Base):
    """ワクチン記録テーブル"""
    __tablename__ = 'vaccine_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    vaccine_name = Column(String(100), nullable=False)
    administered_at = Column(Date, nullable=False)
    next_due_at = Column(Date, nullable=True)
    clinic = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class HealthCheckRecord(Base):
    """健診記録テーブル"""
    __tablename__ = 'health_check_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    checked_at = Column(Date, nullable=False)
    clinic = Column(String(200), nullable=True)
    result = Column(String(200), nullable=True)
    next_due_at = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class MedicationRecord(Base):
    """投薬記録テーブル"""
    __tablename__ = 'medication_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    medication_name = Column(String(100), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    dosage = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class MedicalHistory(Base):
    """病歴テーブル"""
    __tablename__ = 'medical_histories'

    id = Column(Integer, primary_key=True, autoincrement=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    diagnosed_at = Column(Date, nullable=False)
    disease = Column(String(200), nullable=False)
    treatment = Column(Text, nullable=True)
    clinic = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class FoodRecord(Base):
    """フード管理テーブル"""
    __tablename__ = 'food_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    food_name = Column(String(200), nullable=False)
    brand = Column(String(100), nullable=True)
    daily_amount = Column(Numeric(6, 1), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# ─────────────────────────────────────────────
# 法規制対応（台帳）
# ─────────────────────────────────────────────
class LedgerEntry(Base):
    """台帳エントリテーブル"""
    __tablename__ = 'ledger_entries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_date = Column(Date, nullable=False)
    entry_type = Column(SAEnum('acquisition', 'birth', 'sale', 'transfer', 'death', name='ledger_type'), nullable=False)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# ─────────────────────────────────────────────
# 設定・イベントプリセット
# ─────────────────────────────────────────────
class AppSetting(Base):
    """アプリ設定テーブル"""
    __tablename__ = 'app_settings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), nullable=False, unique=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class EventPreset(Base):
    """イベントプリセットテーブル"""
    __tablename__ = 'event_presets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# ─────────────────────────────────────────────
# ドキュメントスキャン（OCR取り込み）
# ─────────────────────────────────────────────
class DocumentScan(Base):
    """ドキュメントスキャンテーブル（血統書PDF等のOCR取り込み）"""
    __tablename__ = 'document_scans'

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    scan_type = Column(String(50), nullable=False, default='pedigree')  # pedigree / chip
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    status = Column(String(20), nullable=False, default='pending')  # pending / success / failed
    result_json = Column(Text, nullable=True)   # OCR結果JSON
    error_message = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
