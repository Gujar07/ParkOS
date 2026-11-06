# 🅿️ ParkOS Backend - Intelligent Parking Guidance API

FastAPI-powered high-performance backend for **ParkOS: Intelligent Parking Guidance and Commercial District Management Platform** (Demonstrated in Indiranagar 100ft Road Corridor, Bengaluru).

---

## 🚀 Quick Start on Windows 11 (PowerShell)

### Step 1: Open PowerShell and Navigate to the Backend Directory
```powershell
cd "C:\Users\Shraddha Gujar\parkos\backend"
```
*(or `cd "C:\Users\Shraddha Gujar\.gemini\antigravity\scratch\parkos\backend"`)*

### Step 2: (Optional) Create & Activate Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Run the Backend Server
```powershell
python main.py
```
*Or using Uvicorn directly:*
```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 🌐 Endpoints & Interactive Documentation

Once started, the backend is available at:
- **FastAPI Interactive Swagger UI**: [http://127.0.0.1:8000/api/v1/docs](http://127.0.0.1:8000/api/v1/docs)
- **ReDoc Documentation**: [http://127.0.0.1:8000/api/v1/redoc](http://127.0.0.1:8000/api/v1/redoc)
- **Health Check**: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

---

## 🛠️ Complete REST API Reference

All routes are mounted under `/api/v1`:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | System health and SQLite database connectivity status |
| `GET` | `/api/v1/parking` | List all parking facilities with live available/occupied bay counts and ParkSure scores |
| `GET` | `/api/v1/parking/{id}` | Facility details and complete floor-wise bay matrix |
| `PATCH` | `/api/v1/parking/spaces/{id}/status` | Manually update parking space status (`AVAILABLE`, `OCCUPIED`, `RESERVED`) |
| `GET` | `/api/v1/curb-zones` | List managed curb parking zones and active dwell rules |
| `PATCH` | `/api/v1/curb-zones/{id}/regulation` | City admin update to curb space dwell rules |
| `POST` | `/api/v1/curb-zones/{id}/report-violation` | Log an overstay violation in a curb parking zone |
| `POST` | `/api/v1/bookings` | Create reservation with dynamic tariff calculation and unique booking ID |
| `GET` | `/api/v1/bookings/my-bookings` | List active and historical bookings |
| `POST` | `/api/v1/bookings/check-in` | Check in with booking code (opens boom barrier & awards credits) |
| `POST` | `/api/v1/bookings/check-out` | Check out, calculate final charges, and release bay |
| `POST` | `/api/v1/predictions/predict` | AI ParkSure™ forecast (0-100 score) using Scikit-Learn RandomForest |
| `GET` | `/api/v1/analytics/operator/{id}` | Operator revenue dashboard, dwell times, and 24-hr demand profile |
| `GET` | `/api/v1/analytics/city` | Municipal (BBMP) congestion metrics, cruising distance and CO2 saved |
| `POST` | `/api/v1/iot/sensor-event` | Accept ESP32 ultrasonic edge sensor telemetry |
| `POST` | `/api/v1/iot/simulate-random` | Live demo simulator: toggle a random bay sensor |

---

## 🔗 How to Connect Your Frontend

### 1. Configure the API Base URL
In your frontend `.env.local` or configuration file:
```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1
# or for Vite / React:
VITE_API_URL=http://127.0.0.1:8000/api/v1
```

### 2. Example Frontend Fetch Calls

#### Fetch Parking Facilities:
```typescript
const res = await fetch("http://127.0.0.1:8000/api/v1/parking");
const facilities = await res.json();
```

#### Create a Reservation:
```typescript
const res = await fetch("http://127.0.0.1:8000/api/v1/bookings", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    facility_id: 1,
    vehicle_number: "KA-01-AB-1234",
    vehicle_type: "EV", // 15% green discount applied automatically
    duration_hours: 2.0,
    user_name: "Rahul Verma",
    user_email: "driver@parkos.in"
  })
});
const booking = await res.json();
console.log("Assigned bay:", booking.bay_number, "Code:", booking.booking_code);
```

#### Predict ParkSure™ Availability Score:
```typescript
const res = await fetch("http://127.0.0.1:8000/api/v1/predictions/predict", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    facility_id: 1,
    lead_time_minutes: 30,
    weather: "Monsoon",
    vehicle_type: "CAR"
  })
});
const prediction = await res.json();
console.log("ParkSure Score:", prediction.parksure_score); // e.g. 88
```

#### Trigger Hackathon IoT Sensor Simulation:
```typescript
const res = await fetch("http://127.0.0.1:8000/api/v1/iot/simulate-random", {
  method: "POST"
});
const event = await res.json();
console.log(`Bay ${event.bay_number} toggled to ${event.new_status}`);
```
