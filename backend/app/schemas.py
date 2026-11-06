from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# --- Common / Health ---
class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "ParkOS Backend API"
    version: str = "1.0.0"
    timestamp: datetime
    database: str = "connected"


# --- Spaces / Bays ---
class SpaceBase(BaseModel):
    bay_number: str
    floor: str = "Ground"
    space_type: str = "CAR"
    status: str = "AVAILABLE"
    sensor_id: Optional[str] = None


class ParkingSpaceResponse(SpaceBase):
    id: int
    facility_id: int
    last_status_change: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SpaceStatusUpdate(BaseModel):
    status: str = Field(..., description="AVAILABLE, OCCUPIED, RESERVED, or OUT_OF_SERVICE")


# --- Facilities ---
class FacilityBase(BaseModel):
    code: str
    name: str
    facility_type: str = "MLCP"
    address: str
    latitude: float
    longitude: float
    total_spots: int
    base_hourly_rate: float
    surge_multiplier: float = 1.0
    amenities: Optional[str] = None
    has_ev_charging: bool = False
    operator_id: str = "OP-01"


class FacilityResponse(FacilityBase):
    id: int
    available_spots: int
    occupied_spots: int
    reserved_spots: int
    occupancy_rate: float
    parksure_score: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FacilityDetailResponse(FacilityResponse):
    spaces: List[ParkingSpaceResponse] = []


class FacilityPricingUpdate(BaseModel):
    base_hourly_rate: Optional[float] = None
    surge_multiplier: Optional[float] = None


# --- Curb Zones ---
class CurbZoneResponse(BaseModel):
    id: int
    code: str
    name: str
    location_desc: str
    latitude: float
    longitude: float
    length_meters: float
    max_dwell_minutes: int
    restriction_type: str
    allowed_hours: str
    active_regulation: str
    enforcement_status: str
    current_occupancy: int
    capacity: int
    violation_count: int = 0
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CurbRegulationUpdate(BaseModel):
    max_dwell_minutes: Optional[int] = None
    restriction_type: Optional[str] = None
    allowed_hours: Optional[str] = None
    active_regulation: Optional[str] = None
    enforcement_status: Optional[str] = None


class CurbViolationCreate(BaseModel):
    vehicle_plate: str
    vehicle_type: str = "TWO_WHEELER"
    dwell_minutes: int
    fine_amount: float = 500.0
    evidence_notes: Optional[str] = None


class CurbViolationResponse(BaseModel):
    id: int
    curb_zone_id: int
    vehicle_plate: str
    vehicle_type: str
    dwell_minutes: int
    fine_amount: float
    evidence_notes: Optional[str] = None
    timestamp: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)


# --- Bookings ---
class BookingCreate(BaseModel):
    facility_id: int
    space_id: Optional[int] = None
    user_name: str = "Driver User"
    user_email: str = "driver@parkos.in"
    vehicle_number: str
    vehicle_type: str = "CAR"  # CAR, TWO_WHEELER, EV
    duration_hours: float = 2.0
    start_time: Optional[datetime] = None


class BookingResponse(BaseModel):
    id: int
    booking_code: str
    facility_id: int
    facility_name: str
    space_id: int
    bay_number: str
    floor: str
    user_name: str
    user_email: str
    vehicle_number: str
    vehicle_type: str
    duration_hours: float
    start_time: datetime
    end_time: datetime
    checked_in_at: Optional[datetime] = None
    checked_out_at: Optional[datetime] = None
    base_rate: float
    applied_multiplier: float
    total_amount: float
    status: str
    qr_code_data: Optional[str] = None
    reward_credits_earned: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CheckInRequest(BaseModel):
    booking_code: Optional[str] = None
    booking_id: Optional[int] = None


class CheckInResponse(BaseModel):
    success: bool
    message: str
    booking_code: str
    vehicle_number: str
    facility_name: str
    bay_number: str
    floor: str
    checked_in_at: datetime
    boom_barrier_status: str = "OPENED"
    reward_credits_earned: int = 15


class CheckOutRequest(BaseModel):
    booking_code: Optional[str] = None
    booking_id: Optional[int] = None


class CheckOutResponse(BaseModel):
    success: bool
    message: str
    booking_code: str
    vehicle_number: str
    facility_name: str
    bay_number: str
    duration_minutes: int
    total_amount: float
    checked_out_at: datetime
    bay_released: bool = True
    reward_wallet_balance: int = 45


# --- Predictions ---
class PredictionRequest(BaseModel):
    facility_id: int
    lead_time_minutes: int = 30
    arrival_time: Optional[datetime] = None
    day_of_week: Optional[int] = None  # 0 = Monday, 6 = Sunday
    weather: Optional[str] = "Clear"  # Clear, Rainy, Monsoon
    vehicle_type: Optional[str] = "CAR"


class ContributingFactor(BaseModel):
    factor: str
    impact: str  # POSITIVE, NEUTRAL, NEGATIVE
    detail: str


class PredictionResponse(BaseModel):
    facility_id: int
    facility_name: str
    parksure_score: int
    predicted_occupancy_rate: float
    predicted_available_bays: int
    confidence_score: float
    recommended_action: str
    arrival_time_formatted: str
    contributing_factors: List[ContributingFactor] = []


# --- Analytics ---
class HourlyProfileItem(BaseModel):
    hour: int
    time_label: str
    occupancy_pct: float
    revenue: float


class VehicleTypeShare(BaseModel):
    vehicle_type: str
    percentage: float
    count: int


class OperatorAnalyticsResponse(BaseModel):
    operator_id: str
    facility_id: int
    facility_name: str
    revenue_today: float
    revenue_week: float
    revenue_month: float
    current_occupancy_rate: float
    peak_hours: str
    avg_dwell_minutes: int
    vehicle_breakdown: List[VehicleTypeShare]
    hourly_occupancy_profile: List[HourlyProfileItem]
    pricing_recommendation: str


class CityAnalyticsResponse(BaseModel):
    district_name: str
    total_facilities: int
    total_capacity: int
    current_citywide_occupancy: float
    congestion_index: int
    cruising_km_reduced: float
    fuel_saved_liters: float
    co2_avoided_kg: float
    curb_compliance_rate: float
    total_violations_today: int
    fines_collected_inr: float
    active_commercial_curbs: int


# --- IoT Sensor Integration ---
class SensorEventRequest(BaseModel):
    sensor_id: str
    facility_code: str
    bay_number: str
    is_occupied: bool
    distance_cm: Optional[float] = None
    battery_pct: Optional[int] = None
    timestamp: Optional[datetime] = None


class SensorEventResponse(BaseModel):
    success: bool
    message: str
    sensor_id: str
    facility_code: str
    bay_number: str
    new_status: str
    facility_total_spots: int
    facility_available_spots: int
    facility_occupied_spots: int


class SimulateRandomResponse(BaseModel):
    success: bool
    message: str
    facility_code: str
    facility_name: str
    bay_number: str
    previous_status: str
    new_status: str
    sensor_id: Optional[str] = None
    facility_available_spots: int
    facility_occupied_spots: int
