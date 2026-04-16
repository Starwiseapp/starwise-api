from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from kerykeion import AstrologicalSubject
import traceback

app = FastAPI(title="Starwise Jyotish API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SIGN_NAMES = {
    "Ari": "Mesha (Aries)",
    "Tau": "Vrishabha (Taurus)",
    "Gem": "Mithuna (Gemini)",
    "Can": "Karka (Cancer)",
    "Leo": "Simha (Leo)",
    "Vir": "Kanya (Virgo)",
    "Lib": "Tula (Libra)",
    "Sco": "Vrishchika (Scorpio)",
    "Sag": "Dhanu (Sagittarius)",
    "Cap": "Makara (Capricorn)",
    "Aqu": "Kumbha (Aquarius)",
    "Pis": "Meena (Pisces)",
}

PLANET_NAMES = {
    "Sun":     "Surya (Sun)",
    "Moon":    "Chandra (Moon)",
    "Mercury": "Budha (Mercury)",
    "Venus":   "Shukra (Venus)",
    "Mars":    "Mangal (Mars)",
    "Jupiter": "Guru (Jupiter)",
    "Saturn":  "Shani (Saturn)",
    "Uranus":  "Uranus",
    "Neptune": "Neptune",
    "Pluto":   "Pluto",
    "True_Node": "Rahu (N.Node)",
    "Chiron":  "Ketu (S.Node)",
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
        subject = AstrologicalSubject(
            name=data.name,
            year=data.year,
            month=data.month,
            day=data.day,
            hour=data.hour,
            minute=data.minute,
            city=data.city,
            nation=data.nation,
            lat=data.lat,
            lng=data.lon,
            tz_str=data.tz,
            zodiac_type="Sidereal",
            sidereal_mode="LAHIRI",
            houses_system_identifier="W",  # Whole sign - classic Jyotish
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
                "house": p.house_name,
                "retrograde": p.retrograde,
                "in_pisces": sign_short == "Pis",
            }

        planets = [
            planet_data(subject.sun),
            planet_data(subject.moon),
            planet_data(subject.mercury),
            planet_data(subject.venus),
            planet_data(subject.mars),
            planet_data(subject.jupiter),
            planet_data(subject.saturn),
            planet_data(subject.uranus),
            planet_data(subject.neptune),
            planet_data(subject.pluto),
            planet_data(subject.true_node),
        ]

        moon_sign_short = subject.moon.sign[:3]
        natal_in_pisces = [p["jyotish_name"] for p in planets if p["in_pisces"]]

        return {
            "status": "ok",
            "name": data.name,
            "moon_sign": subject.moon.sign,
            "moon_sign_jyotish": SIGN_NAMES.get(moon_sign_short, subject.moon.sign),
            "moon_sign_short": moon_sign_short,
            "ascendant": subject.first_house.sign,
            "ascendant_jyotish": SIGN_NAMES.get(subject.first_house.sign[:3], subject.first_house.sign),
            "planets": planets,
            "natal_in_pisces": natal_in_pisces,
            "city": data.city,
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "detail": traceback.format_exc()}
