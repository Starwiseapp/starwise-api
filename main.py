https://starwise-api.onrender.comfrom fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from kerykeion import AstrologicalSubjectFactory
from datetime import datetime
import pytz
import traceback

app = FastAPI(title="Starwise Jyotish API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SIGN_NAMES = {
    "Ari": "Mesha (Aries)",       "Tau": "Vrishabha (Taurus)",
    "Gem": "Mithuna (Gemini)",    "Can": "Karka (Cancer)",
    "Leo": "Simha (Leo)",         "Vir": "Kanya (Virgo)",
    "Lib": "Tula (Libra)",        "Sco": "Vrishchika (Scorpio)",
    "Sag": "Dhanu (Sagittarius)", "Cap": "Makara (Capricorn)",
    "Aqu": "Kumbha (Aquarius)",   "Pis": "Meena (Pisces)",
}

PLANET_NAMES = {
    "Sun":       "Surya (Sun)",
    "Moon":      "Chandra (Moon)",
    "Mercury":   "Budha (Mercury)",
    "Venus":     "Shukra (Venus)",
    "Mars":      "Mangal (Mars)",
    "Jupiter":   "Guru (Jupiter)",
    "Saturn":    "Shani (Saturn)",
    "Uranus":    "Uranus",
    "Neptune":   "Neptune",
    "Pluto":     "Pluto",
    "True_Node": "Rahu (N.Node)",
    "Chiron":    "Ketu (S.Node)",
}

class BirthData(BaseModel):
    name: str
    year: int
    month: int
    day: int
    hour: int
    minute: int
    city: str
    nation: str
    lat: float
    lon: float
    tz: str

@app.get("/")
def root():
    return {"status": "Starwise API is running ✨"}

@app.post("/chart")
def get_chart(data: BirthData):
    try:
        # ── Convert local birth time → UTC ──────────────────────────
        # The user gives us their LOCAL birth time + timezone.
        # Kerykeion needs the LOCAL time AND tz_str — it handles the
        # UTC conversion internally, but we must make sure we pass the
        # correct local wall-clock time, not accidentally double-convert.
        # We validate the timezone is real and build a tz-aware datetime
        # so any invalid tz string raises a clear error early.
        try:
            tz_info = pytz.timezone(data.tz)
        except pytz.exceptions.UnknownTimeZoneError:
            return {"status": "error", "message": f"Unknown timezone: {data.tz}"}

        # Create a timezone-aware datetime for validation only
        local_dt = tz_info.localize(
            datetime(data.year, data.month, data.day, data.hour, data.minute)
        )
        # Convert to UTC so we can log/verify, but pass LOCAL time to Kerykeion
        utc_dt = local_dt.astimezone(pytz.utc)

        # ── Build the chart ─────────────────────────────────────────
        # Pass LOCAL time + tz_str — Kerykeion handles DST & UTC offset
        subject = AstrologicalSubjectFactory.from_birth_data(
            name=data.name,
            year=data.year,
            month=data.month,
            day=data.day,
            hour=data.hour,
            minute=data.minute,
            lng=data.lon,
            lat=data.lat,
            tz_str=data.tz,
            zodiac_type="Sidereal",
            sidereal_mode="LAHIRI",
            houses_system_identifier="W",  # Whole sign — classic Parashari
            online=False,
        )

        def planet_data(p):
            sign_short = p.sign[:3] if p.sign else ""
            return {
                "name": p.name,
                "jyotish_name": PLANET_NAMES.get(p.name, p.name),
                "sign": p.sign,
                "sign_jyotish": SIGN_NAMES.get(sign_short, p.sign),
                "sign_short": sign_short,
                "degree": round(p.position, 2),
                "house": str(p.house_name) if hasattr(p, "house_name") else "",
                "retrograde": bool(p.retrograde),
                "in_pisces": sign_short == "Pis",
            }

        planets = []
        for attr in ["sun", "moon", "mercury", "venus", "mars", "jupiter",
                     "saturn", "uranus", "neptune", "pluto", "true_node"]:
            try:
                planets.append(planet_data(getattr(subject, attr)))
            except Exception:
                pass

        moon_sign_short  = subject.moon.sign[:3]
        natal_in_pisces  = [p["jyotish_name"] for p in planets if p["in_pisces"]]
        asc_sign         = subject.first_house.sign if hasattr(subject, "first_house") else ""
        asc_short        = asc_sign[:3] if asc_sign else ""

        return {
            "status": "ok",
            "name": data.name,
            "moon_sign":          subject.moon.sign,
            "moon_sign_jyotish":  SIGN_NAMES.get(moon_sign_short, subject.moon.sign),
            "moon_sign_short":    moon_sign_short,
            "ascendant":          asc_sign,
            "ascendant_jyotish":  SIGN_NAMES.get(asc_short, asc_sign),
            "planets":            planets,
            "natal_in_pisces":    natal_in_pisces,
            "city":               data.city,
            # Debug info so you can verify in the browser console
            "debug": {
                "local_time": local_dt.isoformat(),
                "utc_time":   utc_dt.isoformat(),
                "timezone":   data.tz,
                "lat":        data.lat,
                "lon":        data.lon,
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "detail": traceback.format_exc()
        }
