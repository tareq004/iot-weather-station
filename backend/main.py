import datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, Float, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# --- 1. Database Configuration (SQLite) ---
DATABASE_URL = "sqlite:///./weather_data.db"

# check_same_thread=False is required for SQLite in multi-threaded FastAPI apps
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Reading(Base):
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    temperature = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    pressure = Column(Float, nullable=False)
    timestamp = Column(
        DateTime, 
        default=lambda: datetime.datetime.now(datetime.timezone.utc), 
        index=True
    )

# Create tables automatically on startup
Base.metadata.create_all(bind=engine)


# --- 2. Pydantic Validation Schemas ---
class ReadingCreate(BaseModel):
    temperature: float = Field(..., example=28.5)
    humidity: float = Field(..., example=75.0)
    pressure: float = Field(..., example=1012.3)

class ReadingResponse(BaseModel):
    id: int
    temperature: float
    humidity: float
    pressure: float
    timestamp: datetime.datetime

    class Config:
        from_attributes = True

class DailyAggregate(BaseModel):
    date: str
    avg_temperature: float
    min_temperature: float
    max_temperature: float
    avg_humidity: float
    avg_pressure: float
    total_samples: int

class WeeklyAggregate(BaseModel):
    year_week: str
    avg_temperature: float
    min_temperature: float
    max_temperature: float
    avg_humidity: float
    avg_pressure: float
    total_samples: int


# --- 3. FastAPI App & Middleware ---
app = FastAPI(
    title="IoT Environmental Monitoring API", 
    version="1.0.0",
    description="Backend service for ESP32 weather telemetry & historical aggregation."
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to provide independent DB sessions per request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- 4. API Endpoints ---

# Data ingestion endpoint for ESP32
# Handles both '/api/readings/' and '/api/readings' to prevent HTTP redirect drops
@app.post("/api/readings/", response_model=ReadingResponse, status_code=status.HTTP_201_CREATED)
@app.post("/api/readings", response_model=ReadingResponse, status_code=status.HTTP_201_CREATED)
def create_reading(payload: ReadingCreate, db: Session = Depends(get_db)):
    reading = Reading(
        temperature=payload.temperature,
        humidity=payload.humidity,
        pressure=payload.pressure,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


# Fetch the single most recent record for real-time metric cards
@app.get("/api/readings/latest", response_model=Optional[ReadingResponse])
def get_latest_reading(db: Session = Depends(get_db)):
    latest = db.query(Reading).order_by(Reading.timestamp.desc()).first()
    return latest


# Fetch last N raw records for real-time charts (ordered oldest-to-newest for direct graphing)
@app.get("/api/readings", response_model=List[ReadingResponse])
def get_readings(limit: int = 50, db: Session = Depends(get_db)):
    records = db.query(Reading).order_by(Reading.timestamp.desc()).limit(limit).all()
    return records[::-1]


# Fetch Daily Aggregates (grouped by calendar day: YYYY-MM-DD)
@app.get("/api/history/daily", response_model=List[DailyAggregate])
def get_daily_history(db: Session = Depends(get_db)):
    date_group = func.strftime("%Y-%m-%d", Reading.timestamp)
    
    query = (
        db.query(
            date_group.label("date"),
            func.avg(Reading.temperature).label("avg_temperature"),
            func.min(Reading.temperature).label("min_temperature"),
            func.max(Reading.temperature).label("max_temperature"),
            func.avg(Reading.humidity).label("avg_humidity"),
            func.avg(Reading.pressure).label("avg_pressure"),
            func.count(Reading.id).label("total_samples"),
        )
        .group_by(date_group)
        .order_by(date_group.desc())
        .all()
    )

    return [
        DailyAggregate(
            date=row.date,
            avg_temperature=round(row.avg_temperature, 2),
            min_temperature=round(row.min_temperature, 2),
            max_temperature=round(row.max_temperature, 2),
            avg_humidity=round(row.avg_humidity, 2),
            avg_pressure=round(row.avg_pressure, 2),
            total_samples=row.total_samples,
        )
        for row in query
    ]


# Fetch Weekly Aggregates (grouped by Year-Week: YYYY-Www)
@app.get("/api/history/weekly", response_model=List[WeeklyAggregate])
def get_weekly_history(db: Session = Depends(get_db)):
    week_group = func.strftime("%Y-W%W", Reading.timestamp)
    
    query = (
        db.query(
            week_group.label("year_week"),
            func.avg(Reading.temperature).label("avg_temperature"),
            func.min(Reading.temperature).label("min_temperature"),
            func.max(Reading.temperature).label("max_temperature"),
            func.avg(Reading.humidity).label("avg_humidity"),
            func.avg(Reading.pressure).label("avg_pressure"),
            func.count(Reading.id).label("total_samples"),
        )
        .group_by(week_group)
        .order_by(week_group.desc())
        .all()
    )

    return [
        WeeklyAggregate(
            year_week=row.year_week,
            avg_temperature=round(row.avg_temperature, 2),
            min_temperature=round(row.min_temperature, 2),
            max_temperature=round(row.max_temperature, 2),
            avg_humidity=round(row.avg_humidity, 2),
            avg_pressure=round(row.avg_pressure, 2),
            total_samples=row.total_samples,
        )
        for row in query
    ]