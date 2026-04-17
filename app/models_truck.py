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

    def to_dict(self):
        return {
            "id": self.id,
            "number": self.number,
            "name": self.name,
            "capacity": self.capacity,
            "note": self.note,
            "active": self.active,
        }


class TruckRoute(Base):
    __tablename__ = "truck_routes"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    origin = Column(String(200))
    destination = Column(String(200))
    distance_km = Column(Float)
    note = Column(Text)
    tenant_id = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "origin": self.origin,
            "destination": self.destination,
            "distance_km": self.distance_km,
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


class TruckAppSettings(Base):
    __tablename__ = "truck_app_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(100), nullable=False)
    tenant_id = Column(Integer, nullable=True)
    value = Column(Text)

    @classmethod
    def get(cls, db_session, key, tenant_id=None, default=None):
        q = db_session.query(cls).filter_by(key=key)
        if tenant_id is not None:
            q = q.filter_by(tenant_id=tenant_id)
        row = q.first()
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
