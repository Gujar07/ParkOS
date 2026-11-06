import random
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Facility, ParkingSpace, SensorEvent
from app.schemas import (
    SensorEventRequest, SensorEventResponse, SimulateRandomResponse
)

router = APIRouter(prefix="/iot", tags=["IoT & Edge Sensors"])


@router.post("/sensor-event", response_model=SensorEventResponse)
def ingest_sensor_event(req: SensorEventRequest, db: Session = Depends(get_db)):
    """
    Ingest ultrasonic edge sensor telemetry from ESP32 / Arduino / Raspberry Pi nodes.
    Updates bay occupancy and recalculates live facility inventory in real-time.
    """
    # Find space by facility code and bay number, or by sensor_id
    facility = db.query(Facility).filter(Facility.code == req.facility_code.strip()).first()

    space = None
    if facility:
        space = db.query(ParkingSpace).filter(
            ParkingSpace.facility_id == facility.id,
            ParkingSpace.bay_number == req.bay_number.strip()
        ).first()

    if not space:
        # Try finding by sensor_id
        space = db.query(ParkingSpace).filter(ParkingSpace.sensor_id == req.sensor_id.strip()).first()
        if space and not facility:
            facility = space.facility

    if not space or not facility:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parking space not found for facility '{req.facility_code}' bay '{req.bay_number}' (Sensor: {req.sensor_id})"
        )

    # Determine status
    new_status = "OCCUPIED" if req.is_occupied else "AVAILABLE"
    space.status = new_status
    space.last_status_change = datetime.utcnow()

    # Log telemetry event
    evt = SensorEvent(
        sensor_id=req.sensor_id,
        facility_code=facility.code,
        bay_number=space.bay_number,
        is_occupied=req.is_occupied,
        distance_cm=req.distance_cm,
        battery_pct=req.battery_pct,
        timestamp=req.timestamp or datetime.utcnow()
    )
    db.add(evt)
    db.commit()

    # Calculate updated counts
    spaces = db.query(ParkingSpace).filter(ParkingSpace.facility_id == facility.id).all()
    total = facility.total_spots or len(spaces)
    occupied = sum(1 for s in spaces if s.status in ["OCCUPIED", "RESERVED"])
    available = max(0, total - occupied)

    return SensorEventResponse(
        success=True,
        message=f"Bay {space.bay_number} status updated to {new_status} via ESP32 sensor telemetry",
        sensor_id=req.sensor_id,
        facility_code=facility.code,
        bay_number=space.bay_number,
        new_status=new_status,
        facility_total_spots=total,
        facility_available_spots=available,
        facility_occupied_spots=occupied
    )


@router.post("/simulate-random", response_model=SimulateRandomResponse)
def simulate_random_sensor(
    facility_code: Optional[str] = Query(None, description="Optional facility code filter"),
    db: Session = Depends(get_db)
):
    """
    Hackathon live demo simulator: randomly toggles an ultrasonic bay sensor state
    and demonstrates instant reactive inventory updates across the platform.
    """
    query = db.query(ParkingSpace)
    if facility_code:
        facility = db.query(Facility).filter(Facility.code == facility_code.strip()).first()
        if facility:
            query = query.filter(ParkingSpace.facility_id == facility.id)

    spaces = query.all()
    if not spaces:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No parking spaces available to simulate"
        )

    chosen_space = random.choice(spaces)
    prev_status = chosen_space.status

    # Toggle status
    if prev_status == "AVAILABLE":
        new_status = "OCCUPIED"
        is_occ = True
        dist = random.uniform(15.0, 35.0)  # vehicle detected close to sensor
    else:
        new_status = "AVAILABLE"
        is_occ = False
        dist = random.uniform(180.0, 240.0)  # bay clear to floor

    chosen_space.status = new_status
    chosen_space.last_status_change = datetime.utcnow()

    # Log telemetry
    fac = chosen_space.facility
    evt = SensorEvent(
        sensor_id=chosen_space.sensor_id or f"ESP32-SIM-{chosen_space.id}",
        facility_code=fac.code if fac else "DEMO",
        bay_number=chosen_space.bay_number,
        is_occupied=is_occ,
        distance_cm=round(dist, 1),
        battery_pct=random.randint(85, 100),
        timestamp=datetime.utcnow()
    )
    db.add(evt)
    db.commit()

    # Recalculate facility metrics
    all_fac_spaces = db.query(ParkingSpace).filter(ParkingSpace.facility_id == fac.id).all()
    total = fac.total_spots or len(all_fac_spaces)
    occupied = sum(1 for s in all_fac_spaces if s.status in ["OCCUPIED", "RESERVED"])
    available = max(0, total - occupied)

    return SimulateRandomResponse(
        success=True,
        message=f"Live simulation: Bay {chosen_space.bay_number} toggled from {prev_status} -> {new_status}",
        facility_code=fac.code if fac else "DEMO",
        facility_name=fac.name if fac else "Demo Facility",
        bay_number=chosen_space.bay_number,
        previous_status=prev_status,
        new_status=new_status,
        sensor_id=chosen_space.sensor_id,
        facility_available_spots=available,
        facility_occupied_spots=occupied
    )
