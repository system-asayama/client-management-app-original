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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
    name = Column(String(100), nullable=False, comment='犬名（通称）')
    registration_name = Column(String(200), nullable=True, comment='登録名')
    breed = Column(String(100), nullable=True, comment='犬種')
    gender = Column(SAEnum('male', 'female', name='dog_gender'), nullable=True)
    birth_date = Column(Date, nullable=True)
    color = Column(String(100), nullable=True, comment='毛色')
    microchip_number = Column(String(50), nullable=True, comment='マイクロチップ番号')
    pedigree_number = Column(String(50), nullable=True, comment='血統書番号')
    dog_type = Column(SAEnum('parent', 'external', name='dog_type'), nullable=False, default='parent')
    status = Column(SAEnum('active', 'retired', 'transferred', 'deceased', name='dog_status'), nullable=False, default='active')
    photo_url = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    father_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    mother_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 子犬
# ─────────────────────────────────────────────
class Puppy(Base):
    """子犬テーブル"""
    __tablename__ = 'puppies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
    key = Column(String(100), nullable=False, unique=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class EventPreset(Base):
    """イベントプリセットテーブル"""
    __tablename__ = 'event_presets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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
    tenant_id = Column(Integer, nullable=True, index=True, comment="テナントID")
    store_id = Column(Integer, nullable=True, index=True, comment="店舗ID")
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

# ─────────────────────────────────────────────
# ブリーダーアプリ権限管理
# ─────────────────────────────────────────────
class BreederPermission(Base):
    """ブリーダーアプリ権限テーブル
    admin（店舗管理者）にテナント単位の閲覧・操作権限を付与する。
    permission_level: 'view'=閲覧のみ, 'operate'=操作（閲覧+編集・追加・削除）
    """
    __tablename__ = 'breeder_permissions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, nullable=False, index=True, comment='対象管理者ID')
    tenant_id = Column(Integer, nullable=False, index=True, comment='対象テナントID')
    permission_level = Column(String(20), nullable=False, default='view', comment='view or operate')
    granted_by = Column(Integer, nullable=True, comment='付与したテナント管理者ID')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

# ─────────────────────────────────────────────
# 遺伝疾患検査結果（Churupi相当）
# ─────────────────────────────────────────────
class GeneticTestResult(Base):
    """遺伝疾患検査結果テーブル
    クリア / キャリア / アフェクテッド を犬ごとに記録する。
    """
    __tablename__ = 'genetic_test_results'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=True, index=True)
    store_id = Column(Integer, nullable=True, index=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    disease_name = Column(String(200), nullable=False, comment='疾患名')
    result = Column(SAEnum('clear', 'carrier', 'affected', 'unknown', name='gene_result'),
                    nullable=False, default='unknown', comment='クリア/キャリア/アフェクテッド/不明')
    tested_at = Column(Date, nullable=True, comment='検査日')
    lab_name = Column(String(200), nullable=True, comment='検査機関')
    certificate_url = Column(Text, nullable=True, comment='証明書URL')
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

# ─────────────────────────────────────────────
# ショー記録（Churupi相当）
# ─────────────────────────────────────────────
class ShowRecord(Base):
    """ドッグショー記録テーブル"""
    __tablename__ = 'show_records'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=True, index=True)
    store_id = Column(Integer, nullable=True, index=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    show_name = Column(String(300), nullable=False, comment='ショー名')
    show_date = Column(Date, nullable=False, comment='開催日')
    location = Column(String(300), nullable=True, comment='開催地')
    title_earned = Column(String(200), nullable=True, comment='取得タイトル')
    placement = Column(String(100), nullable=True, comment='順位・受賞内容')
    judge_name = Column(String(200), nullable=True, comment='審査員名')
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

# ─────────────────────────────────────────────
# 公開カルテ（Churupi相当）
# ─────────────────────────────────────────────
class PublicCarte(Base):
    """公開カルテテーブル
    子犬・親犬の情報を外部（顧客）向けに公開するための設定。
    public_token を URL に埋め込んで認証なしでアクセス可能にする。
    """
    __tablename__ = 'public_cartes'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=True, index=True)
    store_id = Column(Integer, nullable=True, index=True)
    dog_id = Column(Integer, ForeignKey('dogs.id'), nullable=True)
    puppy_id = Column(Integer, ForeignKey('puppies.id'), nullable=True)
    public_token = Column(String(64), nullable=False, unique=True, comment='公開URL用トークン')
    is_published = Column(Integer, nullable=False, default=0, comment='0=非公開 1=公開')
    intro_text = Column(Text, nullable=True, comment='ワンちゃん紹介文')
    view_count = Column(Integer, nullable=False, default=0, comment='閲覧数')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

# ─────────────────────────────────────────────
# 犬舎情報（Churupi相当）
# ─────────────────────────────────────────────
class KennelProfile(Base):
    """犬舎プロフィールテーブル
    犬舎の紹介文・ギャラリー・環境情報などを管理する。
    """
    __tablename__ = 'kennel_profiles'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=True, index=True)
    store_id = Column(Integer, nullable=True, index=True)
    kennel_name = Column(String(200), nullable=True, comment='犬舎名')
    intro_text = Column(Text, nullable=True, comment='犬舎紹介文')
    address = Column(String(300), nullable=True, comment='所在地')
    phone = Column(String(30), nullable=True)
    email = Column(String(320), nullable=True)
    website_url = Column(Text, nullable=True)
    gallery_json = Column(Text, nullable=True, comment='ギャラリー画像URL JSON配列')
    staff_per_dog_ratio = Column(Numeric(5, 2), nullable=True, comment='スタッフ1人あたり親犬頭数')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 血統書祖先情報
# ─────────────────────────────────────────────
class PedigreeAncestor(Base):
    """血統書4代分の祖先情報テーブル
    血統書スキャンから取得した最大4世代の祖先情報を保存する。
    generation: 1=父母, 2=祖父母, 3=曾祖父母, 4=高祖父母
    position: sire/dam/sire_sire/sire_dam/dam_sire/dam_dam/... の位置コード
    """
    __tablename__ = 'pedigree_ancestors'
    id = Column(Integer, primary_key=True, autoincrement=True)
    dog_id = Column(Integer, ForeignKey('dogs.id', ondelete='CASCADE'), nullable=False, index=True)
    generation = Column(Integer, nullable=False, comment='世代（1=父母, 2=祖父母, 3=曾祖父母, 4=高祖父母）')
    position = Column(String(30), nullable=False, comment='位置コード（sire/dam/sire_sire等）')
    name = Column(String(300), nullable=True, comment='犬名')
    registration_number = Column(String(100), nullable=True, comment='登録番号')
    breed = Column(String(100), nullable=True, comment='犬種')
    color = Column(String(100), nullable=True, comment='毛色')
    country_prefix = Column(String(20), nullable=True, comment='国プレフィックス')
    created_at = Column(DateTime, server_default=func.now())

# ─────────────────────────────────────────────
# 交配評価結果
# ─────────────────────────────────────────────
class MatingEvaluation(Base):
    """交配評価結果テーブル
    evaluate_mating_compatibility の結果を保存する。
    result_json に出力 JSON 全体を格納する。
    """
    __tablename__ = 'mating_evaluations'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=True, index=True, comment='テナントID')
    store_id  = Column(Integer, nullable=True, index=True, comment='店舗ID')
    sire_id   = Column(Integer, ForeignKey('dogs.id'), nullable=False, comment='父犬ID')
    dam_id    = Column(Integer, ForeignKey('dogs.id'), nullable=False, comment='母犬ID')
    coi       = Column(Numeric(10, 8), nullable=True, comment='近交係数（小数）')
    coi_percent = Column(Numeric(8, 4), nullable=True, comment='近交係数（%）')
    rank      = Column(String(2), nullable=True, comment='ランク A〜E')
    recommendation = Column(String(100), nullable=True, comment='推奨/非推奨')
    result_json = Column(Text, nullable=True, comment='評価結果 JSON 全体')
    max_depth = Column(Integer, nullable=False, default=5, comment='探索世代数')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

# ─────────────────────────────────────────────
# 犬種別リスクマスタ
# ─────────────────────────────────────────────
class BreedRiskMaster(Base):
    """犬種別リスクマスタテーブル"""
    __tablename__ = 'breed_risk_masters'
    id = Column(Integer, primary_key=True, autoincrement=True)
    breed = Column(String(100), nullable=False, index=True, comment='犬種名')
    risk_name = Column(String(200), nullable=False, comment='リスク名')
    risk_category = Column(String(50), nullable=True, comment='カテゴリ（genetic/structural/other）')
    severity = Column(String(20), nullable=True, comment='重篤度（high/medium/low）')
    description = Column(Text, nullable=True, comment='説明')
    recommended_test = Column(String(300), nullable=True, comment='推奨検査')
    notes = Column(Text, nullable=True, comment='備考')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 親犬の健康履歴
# ─────────────────────────────────────────────
class DogHealthRecord(Base):
    """親犬の健康履歴テーブル"""
    __tablename__ = 'dog_health_records'
    id = Column(Integer, primary_key=True, autoincrement=True)
    dog_id = Column(Integer, ForeignKey('dogs.id', ondelete='CASCADE'), nullable=False, index=True)
    record_date = Column(Date, nullable=True, comment='記録日')
    category = Column(String(50), nullable=True, comment='カテゴリ（orthopedic/eye/heart/skin/respiratory/digestive/neurological/reproductive/other）')
    title = Column(String(300), nullable=False, comment='タイトル')
    severity = Column(String(20), nullable=True, comment='重篤度（critical/high/medium/low）')
    description = Column(Text, nullable=True, comment='詳細')
    diagnosed_by_vet = Column(Integer, nullable=True, comment='獣医師診断フラグ（1=あり）')
    resolved = Column(Integer, nullable=True, comment='解決済みフラグ（1=解決済み）')
    notes = Column(Text, nullable=True, comment='備考')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 繁殖履歴
# ─────────────────────────────────────────────
class BreedingHistory(Base):
    """繁殖履歴テーブル"""
    __tablename__ = 'breeding_histories'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=True, index=True)
    store_id = Column(Integer, nullable=True, index=True)
    sire_id = Column(Integer, ForeignKey('dogs.id'), nullable=False, index=True, comment='父犬ID')
    dam_id = Column(Integer, ForeignKey('dogs.id'), nullable=False, index=True, comment='母犬ID')
    mating_date = Column(Date, nullable=True, comment='交配日')
    birth_date = Column(Date, nullable=True, comment='出産日')
    pregnancy_result = Column(String(20), nullable=True, comment='妊娠結果（success/failed/miscarriage/unknown）')
    puppy_count = Column(Integer, nullable=True, comment='出生頭数')
    live_birth_count = Column(Integer, nullable=True, comment='生存出生頭数')
    stillbirth_count = Column(Integer, nullable=True, comment='死産頭数')
    c_section = Column(Integer, nullable=True, comment='帝王切開フラグ（1=あり）')
    complications = Column(Text, nullable=True, comment='合併症・特記事項')
    notes = Column(Text, nullable=True, comment='備考')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 産子記録
# ─────────────────────────────────────────────
class PuppyRecord(Base):
    """産子記録テーブル"""
    __tablename__ = 'puppy_records'
    id = Column(Integer, primary_key=True, autoincrement=True)
    breeding_history_id = Column(Integer, ForeignKey('breeding_histories.id', ondelete='CASCADE'), nullable=False, index=True)
    puppy_id = Column(Integer, ForeignKey('dogs.id'), nullable=True, index=True, comment='犬IDと紐付け（任意）')
    sex = Column(String(10), nullable=True, comment='性別（male/female/unknown）')
    birth_weight = Column(Numeric(6, 1), nullable=True, comment='出生体重（g）')
    survived = Column(Integer, nullable=True, comment='生存フラグ（1=生存）')
    death_date = Column(Date, nullable=True, comment='死亡日')
    death_age_days = Column(Integer, nullable=True, comment='死亡時日齢')
    health_status = Column(String(100), nullable=True, comment='健康状態')
    defects = Column(Text, nullable=True, comment='先天異常・奇形')
    notes = Column(Text, nullable=True, comment='備考')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 産子フォローアップ
# ─────────────────────────────────────────────
class PuppyFollowUp(Base):
    """産子フォローアップテーブル"""
    __tablename__ = 'puppy_followups'
    id = Column(Integer, primary_key=True, autoincrement=True)
    puppy_id = Column(Integer, ForeignKey('puppy_records.id', ondelete='CASCADE'), nullable=False, index=True)
    followup_date = Column(Date, nullable=True, comment='フォローアップ日')
    age_months = Column(Integer, nullable=True, comment='月齢')
    weight = Column(Numeric(6, 2), nullable=True, comment='体重（kg）')
    health_status = Column(String(100), nullable=True, comment='健康状態')
    disease_found = Column(Integer, nullable=True, comment='疾患発見フラグ（1=あり）')
    disease_name = Column(String(200), nullable=True, comment='疾患名')
    temperament = Column(String(200), nullable=True, comment='性格・気質')
    owner_reported = Column(Integer, nullable=True, comment='飼い主報告フラグ（1=飼い主報告）')
    notes = Column(Text, nullable=True, comment='備考')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 飼い主（将来の飼い主アプリ連携用）
# ─────────────────────────────────────────────
class Owner(Base):
    """飼い主テーブル（将来の飼い主アプリ連携用）"""
    __tablename__ = 'owners'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=True, index=True)
    store_id = Column(Integer, nullable=True, index=True)
    name = Column(String(200), nullable=False, comment='飼い主名')
    email = Column(String(320), nullable=True, comment='メールアドレス')
    phone = Column(String(30), nullable=True, comment='電話番号')
    notes = Column(Text, nullable=True, comment='備考')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# 飼い主×犬の紐付け（将来の飼い主アプリ連携用）
# ─────────────────────────────────────────────
class OwnerDog(Base):
    """飼い主と犬の紐付けテーブル（将来の飼い主アプリ連携用）"""
    __tablename__ = 'owner_dogs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey('owners.id', ondelete='CASCADE'), nullable=False, index=True)
    dog_id = Column(Integer, ForeignKey('dogs.id', ondelete='CASCADE'), nullable=False, index=True)
    acquired_date = Column(Date, nullable=True, comment='取得日')
    breeder_id = Column(Integer, nullable=True, comment='ブリーダーID（将来の連携用）')
    share_health_data = Column(Integer, nullable=True, default=0, comment='健康データ共有フラグ')
    share_followup_data = Column(Integer, nullable=True, default=0, comment='フォローアップデータ共有フラグ')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
