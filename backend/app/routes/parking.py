from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Facility, ParkingSpace, CurbZone, CurbViolation
from app.schemas import (
    FacilityResponse, FacilityDetailResponse, ParkingSpaceResponse,
    SpaceStatusUpdate, FacilityPricingUpdate, CurbZoneResponse,
    CurbRegulationUpdate, CurbViolationCreate, CurbViolationResponse
)

router = APIRouter(tags=["Parking & Curb Management"])


def _compute_facility_metrics(facility: Facility, db: Session) -> dict:
    """Helper to compute real-time counts and ParkSure score for a facility."""
    spaces = db.query(ParkingSpace).filter(ParkingSpace.facility_id == facility.id).all()
    total = facility.total_spots or len(spaces) or 1
    occupied = sum(1 for s in spaces if s.status == "OCCUPIED")
    reserved = sum(1 for s in spaces if s.status == "RESERVED")
    available = max(0, total - (occupied + reserved))
    occ_rate = round((occupied + reserved) / total, 3)

    # Dynamic ParkSure score based on real-time availability
    base_score = int(round((1.0 - occ_rate) * 100))
    if available >= 5:
        base_score = min(98, base_score + 6)
    parksure_score = max(10, min(98, base_score))

    return {
        "available_spots": available,
        "occupied_spots": occupied,
        "reserved_spots": reserved,
        "occupancy_rate": occ_rate,
        "parksure_score": parksure_score,
        "spaces_list": spaces
    }


# --- Parking Facilities Endpoints ---

@router.get("/parking", response_model=List[FacilityResponse])
@router.get("/facilities", response_model=List[FacilityResponse])
def list_parking_facilities(
    search: Optional[str] = Query(None, description="Search by facility name or address"),
    facility_type: Optional[str] = Query(None, description="Filter by MLCP, SURFACE, BASEMENT, MULTI_MODAL"),
    has_ev: Optional[bool] = Query(None, description="Filter facilities with EV charging"),
    db: Session = Depends(get_db)
):
    """
    List all parking facilities with live available/occupied bay counts and ParkSure scores.
    """
    query = db.query(Facility)

    if search:
        query = query.filter(
            (Facility.name.ilike(f"%{search}%")) | (Facility.address.ilike(f"%{search}%"))
        )
    if facility_type:
        query = query.filter(Facility.facility_type == facility_type.upper())
    if has_ev is not None:
        query = query.filter(Facility.has_ev_charging == has_ev)

    facilities = query.all()
    results = []

    for fac in facilities:
        metrics = _compute_facility_metrics(fac, db)
        results.append(FacilityResponse(
            id=fac.id,
            code=fac.code,
            name=fac.name,
            facility_type=fac.facility_type,
            address=fac.address,
            latitude=fac.latitude,
            longitude=fac.longitude,
            total_spots=fac.total_spots,
            base_hourly_rate=fac.base_hourly_rate,
            surge_multiplier=fac.surge_multiplier,
            amenities=fac.amenities,
            has_ev_charging=fac.has_ev_charging,
            operator_id=fac.operator_id,
            available_spots=metrics["available_spots"],
            occupied_spots=metrics["occupied_spots"],
            reserved_spots=metrics["reserved_spots"],
            occupancy_rate=metrics["occupancy_rate"],
            parksure_score=metrics["parksure_score"],
            created_at=fac.created_at
        ))

    return results


@router.get("/parking/{facility_id}", response_model=FacilityDetailResponse)
@router.get("/facilities/{facility_id}", response_model=FacilityDetailResponse)
def get_facility_details(facility_id: int, db: Session = Depends(get_db)):
    """
    Retrieve full facility profile and its complete floor-wise bay matrix.
    """
    facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Facility with ID {facility_id} not found"
        )

    metrics = _compute_facility_metrics(facility, db)

    return FacilityDetailResponse(
        id=facility.id,
        code=facility.code,
        name=facility.name,
        facility_type=facility.facility_type,
        address=facility.address,
        latitude=facility.latitude,
        longitude=facility.longitude,
        total_spots=facility.total_spots,
        base_hourly_rate=facility.base_hourly_rate,
        surge_multiplier=facility.surge_multiplier,
        amenities=facility.amenities,
        has_ev_charging=facility.has_ev_charging,
        operator_id=facility.operator_id,
        available_spots=metrics["available_spots"],
        occupied_spots=metrics["occupied_spots"],
        reserved_spots=metrics["reserved_spots"],
        occupancy_rate=metrics["occupancy_rate"],
        parksure_score=metrics["parksure_score"],
        created_at=facility.created_at,
        spaces=[ParkingSpaceResponse.model_validate(s) for s in metrics["spaces_list"]]
    )


@router.get("/bays/facility/{facility_id}", response_model=List[ParkingSpaceResponse])
def get_facility_bays(facility_id: int, db: Session = Depends(get_db)):
    """
    Get the complete live bay matrix for a facility (used by Operator deck).
    """
    facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Facility with ID {facility_id} not found"
        )
    spaces = db.query(ParkingSpace).filter(ParkingSpace.facility_id == facility_id).order_by(ParkingSpace.bay_number).all()
    return [ParkingSpaceResponse.model_validate(s) for s in spaces]


@router.patch("/parking/spaces/{space_id}/status", response_model=ParkingSpaceResponse)
@router.patch("/bays/{space_id}/status", response_model=ParkingSpaceResponse)
def update_space_status(
    space_id: int,
    req: SpaceStatusUpdate,
    db: Session = Depends(get_db)
):
    """
    Manually update a parking space status (e.g. AVAILABLE, OCCUPIED, RESERVED, OUT_OF_SERVICE).
    """
    space = db.query(ParkingSpace).filter(ParkingSpace.id == space_id).first()
    if not space:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parking space with ID {space_id} not found"
        )

    valid_statuses = ["AVAILABLE", "OCCUPIED", "RESERVED", "OUT_OF_SERVICE"]
    new_status = req.status.upper()
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{req.status}'. Must be one of: {', '.join(valid_statuses)}"
        )

    space.status = new_status
    space.last_status_change = datetime.utcnow()
    db.commit()
    db.refresh(space)
    return ParkingSpaceResponse.model_validate(space)


@router.patch("/facilities/{facility_id}/pricing", response_model=FacilityResponse)
@router.patch("/parking/{facility_id}/pricing", response_model=FacilityResponse)
def update_facility_pricing(
    facility_id: int,
    req: FacilityPricingUpdate,
    db: Session = Depends(get_db)
):
    """
    Operator deck endpoint to update base hourly tariffs and demand surge multiplier.
    """
    facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Facility with ID {facility_id} not found"
        )

    if req.base_hourly_rate is not None:
        facility.base_hourly_rate = max(10.0, req.base_hourly_rate)
    if req.surge_multiplier is not None:
        facility.surge_multiplier = max(0.5, min(3.0, req.surge_multiplier))

    db.commit()
    db.refresh(facility)
    metrics = _compute_facility_metrics(facility, db)

    return FacilityResponse(
        id=facility.id,
        code=facility.code,
        name=facility.name,
        facility_type=facility.facility_type,
        address=facility.address,
        latitude=facility.latitude,
        longitude=facility.longitude,
        total_spots=facility.total_spots,
        base_hourly_rate=facility.base_hourly_rate,
        surge_multiplier=facility.surge_multiplier,
        amenities=facility.amenities,
        has_ev_charging=facility.has_ev_charging,
        operator_id=facility.operator_id,
        available_spots=metrics["available_spots"],
        occupied_spots=metrics["occupied_spots"],
        reserved_spots=metrics["reserved_spots"],
        occupancy_rate=metrics["occupancy_rate"],
        parksure_score=metrics["parksure_score"],
        created_at=facility.created_at
    )


# --- Smart Curb Management Endpoints ---

@router.get("/curb-zones", response_model=List[CurbZoneResponse])
def list_curb_zones(db: Session = Depends(get_db)):
    """
    List all managed commercial curb zones, active dwell regulations, and live occupancy.
    """
    zones = db.query(CurbZone).all()
    results = []
    for cz in zones:
        v_count = db.query(CurbViolation).filter(CurbViolation.curb_zone_id == cz.id).count()
        results.append(CurbZoneResponse(
            id=cz.id,
            code=cz.code,
            name=cz.name,
            location_desc=cz.location_desc,
            latitude=cz.latitude,
            longitude=cz.longitude,
            length_meters=cz.length_meters,
            max_dwell_minutes=cz.max_dwell_minutes,
            restriction_type=cz.restriction_type,
            allowed_hours=cz.allowed_hours,
            active_regulation=cz.active_regulation,
            enforcement_status=cz.enforcement_status,
            current_occupancy=cz.current_occupancy,
            capacity=cz.capacity,
            violation_count=v_count,
            created_at=cz.created_at
        ))
    return results


@router.patch("/curb-zones/{curb_id}/regulation", response_model=CurbZoneResponse)
def update_curb_regulation(
    curb_id: int,
    req: CurbRegulationUpdate,
    db: Session = Depends(get_db)
):
    """
    City Admin (BBMP/BMC) endpoint to update curb zone dwell rules and policies.
    """
    zone = db.query(CurbZone).filter(CurbZone.id == curb_id).first()
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Curb zone with ID {curb_id} not found"
        )

    if req.max_dwell_minutes is not None:
        zone.max_dwell_minutes = max(1, req.max_dwell_minutes)
    if req.restriction_type is not None:
        zone.restriction_type = req.restriction_type
    if req.allowed_hours is not None:
        zone.allowed_hours = req.allowed_hours
    if req.active_regulation is not None:
        zone.active_regulation = req.active_regulation
    if req.enforcement_status is not None:
        zone.enforcement_status = req.enforcement_status

    db.commit()
    db.refresh(zone)
    v_count = db.query(CurbViolation).filter(CurbViolation.curb_zone_id == zone.id).count()

    return CurbZoneResponse(
        id=zone.id,
        code=zone.code,
        name=zone.name,
        location_desc=zone.location_desc,
        latitude=zone.latitude,
        longitude=zone.longitude,
        length_meters=zone.length_meters,
        max_dwell_minutes=zone.max_dwell_minutes,
        restriction_type=zone.restriction_type,
        allowed_hours=zone.allowed_hours,
        active_regulation=zone.active_regulation,
        enforcement_status=zone.enforcement_status,
        current_occupancy=zone.current_occupancy,
        capacity=zone.capacity,
        violation_count=v_count,
        created_at=zone.created_at
    )


@router.post("/curb-zones/{curb_id}/report-violation", response_model=CurbViolationResponse)
def report_curb_violation(
    curb_id: int,
    req: CurbViolationCreate,
    db: Session = Depends(get_db)
):
    """
    Log an overstay violation in a curb parking zone.
    """
    zone = db.query(CurbZone).filter(CurbZone.id == curb_id).first()
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Curb zone with ID {curb_id} not found"
        )

    violation = CurbViolation(
        curb_zone_id=zone.id,
        vehicle_plate=req.vehicle_plate.upper().strip(),
        vehicle_type=req.vehicle_type.upper(),
        dwell_minutes=req.dwell_minutes,
        fine_amount=req.fine_amount,
        evidence_notes=req.evidence_notes or f"Overstay of {req.dwell_minutes}m exceeding {zone.max_dwell_minutes}m rule.",
        timestamp=datetime.utcnow(),
        status="ISSUED"
    )
    db.add(violation)
    db.commit()
    db.refresh(violation)
    return CurbViolationResponse.model_validate(violation)


@router.get("/curb-zones/{curb_id}/violations", response_model=List[CurbViolationResponse])
def list_curb_violations(curb_id: int, db: Session = Depends(get_db)):
    """
    List logged violations for a specific curb zone.
    """
    violations = db.query(CurbViolation).filter(CurbViolation.curb_zone_id == curb_id).order_by(CurbViolation.timestamp.desc()).all()
    return [CurbViolationResponse.model_validate(v) for v in violations]
