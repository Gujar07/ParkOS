import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Facility(Base):
    __tablename__ = "facilities"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False)
    facility_type = Column(String(50), nullable=False, default="MLCP")  # MLCP, SURFACE, BASEMENT, MULTI_MODAL
    address = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    total_spots = Column(Integer, nullable=False, default=20)
    base_hourly_rate = Column(Float, nullable=False, default=40.0)
    surge_multiplier = Column(Float, nullable=False, default=1.0)
    amenities = Column(Text, nullable=True)  # Comma separated or JSON string
    has_ev_charging = Column(Boolean, default=False)
    operator_id = Column(String(50), default="OP-01")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    spaces = relationship("ParkingSpace", back_populates="facility", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="facility")


class ParkingSpace(Base):
    __tablename__ = "parking_spaces"

    id = Column(Integer, primary_key=True, index=True)
    facility_id = Column(Integer, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    bay_number = Column(String(50), nullable=False, index=True)
    floor = Column(String(50), nullable=False, default="Ground")
    space_type = Column(String(30), nullable=False, default="CAR")  # CAR, TWO_WHEELER, EV, ACCESSIBLE
    status = Column(String(30), nullable=False, default="AVAILABLE")  # AVAILABLE, OCCUPIED, RESERVED, OUT_OF_SERVICE
    sensor_id = Column(String(100), nullable=True, index=True)
    last_status_change = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    facility = relationship("Facility", back_populates="spaces")
    bookings = relationship("Booking", back_populates="space")


class CurbZone(Base):
    __tablename__ = "curb_zones"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False)
    location_desc = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    length_meters = Column(Float, nullable=False, default=30.0)
    max_dwell_minutes = Column(Integer, nullable=False, default=15)
    restriction_type = Column(String(50), nullable=False, default="QUICK_COMMERCE_DELIVERY")
    allowed_hours = Column(String(50), default="24/7")
    active_regulation = Column(Text, nullable=False)
    enforcement_status = Column(String(30), default="ACTIVE")  # ACTIVE, MONITORED, RESTRICTED
    current_occupancy = Column(Integer, default=0)
    capacity = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    violations = relationship("CurbViolation", back_populates="zone", cascade="all, delete-orphan")


class CurbViolation(Base):
    __tablename__ = "curb_violations"

    id = Column(Integer, primary_key=True, index=True)
    curb_zone_id = Column(Integer, ForeignKey("curb_zones.id", ondelete="CASCADE"), nullable=False)
    vehicle_plate = Column(String(50), nullable=False, index=True)
    vehicle_type = Column(String(30), nullable=False, default="TWO_WHEELER")
    dwell_minutes = Column(Integer, nullable=False)
    fine_amount = Column(Float, nullable=False, default=500.0)
    evidence_notes = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String(30), default="ISSUED")  # ISSUED, PAID, DISPUTED

    # Relationships
    zone = relationship("CurbZone", back_populates="violations")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    booking_code = Column(String(50), unique=True, index=True, nullable=False)
    facility_id = Column(Integer, ForeignKey("facilities.id"), nullable=False)
    space_id = Column(Integer, ForeignKey("parking_spaces.id"), nullable=False)
    user_name = Column(String(100), nullable=False, default="Demo Driver")
    user_email = Column(String(120), nullable=False, default="driver@parkos.in")
    vehicle_number = Column(String(30), nullable=False)
    vehicle_type = Column(String(30), nullable=False, default="CAR")  # CAR, TWO_WHEELER, EV
    duration_hours = Column(Float, nullable=False, default=2.0)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    checked_in_at = Column(DateTime, nullable=True)
    checked_out_at = Column(DateTime, nullable=True)
    base_rate = Column(Float, nullable=False, default=40.0)
    applied_multiplier = Column(Float, nullable=False, default=1.0)
    total_amount = Column(Float, nullable=False, default=80.0)
    status = Column(String(30), default="CONFIRMED")  # CONFIRMED, CHECKED_IN, COMPLETED, CANCELLED
    qr_code_data = Column(String(255), nullable=True)
    reward_credits_earned = Column(Integer, default=10)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    facility = relationship("Facility", back_populates="bookings")
    space = relationship("ParkingSpace", back_populates="bookings")


class SensorEvent(Base):
    __tablename__ = "sensor_events"

    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(String(100), nullable=False, index=True)
    facility_code = Column(String(50), nullable=False)
    bay_number = Column(String(50), nullable=False)
    is_occupied = Column(Boolean, nullable=False)
    distance_cm = Column(Float, nullable=True)
    battery_pct = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)


class HistoricalOccupancy(Base):
    __tablename__ = "historical_occupancy"

    id = Column(Integer, primary_key=True, index=True)
    facility_id = Column(Integer, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)
    hour_of_day = Column(Integer, nullable=False)
    day_of_week = Column(Integer, nullable=False)
    occupied_count = Column(Integer, nullable=False)
    occupancy_rate = Column(Float, nullable=False)
    weather = Column(String(50), default="Clear")
    traffic_index = Column(Float, default=50.0)
