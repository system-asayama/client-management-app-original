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
    owner_name = Column(String(100))
    user_name = Column(String(100))
    base_location = Column(String(200))
    vehicle_type = Column(String(100))
    year = Column(Integer)
    color = Column(String(50))
    vin = Column(String(100))
    engine_number = Column(String(100))
    shaken_expiry = Column(Date)
    shaken_number = Column(String(100))
    insurance_company = Column(String(200))
    insurance_policy = Column(String(100))
    insurance_expiry = Column(Date)
    photo_path = Column(String(500))
    photo_name = Column(String(200))
    shaken_doc_path = Column(String(500))
    shaken_doc_name = Column(String(200))
    insurance_doc_path = Column(String(500))
    insurance_doc_name = Column(String(200))

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
    client_id = Column(Integer, ForeignKey("truck_clients.id"), nullable=True)
    contract_amount = Column(Integer)
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
    operation_type = Column(String(20), default='driving')  # 'driving' or 'office'
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
    name = Column(String(100), nullable=False)
    kana = Column(String(100))
    contact_name = Column(String(100))
    phone = Column(String(20))
    email = Column(String(200))
    address = Column(String(300))
    client_type = Column(String(20), default='both')
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
    title = Column(String(200), nullable=False)
    contract_type = Column(String(50))
    counterparty = Column(String(200))
    start_date = Column(Date)
    end_date = Column(Date)
    amount = Column(Float)
    file_path = Column(String(500))
    file_name = Column(String(200))
    ocr_title = Column(String(200))
    ocr_counterparty = Column(String(200))
    ocr_start_date = Column(String(50))
    ocr_end_date = Column(String(50))
    ocr_amount = Column(String(100))
    ocr_summary = Column(Text)
    ocr_raw = Column(Text)
    ocr_status = Column(String(20), default='none')
    note = Column(Text)
    tenant_id = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TruckInsurance(Base):
    """保険情報管理"""
    __tablename__ = "truck_insurances"
    id = Column(Integer, primary_key=True)
    insurance_type = Column(String(50))
    insurer = Column(String(200))
    policy_number = Column(String(100))
    truck_id = Column(Integer, ForeignKey("trucks.id"), nullable=True)
    driver_id = Column(Integer, ForeignKey("truck_drivers.id"), nullable=True)
    start_date = Column(Date)
    end_date = Column(Date)
    premium = Column(Float)
    coverage_amount = Column(Float)
    file_path = Column(String(500))
    file_name = Column(String(200))
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
    driver_id = Column(Integer, ForeignKey("truck_drivers.id"), nullable=True)
    accident_date = Column(Date, nullable=False)
    location = Column(String(300))
    description = Column(Text)
    damage_level = Column(String(20))
    fault_ratio = Column(Integer, nullable=True)
    repair_cost = Column(Float)
    repair_completed = Column(Boolean, default=False)
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
    inspection_date = Column(Date, nullable=False)
    inspection_type = Column(String(50))
    inspector = Column(String(100))
    result = Column(String(20))
    next_inspection_date = Column(Date)
    mileage = Column(Integer)
    description = Column(Text)
    cost = Column(Float)
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
            row = db_session.query(cls).filter_by(key=key, tenant_id=tenant_id).first()
            if row:
                return row.value
            row = db_session.query(cls).filter_by(key=key, tenant_id=None).first()
            return row.value if row else default
        row = db_session.query(cls).filter_by(key=key).first()
        return row.value if row else default

    @classmethod
    def set(cls, db_session, key, value, tenant_id=None):
        q = db_session.query(cls).filter_by(key=key)
        if tenant_id is not None:
            q = q.filter_by(tenant_id=tenant_id)
        else:
            q = q.filter(cls.tenant_id == None)  # noqa: E711
        row = q.first()
        if row:
            row.value = value
        else:
            row = cls(key=key, value=value, tenant_id=tenant_id)
            db_session.add(row)
        db_session.commit()


class TruckInvoice(Base):
    """請求書"""
    __tablename__ = "truck_invoices"
    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(50), nullable=False)   # 請求書番号
    client_id = Column(Integer, ForeignKey("truck_clients.id"), nullable=True)
    client_name = Column(String(200))                      # 請求先名（手入力用）
    client_address = Column(String(300))                   # 請求先住所
    issue_date = Column(Date, nullable=False)              # 発行日
    due_date = Column(Date)                                # 支払期限
    period_from = Column(Date)                             # 請求対象期間（開始）
    period_to = Column(Date)                               # 請求対象期間（終了）
    subtotal = Column(Integer, default=0)                  # 小計
    tax_amount = Column(Integer, default=0)                # 消費税
    total_amount = Column(Integer, default=0)              # 合計
    tax_rate = Column(Float, default=0.10)                 # 税率
    note = Column(Text)                                    # 備考
    status = Column(String(20), default='draft')           # draft/sent/paid
    tenant_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("TruckClient", backref="invoices")
    items = relationship("TruckInvoiceItem", backref="invoice", cascade="all, delete-orphan", order_by="TruckInvoiceItem.id")


class TruckInvoiceItem(Base):
    """請求書明細"""
    __tablename__ = "truck_invoice_items"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("truck_invoices.id"), nullable=False)
    description = Column(String(300), nullable=False)      # 品目・摘要
    operation_date = Column(Date)                          # 運行日（自動集計時）
    route_name = Column(String(200))                       # ルート名（自動集計時）
    quantity = Column(Integer, default=1)                  # 数量
    unit_price = Column(Integer, default=0)                # 単価
    amount = Column(Integer, default=0)                    # 金額


class TruckSchedule(Base):
    """運行スケジュール"""
    __tablename__ = "truck_schedules"
    id = Column(Integer, primary_key=True)
    schedule_date = Column(Date, nullable=False)           # 運行予定日
    driver_id = Column(Integer, ForeignKey("truck_drivers.id"), nullable=True)
    truck_id = Column(Integer, ForeignKey("trucks.id"), nullable=True)
    route_id = Column(Integer, ForeignKey("truck_routes.id"), nullable=True)
    start_time = Column(String(5))                         # 予定出発時刻 HH:MM
    end_time = Column(String(5))                           # 予定終了時刻 HH:MM
    note = Column(Text)                                    # 備考
    tenant_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    driver = relationship("TruckDriver", backref="schedules")
    truck = relationship("Truck", backref="schedules")
    route = relationship("TruckRoute", backref="schedules")
