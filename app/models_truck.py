# -*- coding: utf-8 -*-
"""
トラック運行管理システム DBモデル
"""
from datetime import datetime, date
from app.db import Base
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship


class TruckAdmin(Base):
    __tablename__ = "truck_admins"
    id = Column(Integer, primary_key=True)
    login_id = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(256), nullable=False)
    name = Column(String(100), nullable=False)
    tenant_id = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Truck(Base):
    __tablename__ = "trucks"
    id = Column(Integer, primary_key=True)
    number = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False)
    capacity = Column(Float)
    note = Column(Text)
    tenant_id = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ── 詳細情報 ──
    owner_name = Column(String(100))          # 所有者
    user_name = Column(String(100))           # 使用者
    base_location = Column(String(200))       # 所属（営業所・拠点）
    vehicle_type = Column(String(100))        # 車種・型式
    year = Column(Integer)                    # 年式
    color = Column(String(50))                # 車体色
    vin = Column(String(100))                 # 車台番号
    engine_number = Column(String(100))       # エンジン番号
    # 車検情報
    shaken_expiry = Column(Date)              # 車検満了日
    shaken_number = Column(String(100))       # 車検証番号
    # 保険情報（簡易）
    insurance_company = Column(String(200))   # 保険会社名
    insurance_policy = Column(String(100))    # 証券番号
    insurance_expiry = Column(Date)           # 保険満了日
    # 写真
    photo_path = Column(String(500))          # 車両写真パス
    photo_name = Column(String(200))          # 元ファイル名
    # 車検証ファイル
    shaken_doc_path = Column(String(500))     # 車検証ファイルパス
    shaken_doc_name = Column(String(200))     # 車検証元ファイル名
    # 保険証ファイル
    insurance_doc_path = Column(String(500))  # 保険証ファイルパス
    insurance_doc_name = Column(String(200))  # 保険証元ファイル名

    # リレーション
    accident_records = relationship("TruckAccidentRecord", back_populates="truck", cascade="all, delete-orphan")
    inspection_records = relationship("TruckInspectionRecord", back_populates="truck", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "number": self.number,
            "name": self.name,
            "capacity": self.capacity,
            "note": self.note,
            "active": self.active,
            "owner_name": self.owner_name,
            "user_name": self.user_name,
            "base_location": self.base_location,
            "vehicle_type": self.vehicle_type,
            "year": self.year,
            "color": self.color,
            "vin": self.vin,
            "shaken_expiry": self.shaken_expiry.isoformat() if self.shaken_expiry else None,
            "shaken_number": self.shaken_number,
            "insurance_company": self.insurance_company,
            "insurance_policy": self.insurance_policy,
            "insurance_expiry": self.insurance_expiry.isoformat() if self.insurance_expiry else None,
        }


class TruckRoute(Base):
    __tablename__ = "truck_routes"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    origin = Column(String(200))
    destination = Column(String(200))
    distance_km = Column(Float)
    client_id = Column(Integer, ForeignKey("truck_clients.id"), nullable=True)  # 取引先・荷主
    contract_amount = Column(Integer)  # 請負金額（円）
    note = Column(Text)
    tenant_id = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("TruckClient", backref="routes")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "origin": self.origin,
            "destination": self.destination,
            "distance_km": self.distance_km,
            "client_id": self.client_id,
            "client_name": self.client.name if self.client else None,
            "contract_amount": self.contract_amount,
            "note": self.note,
            "active": self.active,
        }


class TruckDriver(Base):
    __tablename__ = "truck_drivers"
    id = Column(Integer, primary_key=True)
    login_id = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(256), nullable=False)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    license_number = Column(String(50))
    note = Column(Text)
    tenant_id = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "login_id": self.login_id,
            "name": self.name,
            "phone": self.phone,
            "license_number": self.license_number,
            "note": self.note,
            "active": self.active,
        }


class TruckOperation(Base):
    __tablename__ = "truck_operations"
    id = Column(Integer, primary_key=True)
    driver_id = Column(Integer, ForeignKey("truck_drivers.id"), nullable=False)
    truck_id = Column(Integer, ForeignKey("trucks.id"), nullable=False)
    route_id = Column(Integer, ForeignKey("truck_routes.id"), nullable=True)
    status = Column(String(20), default="off")
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    loading_start_time = Column(DateTime)
    unloading_start_time = Column(DateTime)
    break_start_time = Column(DateTime)
    break_end_time = Column(DateTime)
    operation_date = Column(Date, default=date.today)
    note = Column(Text)
    tenant_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    driver = relationship("TruckDriver", backref="operations")
    truck = relationship("Truck", backref="operations")
    route = relationship("TruckRoute", backref="operations")

    def to_dict(self):
        return {
            "id": self.id,
            "driver_id": self.driver_id,
            "driver_name": self.driver.name if self.driver else "-",
            "truck_id": self.truck_id,
            "truck_number": self.truck.number if self.truck else "-",
            "truck_name": self.truck.name if self.truck else "-",
            "route_id": self.route_id,
            "route_name": self.route.name if self.route else "-",
            "status": self.status,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "operation_date": self.operation_date.isoformat() if self.operation_date else None,
            "note": self.note,
        }


class TruckClient(Base):
    __tablename__ = "truck_clients"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)          # 会社名
    kana = Column(String(100))                           # フリガナ
    contact_name = Column(String(100))                   # 担当者名
    phone = Column(String(20))
    email = Column(String(200))
    address = Column(String(300))
    client_type = Column(String(20), default='both')     # shipper/consignee/both
    note = Column(Text)
    tenant_id = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "kana": self.kana,
            "contact_name": self.contact_name,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "client_type": self.client_type,
            "note": self.note,
            "active": self.active,
        }


class TruckContract(Base):
    """契約書管理"""
    __tablename__ = "truck_contracts"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)          # 契約書タイトル
    contract_type = Column(String(50))                   # lease/maintenance/other
    counterparty = Column(String(200))                   # 相手方
    start_date = Column(Date)
    end_date = Column(Date)
    amount = Column(Float)                               # 契約金額
    file_path = Column(String(500))                      # アップロードファイルパス
    file_name = Column(String(200))                      # 元のファイル名
    # OCR読み取り結果
    ocr_title = Column(String(200))
    ocr_counterparty = Column(String(200))
    ocr_start_date = Column(String(50))
    ocr_end_date = Column(String(50))
    ocr_amount = Column(String(100))
    ocr_summary = Column(Text)
    ocr_raw = Column(Text)                               # OCR生JSON
    ocr_status = Column(String(20), default='none')      # none/processing/done/error
    note = Column(Text)
    tenant_id = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TruckInsurance(Base):
    """保険情報管理"""
    __tablename__ = "truck_insurances"
    id = Column(Integer, primary_key=True)
    insurance_type = Column(String(50))                  # 自賠責/任意/貨物/その他
    insurer = Column(String(200))                        # 保険会社名
    policy_number = Column(String(100))                  # 証券番号
    truck_id = Column(Integer, ForeignKey("trucks.id"), nullable=True)  # 対象車両
    driver_id = Column(Integer, ForeignKey("truck_drivers.id"), nullable=True)  # 対象ドライバー
    start_date = Column(Date)
    end_date = Column(Date)
    premium = Column(Float)                              # 保険料
    coverage_amount = Column(Float)                      # 保険金額
    file_path = Column(String(500))
    file_name = Column(String(200))
    # OCR読み取り結果
    ocr_insurer = Column(String(200))
    ocr_policy_number = Column(String(100))
    ocr_start_date = Column(String(50))
    ocr_end_date = Column(String(50))
    ocr_premium = Column(String(100))
    ocr_summary = Column(Text)
    ocr_raw = Column(Text)
    ocr_status = Column(String(20), default='none')
    note = Column(Text)
    tenant_id = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    truck = relationship("Truck", backref="insurances", foreign_keys=[truck_id])
    driver = relationship("TruckDriver", backref="insurances", foreign_keys=[driver_id])


class TruckAccidentRecord(Base):
    """事故履歴"""
    __tablename__ = "truck_accident_records"
    id = Column(Integer, primary_key=True)
    truck_id = Column(Integer, ForeignKey("trucks.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("truck_drivers.id"), nullable=True)  # 担当ドライバー
    accident_date = Column(Date, nullable=False)   # 事故日
    location = Column(String(300))                 # 発生場所
    description = Column(Text)                     # 事故内容
    damage_level = Column(String(20))              # 軽微/中程度/重大
    fault_ratio = Column(Integer, nullable=True)   # 過失割合（0-100）
    repair_cost = Column(Float)                    # 修理費用
    repair_completed = Column(Boolean, default=False)  # 修理完了
    note = Column(Text)
    tenant_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    truck = relationship("Truck", back_populates="accident_records")
    driver = relationship("TruckDriver", foreign_keys=[driver_id])


class TruckInspectionRecord(Base):
    """点検履歴"""
    __tablename__ = "truck_inspection_records"
    id = Column(Integer, primary_key=True)
    truck_id = Column(Integer, ForeignKey("trucks.id"), nullable=False)
    inspection_date = Column(Date, nullable=False)  # 点検日
    inspection_type = Column(String(50))            # 定期点検/車検/日常点検/その他
    inspector = Column(String(100))                 # 点検者・業者名
    result = Column(String(20))                     # 合格/要注意/不合格
    next_inspection_date = Column(Date)             # 次回点検予定日
    mileage = Column(Integer)                       # 走行距離（km）
    description = Column(Text)                      # 点検内容・所見
    cost = Column(Float)                            # 費用
    note = Column(Text)
    tenant_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    truck = relationship("Truck", back_populates="inspection_records")


class TruckAppSettings(Base):
    __tablename__ = "truck_app_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(100), nullable=False)
    tenant_id = Column(Integer, nullable=True)
    value = Column(Text)

    @classmethod
    def get(cls, db_session, key, tenant_id=None, default=None):
        if tenant_id is not None:
            # まずtenant_id指定で検索
            row = db_session.query(cls).filter_by(key=key, tenant_id=tenant_id).first()
            if row:
                return row.value
            # 見つからない場合はtenant_id=Noneのグローバル設定にフォールバック
            row = db_session.query(cls).filter_by(key=key, tenant_id=None).first()
            return row.value if row else default
        row = db_session.query(cls).filter_by(key=key).first()
        return row.value if row else default

    @classmethod
    def set(cls, db_session, key, value, tenant_id=None):
        q = db_session.query(cls).filter_by(key=key)
        if tenant_id is not None:
            q = q.filter_by(tenant_id=tenant_id)
        row = q.first()
        if row:
            row.value = value
        else:
            row = cls(key=key, value=value, tenant_id=tenant_id)
            db_session.add(row)
        db_session.commit()
