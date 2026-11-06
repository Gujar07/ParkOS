import os
import random
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models import (
    Base, Facility, ParkingSpace, CurbZone, CurbViolation, Booking, HistoricalOccupancy
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./parkos.db")

# SQLite thread connection setup
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_demo_data(db: Session):
    """Seed initial facilities, parking spaces, curb zones, bookings, and ML historical data."""
    if db.query(Facility).first():
        return  # Already seeded

    print("[ParkOS DB] Seeding demo facilities and commercial corridor data...")

    facilities_data = [
        {
            "code": "INDIRA-MLCP-01",
            "name": "Indiranagar Metro Multi-Level Car Park (MLCP)",
            "facility_type": "MLCP",
            "address": "100ft Road, near Indiranagar Metro, Bengaluru 560038",
            "latitude": 12.97836,
            "longitude": 77.64083,
            "total_spots": 35,
            "base_hourly_rate": 40.0,
            "surge_multiplier": 1.0,
            "amenities": "EV Fast Charging (60kW), Covered Parking, CCTV 24/7, Metro Walkway, Restrooms",
            "has_ev_charging": True,
            "operator_id": "OP-METRO-01",
            "floors": [
                {"name": "Ground", "slots": 8, "types": ["EV", "ACCESSIBLE", "CAR"]},
                {"name": "Floor 1", "slots": 9, "types": ["CAR"]},
                {"name": "Floor 2", "slots": 9, "types": ["CAR", "TWO_WHEELER"]},
                {"name": "Floor 3", "slots": 9, "types": ["TWO_WHEELER", "CAR"]}
            ]
        },
        {
            "code": "INDIRA-SURF-02",
            "name": "100ft Road Central Surface Lot",
            "facility_type": "SURFACE",
            "address": "Opposite 12th Main Corner, 100ft Road, Indiranagar, Bengaluru 560038",
            "latitude": 12.97210,
            "longitude": 77.64320,
            "total_spots": 20,
            "base_hourly_rate": 50.0,
            "surge_multiplier": 1.2,
            "amenities": "Prime Frontage, Automated Boom Barrier, UPI Instant Pay, Security Guard",
            "has_ev_charging": False,
            "operator_id": "OP-CENTRAL-02",
            "floors": [
                {"name": "Surface", "slots": 20, "types": ["CAR", "CAR", "TWO_WHEELER"]}
            ]
        },
        {
            "code": "INDIRA-BSMT-03",
            "name": "12th Main Gourmet District Basement Parking",
            "facility_type": "BASEMENT",
            "address": "12th Main Rd, HAL 2nd Stage, Indiranagar, Bengaluru 560038",
            "latitude": 12.97020,
            "longitude": 77.63940,
            "total_spots": 25,
            "base_hourly_rate": 60.0,
            "surge_multiplier": 1.0,
            "amenities": "Valet Drop-off, Underground Climate Control, EV AC Slow Charging (7.4kW)",
            "has_ev_charging": True,
            "operator_id": "OP-GOURMET-03",
            "floors": [
                {"name": "Basement 1", "slots": 13, "types": ["CAR", "EV"]},
                {"name": "Basement 2", "slots": 12, "types": ["CAR", "TWO_WHEELER"]}
            ]
        },
        {
            "code": "INDIRA-PLAZA-04",
            "name": "CMH Road Metro Plaza & Multi-modal Park",
            "facility_type": "MULTI_MODAL",
            "address": "CMH Road, Indiranagar, Bengaluru 560038",
            "latitude": 12.97960,
            "longitude": 77.64410,
            "total_spots": 30,
            "base_hourly_rate": 30.0,
            "surge_multiplier": 1.0,
            "amenities": "Two-Wheeler Dedicated Floor, EV Battery Swapping Station, Direct Metro Concourse",
            "has_ev_charging": True,
            "operator_id": "OP-METRO-01",
            "floors": [
                {"name": "Ground", "slots": 10, "types": ["TWO_WHEELER", "EV"]},
                {"name": "Floor 1", "slots": 10, "types": ["TWO_WHEELER"]},
                {"name": "Floor 2", "slots": 10, "types": ["CAR"]}
            ]
        },
        {
            "code": "INDIRA-PKWK-05",
            "name": "Defence Colony Park & Walk Facility",
            "facility_type": "SURFACE",
            "address": "Defence Colony Perimeter, Indiranagar, Bengaluru 560038",
            "latitude": 12.97480,
            "longitude": 77.64550,
            "total_spots": 16,
            "base_hourly_rate": 35.0,
            "surge_multiplier": 1.0,
            "amenities": "Tree Canopy Shading, Pedestrian Promenade Access, Smart Metering",
            "has_ev_charging": False,
            "operator_id": "OP-RESIDENTIAL-04",
            "floors": [
                {"name": "Surface", "slots": 16, "types": ["CAR", "TWO_WHEELER"]}
            ]
        },
        {
            "code": "INDIRA-CLUB-06",
            "name": "Indiranagar Club Annex Valet & Smart Lot",
            "facility_type": "SURFACE",
            "address": "4th Cross, 100ft Road Link, Indiranagar, Bengaluru 560038",
            "latitude": 12.97650,
            "longitude": 77.64190,
            "total_spots": 20,
            "base_hourly_rate": 45.0,
            "surge_multiplier": 1.1,
            "amenities": "Club Access, Valet Assistance, Automated Number Plate Recognition (ANPR)",
            "has_ev_charging": True,
            "operator_id": "OP-CLUB-05",
            "floors": [
                {"name": "Ground", "slots": 20, "types": ["CAR", "EV", "ACCESSIBLE"]}
            ]
        }
    ]

    created_facilities = []
    created_spaces = []

    for f_idx, fdata in enumerate(facilities_data, start=1):
        floors = fdata.pop("floors")
        facility = Facility(**fdata)
        db.add(facility)
        db.flush()
        created_facilities.append(facility)

        bay_counter = 1
        for floor_info in floors:
            floor_name = floor_info["name"]
            slots_count = floor_info["slots"]
            types = floor_info["types"]

            for s_idx in range(1, slots_count + 1):
                # Distribute space status: ~65% Available, ~25% Occupied, ~10% Reserved
                rnd = random.random()
                if rnd < 0.65:
                    status = "AVAILABLE"
                elif rnd < 0.90:
                    status = "OCCUPIED"
                else:
                    status = "RESERVED"

                space_type = types[s_idx % len(types)]
                bay_num = f"{f_idx:02d}-{floor_name[0]}{s_idx:02d}"
                sensor_id = f"ESP32-US-{facility.code}-{bay_counter:03d}"

                space = ParkingSpace(
                    facility_id=facility.id,
                    bay_number=bay_num,
                    floor=floor_name,
                    space_type=space_type,
                    status=status,
                    sensor_id=sensor_id,
                    last_status_change=datetime.utcnow() - timedelta(minutes=random.randint(5, 120))
                )
                db.add(space)
                created_spaces.append(space)
                bay_counter += 1

    db.flush()

    # Seed Curb Zones
    curb_zones_data = [
        {
            "code": "CURB-IND-01",
            "name": "100ft Rd Quick-Commerce & Delivery Hub",
            "location_desc": "100ft Road, opposite 12th Main junction, near Starbucks",
            "latitude": 12.97230,
            "longitude": 77.64335,
            "length_meters": 30.0,
            "max_dwell_minutes": 15,
            "restriction_type": "QUICK_COMMERCE_DELIVERY",
            "allowed_hours": "07:00-23:30",
            "active_regulation": "15-minute strict maximum dwell for delivery riders (Zomato/Blinkit/Zepto/Swiggy). Overstay automated e-challan ₹500.",
            "enforcement_status": "ACTIVE",
            "current_occupancy": 3,
            "capacity": 6
        },
        {
            "code": "CURB-IND-02",
            "name": "12th Main Auto-Rickshaw & Cab Pick-up Bay",
            "location_desc": "12th Main Gourmet crosswalk, outside Toit Brewpub",
            "latitude": 12.97035,
            "longitude": 77.63970,
            "length_meters": 25.0,
            "max_dwell_minutes": 3,
            "restriction_type": "PASSENGER_PICKUP",
            "allowed_hours": "24/7",
            "active_regulation": "3-minute rolling pick-up/drop-off zone only. Engine idling prohibited. ₹1,000 traffic obstruction penalty.",
            "enforcement_status": "MONITORED",
            "current_occupancy": 2,
            "capacity": 4
        },
        {
            "code": "CURB-IND-03",
            "name": "CMH Market Morning Goods Unloading Zone",
            "location_desc": "CMH Road entrance, adjacent to Metro Pillar 68",
            "latitude": 12.97980,
            "longitude": 77.64430,
            "length_meters": 40.0,
            "max_dwell_minutes": 45,
            "restriction_type": "FREIGHT_UNLOADING",
            "allowed_hours": "06:00-11:30",
            "active_regulation": "Dedicated commercial logistics & fresh produce unloading window between 06:00 and 11:30 AM. Non-commercial parking strictly prohibited.",
            "enforcement_status": "ACTIVE",
            "current_occupancy": 1,
            "capacity": 3
        }
    ]

    created_curbs = []
    for cz in curb_zones_data:
        curb = CurbZone(**cz)
        db.add(curb)
        db.flush()
        created_curbs.append(curb)

    # Seed Curb Violations
    violations_data = [
        {
            "curb_zone_id": created_curbs[0].id,
            "vehicle_plate": "KA-03-HA-8821",
            "vehicle_type": "TWO_WHEELER",
            "dwell_minutes": 32,
            "fine_amount": 500.0,
            "evidence_notes": "Exceeded 15m quick-commerce delivery dwell limit by 17 mins. Automatic camera log.",
            "timestamp": datetime.utcnow() - timedelta(minutes=45),
            "status": "ISSUED"
        },
        {
            "curb_zone_id": created_curbs[0].id,
            "vehicle_plate": "KA-01-MJ-4319",
            "vehicle_type": "COMMERCIAL_VAN",
            "dwell_minutes": 48,
            "fine_amount": 500.0,
            "evidence_notes": "Commercial parcel drop parked unattended without driver.",
            "timestamp": datetime.utcnow() - timedelta(hours=2),
            "status": "ISSUED"
        },
        {
            "curb_zone_id": created_curbs[1].id,
            "vehicle_plate": "KA-04-E-1920",
            "vehicle_type": "AUTO_RICKSHAW",
            "dwell_minutes": 14,
            "fine_amount": 1000.0,
            "evidence_notes": "Auto-rickshaw parked in 3m active passenger pickup bay causing corridor bottleneck.",
            "timestamp": datetime.utcnow() - timedelta(hours=3),
            "status": "ISSUED"
        }
    ]
    for v in violations_data:
        db.add(CurbViolation(**v))

    # Seed Bookings (Active and Past)
    sample_bookings = [
        {
            "booking_code": "POS-2026-98142",
            "facility_id": created_facilities[0].id,
            "space_id": created_spaces[0].id,
            "user_name": "Rohan Deshmukh",
            "user_email": "driver@parkos.in",
            "vehicle_number": "KA-05-MM-7840",
            "vehicle_type": "EV",
            "duration_hours": 3.0,
            "start_time": datetime.utcnow() - timedelta(minutes=30),
            "end_time": datetime.utcnow() + timedelta(hours=2, minutes=30),
            "checked_in_at": datetime.utcnow() - timedelta(minutes=25),
            "base_rate": 40.0,
            "applied_multiplier": 0.85,  # 15% green EV discount
            "total_amount": 102.0,
            "status": "CHECKED_IN",
            "qr_code_data": "PARKOS:POS-2026-98142:KA-05-MM-7840",
            "reward_credits_earned": 15
        },
        {
            "booking_code": "POS-2026-77319",
            "facility_id": created_facilities[1].id,
            "space_id": created_spaces[35].id,
            "user_name": "Priya Sharma",
            "user_email": "driver@parkos.in",
            "vehicle_number": "KA-01-AB-1204",
            "vehicle_type": "CAR",
            "duration_hours": 2.0,
            "start_time": datetime.utcnow() + timedelta(minutes=20),
            "end_time": datetime.utcnow() + timedelta(hours=2, minutes=20),
            "checked_in_at": None,
            "base_rate": 50.0,
            "applied_multiplier": 1.2,  # Surge
            "total_amount": 120.0,
            "status": "CONFIRMED",
            "qr_code_data": "PARKOS:POS-2026-77319:KA-01-AB-1204",
            "reward_credits_earned": 10
        },
        {
            "booking_code": "POS-2026-44120",
            "facility_id": created_facilities[2].id,
            "space_id": created_spaces[55].id,
            "user_name": "Vikram Sethi",
            "user_email": "vikram@example.com",
            "vehicle_number": "KA-03-TC-5021",
            "vehicle_type": "TWO_WHEELER",
            "duration_hours": 4.0,
            "start_time": datetime.utcnow() - timedelta(hours=5),
            "end_time": datetime.utcnow() - timedelta(hours=1),
            "checked_in_at": datetime.utcnow() - timedelta(hours=4, minutes=55),
            "checked_out_at": datetime.utcnow() - timedelta(hours=1, minutes=5),
            "base_rate": 60.0,
            "applied_multiplier": 0.40,  # 60% 2-wheeler concession
            "total_amount": 96.0,
            "status": "COMPLETED",
            "qr_code_data": "PARKOS:POS-2026-44120:KA-03-TC-5021",
            "reward_credits_earned": 20
        }
    ]

    for b in sample_bookings:
        db.add(Booking(**b))

    # Seed 1,440 Historical Occupancy records for ML training
    # Simulates 30 days of hourly data for facility 1
    base_time = datetime.utcnow() - timedelta(days=60)
    history_records = []
    weather_choices = ["Clear", "Clear", "Clear", "Rainy", "Monsoon"]

    for step in range(1440):
        t = base_time + timedelta(hours=step)
        hr = t.hour
        dow = t.weekday()

        # Demand pattern: lunch peak 12-14, evening peak 18-22, weekend surges
        demand_factor = 0.35
        if 12 <= hr <= 14:
            demand_factor = 0.75
        elif 18 <= hr <= 22:
            demand_factor = 0.90
        elif 0 <= hr <= 6:
            demand_factor = 0.15

        if dow >= 4:  # Friday - Sunday
            demand_factor = min(1.0, demand_factor + 0.12)

        weather = random.choice(weather_choices)
        if weather in ["Rainy", "Monsoon"]:
            demand_factor = min(0.98, demand_factor + 0.15)

        noise = random.uniform(-0.08, 0.08)
        occ_rate = max(0.05, min(1.0, demand_factor + noise))
        occupied_count = int(occ_rate * 35)

        rec = HistoricalOccupancy(
            facility_id=1,
            timestamp=t,
            hour_of_day=hr,
            day_of_week=dow,
            occupied_count=occupied_count,
            occupancy_rate=round(occ_rate, 3),
            weather=weather,
            traffic_index=round(occ_rate * 85 + random.uniform(5, 15), 1)
        )
        history_records.append(rec)

    db.bulk_save_objects(history_records)
    db.commit()
    print("[ParkOS DB] Demo data seeded successfully (6 facilities, 146 bays, 3 curb zones, 1440 ML records).")


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_demo_data(db)
    finally:
        db.close()
