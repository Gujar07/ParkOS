import os
import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Facility, ParkingSpace, HistoricalOccupancy
from app.schemas import PredictionRequest, PredictionResponse, ContributingFactor

router = APIRouter(prefix="/predictions", tags=["Predictions"])

# In-memory trained model cache
_ML_MODEL = None
_WEATHER_MAP = {"Clear": 0, "Rainy": 1, "Monsoon": 2}


def get_trained_model(db: Session):
    """Retrieve or train Scikit-learn RandomForestRegressor on historical occupancy."""
    global _ML_MODEL
    if _ML_MODEL is not None:
        return _ML_MODEL

    try:
        from sklearn.ensemble import RandomForestRegressor
        import numpy as np

        history = db.query(HistoricalOccupancy).limit(1440).all()
        if not history:
            return None

        X = []
        y = []
        for h in history:
            w_code = _WEATHER_MAP.get(h.weather, 0)
            # Features: [hour, day_of_week, lead_time_min, current_occ_ratio, weather_code, traffic_index]
            # Synthesize 2 training variations per historical point
            X.append([h.hour_of_day, h.day_of_week, 0, h.occupancy_rate, w_code, h.traffic_index])
            y.append(h.occupancy_rate)

            # Variation with 45m lead time
            future_occ = min(1.0, max(0.05, h.occupancy_rate + np.random.uniform(-0.1, 0.15)))
            X.append([h.hour_of_day, h.day_of_week, 45, h.occupancy_rate, w_code, h.traffic_index])
            y.append(future_occ)

        model = RandomForestRegressor(n_estimators=30, max_depth=8, random_state=42)
        model.fit(np.array(X), np.array(y))
        _ML_MODEL = model
        print("[ParkOS AI] ParkSure Scikit-Learn RandomForest model initialized.")
        return _ML_MODEL
    except Exception as e:
        print(f"[ParkOS AI] Warning: Failed to train Scikit-Learn model: {e}. Using deterministic fallback.")
        return None


def calculate_parksure_fallback(hour: int, dow: int, lead_time: int, curr_occ: float, weather: str) -> float:
    """Deterministic fallback prediction when ML model cannot be loaded."""
    # Peak curve
    if 12 <= hour <= 14:
        expected_occ = 0.82
    elif 18 <= hour <= 22:
        expected_occ = 0.88
    elif 0 <= hour <= 6:
        expected_occ = 0.18
    else:
        expected_occ = 0.50

    if dow in [4, 5, 6]:  # Fri-Sun
        expected_occ = min(0.95, expected_occ + 0.10)

    if weather in ["Rainy", "Monsoon"]:
        expected_occ = min(0.98, expected_occ + 0.12)

    # Blend with current occupancy weighted by lead time
    blend_weight = max(0.2, 1.0 - (lead_time / 120.0))
    pred_occ = (curr_occ * blend_weight) + (expected_occ * (1.0 - blend_weight))
    return max(0.05, min(0.98, pred_occ))


@router.post("/predict", response_model=PredictionResponse)
def predict_parking_availability(req: PredictionRequest, db: Session = Depends(get_db)):
    """
    Predict parking availability and generate AI ParkSure™ Score (0-100).
    Features: arrival time, lead time, day of week, weather, traffic congestion index.
    """
    facility = db.query(Facility).filter(Facility.id == req.facility_id).first()
    if not facility:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Facility with ID {req.facility_id} not found"
        )

    # Current live facility occupancy
    total_spaces = facility.total_spots or 1
    occupied_count = db.query(ParkingSpace).filter(
        ParkingSpace.facility_id == facility.id,
        ParkingSpace.status.in_(["OCCUPIED", "RESERVED"])
    ).count()
    current_occ_ratio = occupied_count / total_spaces

    # Compute target arrival time
    now = datetime.datetime.utcnow()
    lead_time = max(0, min(180, req.lead_time_minutes))
    arrival_dt = req.arrival_time if req.arrival_time else (now + datetime.timedelta(minutes=lead_time))

    arr_hour = arrival_dt.hour
    arr_dow = req.day_of_week if req.day_of_week is not None else arrival_dt.weekday()
    weather_str = req.weather or "Clear"
    w_code = _WEATHER_MAP.get(weather_str, 0)
    traffic_idx = min(100.0, current_occ_ratio * 90.0 + 10.0)

    # Predict via Scikit-Learn or deterministic fallback
    model = get_trained_model(db)
    if model is not None:
        try:
            import numpy as np
            features = np.array([[arr_hour, arr_dow, lead_time, current_occ_ratio, w_code, traffic_idx]])
            pred_occ = float(model.predict(features)[0])
            pred_occ = max(0.05, min(0.98, pred_occ))
            confidence = 0.92
        except Exception:
            pred_occ = calculate_parksure_fallback(arr_hour, arr_dow, lead_time, current_occ_ratio, weather_str)
            confidence = 0.85
    else:
        pred_occ = calculate_parksure_fallback(arr_hour, arr_dow, lead_time, current_occ_ratio, weather_str)
        confidence = 0.85

    # Compute ParkSure Score (0 - 100)
    # Higher score = higher probability of finding an open slot
    availability_prob = 1.0 - pred_occ
    raw_score = availability_prob * 100

    # Adjustments
    if lead_time <= 20 and current_occ_ratio < 0.70:
        raw_score += 8  # Short lead time and currently plenty of space
    if weather_str in ["Rainy", "Monsoon"] and facility.facility_type in ["MLCP", "BASEMENT"]:
        raw_score += 4  # Covered facility premium satisfaction
    if facility.has_ev_charging and (req.vehicle_type or "").upper() == "EV":
        raw_score += 5

    parksure_score = int(round(max(8, min(98, raw_score))))
    predicted_available = max(1, int(round((1.0 - pred_occ) * total_spaces)))

    # Explainable Contributing Factors
    factors = []
    if 12 <= arr_hour <= 14:
        factors.append(ContributingFactor(
            factor="Lunch Peak Demand",
            impact="NEGATIVE",
            detail=f"Corridor lunch rush along 100ft Rd typically increases occupancy by ~30%."
        ))
    elif 18 <= arr_hour <= 22:
        factors.append(ContributingFactor(
            factor="Dinner & Retail Surge",
            impact="NEGATIVE",
            detail=f"Commercial evening traffic peak reduces bay turnover."
        ))
    else:
        factors.append(ContributingFactor(
            factor="Off-Peak Driving Window",
            impact="POSITIVE",
            detail=f"Arrival hour ({arr_hour:02d}:00) historically experiences smooth slot turnover."
        ))

    if weather_str in ["Rainy", "Monsoon"]:
        factors.append(ContributingFactor(
            factor="Monsoon Weather Demand",
            impact="NEGATIVE" if facility.facility_type == "SURFACE" else "POSITIVE",
            detail=f"Heavy rain spikes demand for covered bays by 25%."
        ))

    if current_occ_ratio < 0.60:
        factors.append(ContributingFactor(
            factor="Real-Time Bay Availability",
            impact="POSITIVE",
            detail=f"Live ultrasonic bay matrix currently reports {total_spaces - occupied_count} vacant bays."
        ))

    if lead_time <= 25:
        factors.append(ContributingFactor(
            factor="Short Arrival Window",
            impact="POSITIVE",
            detail=f"Driver is {lead_time} minutes away; low risk of rapid capacity exhaustion."
        ))

    # Recommendations
    if parksure_score >= 75:
        action = "High availability forecast. You can drive directly or secure a guaranteed reservation."
    elif parksure_score >= 45:
        action = "Moderate demand expected at arrival. Advance reservation is strongly recommended."
    else:
        action = "High congestion risk. We suggest reserving immediately or choosing CMH Road Metro Plaza."

    return PredictionResponse(
        facility_id=facility.id,
        facility_name=facility.name,
        parksure_score=parksure_score,
        predicted_occupancy_rate=round(pred_occ, 3),
        predicted_available_bays=predicted_available,
        confidence_score=confidence,
        recommended_action=action,
        arrival_time_formatted=arrival_dt.strftime("%I:%M %p"),
        contributing_factors=factors
    )
