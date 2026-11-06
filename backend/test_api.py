"""
Automated Comprehensive Test Suite for ParkOS Backend API.
Tests all endpoints, database operations, ML predictions, and IoT integrations.
"""
import sys
import os
from fastapi.testclient import TestClient

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app


def run_all_tests():
    print("=" * 70)
    print("[TEST] Running ParkOS Automated API Test Suite")
    print("=" * 70)
    passed = 0
    failed = 0

    with TestClient(app) as client:
        def assert_test(name, condition, details=""):
            nonlocal passed, failed
            if condition:
                passed += 1
                print(f"  [PASS] {name} {details}")
            else:
                failed += 1
                print(f"  [FAIL] {name} {details}")

        # 1. Health check
        res = client.get("/api/v1/health")
        assert_test("GET /api/v1/health", res.status_code == 200 and res.json()["status"] == "healthy")

        # 2. List parking facilities
        res = client.get("/api/v1/parking")
        assert_test("GET /api/v1/parking", res.status_code == 200 and len(res.json()) >= 6, f"(Found {len(res.json())} facilities)")
        facilities = res.json()
        first_fac_id = facilities[0]["id"]
        print(f"       Facility 1: {facilities[0]['name']} | Available: {facilities[0]['available_spots']} | ParkSure: {facilities[0]['parksure_score']}")

        # 3. Facility Details & Bay Matrix
        res = client.get(f"/api/v1/parking/{first_fac_id}")
        assert_test(f"GET /api/v1/parking/{first_fac_id}", res.status_code == 200 and len(res.json()["spaces"]) > 0, f"(Bays: {len(res.json().get('spaces', []))})")
        first_space = res.json()["spaces"][0]
        space_id = first_space["id"]

        # 4. Manual Bay Status Update
        res = client.patch(f"/api/v1/parking/spaces/{space_id}/status", json={"status": "AVAILABLE"})
        assert_test(f"PATCH /api/v1/parking/spaces/{space_id}/status", res.status_code == 200 and res.json()["status"] == "AVAILABLE")

        # 5. List Curb Zones
        res = client.get("/api/v1/curb-zones")
        assert_test("GET /api/v1/curb-zones", res.status_code == 200 and len(res.json()) >= 3, f"(Zones: {len(res.json())})")
        first_curb_id = res.json()[0]["id"]

        # 6. Update Curb Regulation
        res = client.patch(f"/api/v1/curb-zones/{first_curb_id}/regulation", json={
            "max_dwell_minutes": 20,
            "active_regulation": "Updated policy: 20-min max dwell for delivery hubs."
        })
        assert_test(f"PATCH /api/v1/curb-zones/{first_curb_id}/regulation", res.status_code == 200 and res.json()["max_dwell_minutes"] == 20)

        # 7. Report Curb Violation
        res = client.post(f"/api/v1/curb-zones/{first_curb_id}/report-violation", json={
            "vehicle_plate": "KA-04-XX-9999",
            "vehicle_type": "COMMERCIAL_VAN",
            "dwell_minutes": 45,
            "fine_amount": 750.0,
            "evidence_notes": "Unattended parcel van blocking loading curb bay."
        })
        assert_test(f"POST /api/v1/curb-zones/{first_curb_id}/report-violation", res.status_code == 200 and res.json()["vehicle_plate"] == "KA-04-XX-9999")

        # 8. Create EV Reservation with Green Discount
        booking_payload = {
            "facility_id": first_fac_id,
            "vehicle_number": "KA-01-EV-5544",
            "vehicle_type": "EV",
            "duration_hours": 2.0,
            "user_name": "Test Driver",
            "user_email": "driver@parkos.in"
        }
        res = client.post("/api/v1/bookings", json=booking_payload)
        assert_test("POST /api/v1/bookings (EV)", res.status_code == 201 and "booking_code" in res.json(), f"(Code: {res.json().get('booking_code')}, Total: INR {res.json().get('total_amount')})")
        booking_data = res.json()
        booking_code = booking_data["booking_code"]

        # 9. List My Bookings
        res = client.get("/api/v1/bookings/my-bookings?user_email=driver@parkos.in")
        assert_test("GET /api/v1/bookings/my-bookings", res.status_code == 200 and len(res.json()) > 0, f"(Found {len(res.json())} bookings)")

        # 10. Check-in
        res = client.post("/api/v1/bookings/check-in", json={"booking_code": booking_code})
        assert_test("POST /api/v1/bookings/check-in", res.status_code == 200 and res.json()["boom_barrier_status"] == "OPENED", f"(Barrier: {res.json().get('boom_barrier_status')})")

        # 11. Check-out
        res = client.post("/api/v1/bookings/check-out", json={"booking_code": booking_code})
        assert_test("POST /api/v1/bookings/check-out", res.status_code == 200 and res.json()["bay_released"] is True, f"(Receipt Total: INR {res.json().get('total_amount')})")

        # 12. Predict Availability & ParkSure Score
        res = client.post("/api/v1/predictions/predict", json={
            "facility_id": first_fac_id,
            "lead_time_minutes": 25,
            "weather": "Monsoon",
            "vehicle_type": "CAR"
        })
        pred = res.json()
        assert_test("POST /api/v1/predictions/predict", res.status_code == 200 and 0 <= pred.get("parksure_score", -1) <= 100, f"(Score: {pred.get('parksure_score')}/100, Predicted Bays: {pred.get('predicted_available_bays')})")

        # 13. Operator Analytics
        res = client.get(f"/api/v1/analytics/operator/{first_fac_id}")
        assert_test(f"GET /api/v1/analytics/operator/{first_fac_id}", res.status_code == 200 and "revenue_today" in res.json(), f"(Revenue Today: INR {res.json().get('revenue_today')})")

        # 14. City Municipal Analytics
        res = client.get("/api/v1/analytics/city")
        assert_test("GET /api/v1/analytics/city", res.status_code == 200 and res.json().get("cruising_km_reduced", 0) > 0, f"(Cruising Saved: {res.json().get('cruising_km_reduced')} km, CO2 Avoided: {res.json().get('co2_avoided_kg')} kg)")

        # 15. ESP32 Sensor Telemetry Ingestion
        res = client.post("/api/v1/iot/sensor-event", json={
            "sensor_id": f"ESP32-US-INDIRA-MLCP-01-001",
            "facility_code": "INDIRA-MLCP-01",
            "bay_number": "01-G01",
            "is_occupied": True,
            "distance_cm": 22.4,
            "battery_pct": 97
        })
        assert_test("POST /api/v1/iot/sensor-event", res.status_code == 200 and res.json().get("new_status") == "OCCUPIED", f"(New Status: {res.json().get('new_status')})")

        # 16. IoT Simulator Random Toggle
        res = client.post("/api/v1/iot/simulate-random")
        assert_test("POST /api/v1/iot/simulate-random", res.status_code == 200 and res.json().get("success") is True, f"(Toggled: {res.json().get('bay_number')} -> {res.json().get('new_status')})")

        print("=" * 70)
        print(f"[SUMMARY] Test Results: {passed} PASSED, {failed} FAILED")
        print("=" * 70)
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
