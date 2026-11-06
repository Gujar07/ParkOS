import random
import string
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Booking, Facility, ParkingSpace
from app.schemas import (
    BookingCreate, BookingResponse, CheckInRequest, CheckInResponse,
    CheckOutRequest, CheckOutResponse
)

router = APIRouter(prefix="/bookings", tags=["Bookings"])


def _generate_booking_code() -> str:
    """Generate a unique human-friendly booking code like POS-2026-X8K21."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"POS-2026-{suffix}"


def _format_booking_response(b: Booking) -> BookingResponse:
    fac_name = b.facility.name if b.facility else "Unknown Facility"
    bay_num = b.space.bay_number if b.space else "N/A"
    floor_name = b.space.floor if b.space else "Ground"

    return BookingResponse(
        id=b.id,
        booking_code=b.booking_code,
        facility_id=b.facility_id,
        facility_name=fac_name,
        space_id=b.space_id,
        bay_number=bay_num,
        floor=floor_name,
        user_name=b.user_name,
        user_email=b.user_email,
        vehicle_number=b.vehicle_number,
        vehicle_type=b.vehicle_type,
        duration_hours=b.duration_hours,
        start_time=b.start_time,
        end_time=b.end_time,
        checked_in_at=b.checked_in_at,
        checked_out_at=b.checked_out_at,
        base_rate=b.base_rate,
        applied_multiplier=b.applied_multiplier,
        total_amount=b.total_amount,
        status=b.status,
        qr_code_data=b.qr_code_data,
        reward_credits_earned=b.reward_credits_earned,
        created_at=b.created_at
    )


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(req: BookingCreate, db: Session = Depends(get_db)):
    """
    Create a new parking reservation.
    Applies dynamic pricing based on vehicle type (2W 60% off, EV 15% green discount) and lot occupancy surge.
    """
    facility = db.query(Facility).filter(Facility.id == req.facility_id).first()
    if not facility:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Facility with ID {req.facility_id} not found"
        )

    # Resolve or auto-assign space
    space = None
    if req.space_id:
        space = db.query(ParkingSpace).filter(
            ParkingSpace.id == req.space_id,
            ParkingSpace.facility_id == facility.id
        ).first()
        if not space:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parking space with ID {req.space_id} not found in this facility"
            )
        if space.status in ["OCCUPIED", "RESERVED"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Bay {space.bay_number} is currently {space.status}. Please choose an AVAILABLE bay."
            )
    else:
        # Auto-assign an available space matching vehicle type if possible, or any available
        vtype = (req.vehicle_type or "CAR").upper()
        space = db.query(ParkingSpace).filter(
            ParkingSpace.facility_id == facility.id,
            ParkingSpace.status == "AVAILABLE",
            ParkingSpace.space_type == vtype
        ).first()

        if not space:
            # Fallback to any available car/general space
            space = db.query(ParkingSpace).filter(
                ParkingSpace.facility_id == facility.id,
                ParkingSpace.status == "AVAILABLE"
            ).first()

        if not space:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No available parking bays in this facility at the moment."
            )

    # Calculate dynamic pricing
    # 1. Base rate
    base_rate = facility.base_hourly_rate
    # 2. Vehicle multiplier: 2-wheeler = 0.40, EV = 0.85, Car = 1.0
    v_mult = 1.0
    v_clean = (req.vehicle_type or "CAR").upper()
    if v_clean == "TWO_WHEELER":
        v_mult = 0.40
    elif v_clean == "EV":
        v_mult = 0.85

    # 3. Occupancy surge
    total_spaces = facility.total_spots or 1
    occupied_count = db.query(ParkingSpace).filter(
        ParkingSpace.facility_id == facility.id,
        ParkingSpace.status.in_(["OCCUPIED", "RESERVED"])
    ).count()
    occ_ratio = occupied_count / total_spaces

    surge = facility.surge_multiplier or 1.0
    if occ_ratio >= 0.90:
        surge = max(surge, 1.40)
    elif occ_ratio >= 0.80:
        surge = max(surge, 1.20)

    applied_multiplier = round(v_mult * surge, 2)
    duration = max(0.5, req.duration_hours)
    total_amount = round(base_rate * duration * applied_multiplier, 2)

    # Start and End Times
    start_dt = req.start_time if req.start_time else datetime.utcnow()
    end_dt = start_dt + timedelta(hours=duration)

    booking_code = _generate_booking_code()
    clean_vnum = req.vehicle_number.upper().strip()

    # Create Booking
    booking = Booking(
        booking_code=booking_code,
        facility_id=facility.id,
        space_id=space.id,
        user_name=req.user_name.strip() or "Driver",
        user_email=req.user_email.strip() or "driver@parkos.in",
        vehicle_number=clean_vnum,
        vehicle_type=v_clean,
        duration_hours=duration,
        start_time=start_dt,
        end_time=end_dt,
        base_rate=base_rate,
        applied_multiplier=applied_multiplier,
        total_amount=total_amount,
        status="CONFIRMED",
        qr_code_data=f"PARKOS:{booking_code}:{clean_vnum}",
        reward_credits_earned=10,
        created_at=datetime.utcnow()
    )
    db.add(booking)

    # Update Space to RESERVED
    space.status = "RESERVED"
    space.last_status_change = datetime.utcnow()

    db.commit()
    db.refresh(booking)

    return _format_booking_response(booking)


@router.get("/my-bookings", response_model=List[BookingResponse])
def get_my_bookings(
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    status: Optional[str] = Query(None, description="Filter by status: CONFIRMED, CHECKED_IN, COMPLETED, CANCELLED"),
    db: Session = Depends(get_db)
):
    """
    List user active and historical bookings.
    """
    query = db.query(Booking)
    if user_email:
        query = query.filter(Booking.user_email.ilike(user_email.strip()))
    if status:
        query = query.filter(Booking.status == status.upper())

    bookings = query.order_by(Booking.created_at.desc()).all()
    return [_format_booking_response(b) for b in bookings]


@router.get("/{booking_id}", response_model=BookingResponse)
def get_booking_by_id(booking_id: int, db: Session = Depends(get_db)):
    """
    Get a specific booking by its numeric ID.
    """
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with ID {booking_id} not found"
        )
    return _format_booking_response(b)


@router.post("/check-in", response_model=CheckInResponse)
def check_in_booking(req: CheckInRequest, db: Session = Depends(get_db)):
    """
    Check-in with booking code or ID.
    Simulates boom barrier opening, marks bay as OCCUPIED, and awards verified arrival bonus credits.
    """
    if not req.booking_code and not req.booking_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'booking_code' or 'booking_id' must be provided"
        )

    query = db.query(Booking)
    if req.booking_code:
        booking = query.filter(Booking.booking_code == req.booking_code.strip()).first()
    else:
        booking = query.filter(Booking.id == req.booking_id).first()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking record not found"
        )

    if booking.status == "CHECKED_IN":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Booking {booking.booking_code} is already checked in"
        )
    if booking.status in ["COMPLETED", "CANCELLED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot check in: booking is already {booking.status}"
        )

    # Perform check-in
    now = datetime.utcnow()
    booking.checked_in_at = now
    booking.status = "CHECKED_IN"
    booking.reward_credits_earned += 15  # Early/on-time arrival verification bonus

    # Mark space as OCCUPIED
    space = db.query(ParkingSpace).filter(ParkingSpace.id == booking.space_id).first()
    if space:
        space.status = "OCCUPIED"
        space.last_status_change = now

    db.commit()

    return CheckInResponse(
        success=True,
        message="Check-in verified successfully. Smart boom barrier OPENED.",
        booking_code=booking.booking_code,
        vehicle_number=booking.vehicle_number,
        facility_name=booking.facility.name if booking.facility else "ParkOS Facility",
        bay_number=space.bay_number if space else "Assigned Bay",
        floor=space.floor if space else "Ground",
        checked_in_at=now,
        boom_barrier_status="OPENED",
        reward_credits_earned=15
    )


@router.post("/check-out", response_model=CheckOutResponse)
def check_out_booking(req: CheckOutRequest, db: Session = Depends(get_db)):
    """
    Check-out and release parking bay.
    Calculates final dwell duration, updates space back to AVAILABLE, and returns receipt.
    """
    if not req.booking_code and not req.booking_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'booking_code' or 'booking_id' must be provided"
        )

    query = db.query(Booking)
    if req.booking_code:
        booking = query.filter(Booking.booking_code == req.booking_code.strip()).first()
    else:
        booking = query.filter(Booking.id == req.booking_id).first()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking record not found"
        )

    if booking.status == "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Booking {booking.booking_code} has already completed check-out"
        )

    now = datetime.utcnow()
    checkin_time = booking.checked_in_at or booking.start_time
    duration_min = max(5, int((now - checkin_time).total_seconds() / 60))

    booking.checked_out_at = now
    booking.status = "COMPLETED"

    # Release Space back to AVAILABLE
    space = db.query(ParkingSpace).filter(ParkingSpace.id == booking.space_id).first()
    if space:
        space.status = "AVAILABLE"
        space.last_status_change = now

    db.commit()

    return CheckOutResponse(
        success=True,
        message="Check-out completed. Bay released to live inventory.",
        booking_code=booking.booking_code,
        vehicle_number=booking.vehicle_number,
        facility_name=booking.facility.name if booking.facility else "ParkOS Facility",
        bay_number=space.bay_number if space else "Bay",
        duration_minutes=duration_min,
        total_amount=booking.total_amount,
        checked_out_at=now,
        bay_released=True,
        reward_wallet_balance=booking.reward_credits_earned + 30
    )
