from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from kerykeion import AstrologicalSubject
import traceback
import pytz
from datetime import datetime

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

SIGN_ORDER = ["Ari","Tau","Gem","Can","Leo","Vir",
              "Lib","Sco","Sag","Cap","Aqu","Pis"]
SIGN_FULL  = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
              "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]

PLANET_NAMES = {
    "Sun":      "Surya (Sun)",
    "Moon":     "Chandra (Moon)",
    "Mercury":  "Budha (Mercury)",
    "Venus":    "Shukra (Venus)",
    "Mars":     "Mangal (Mars)",
    "Jupiter":  "Guru (Jupiter)",
    "Saturn":   "Shani (Saturn)",
    "Uranus":   "Uranus",
    "Neptune":  "Neptune",
    "Pluto":    "Pluto",
    "True_Node":"Rahu (N.Node)",
    "Chiron":   "Ketu (S.Node)",
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
    return {"status": "Starwise API is running"}


@app.post("/chart")
def get_chart(data: BirthData):
    try:
        # Timezone validation and UTC conversion
        try:
            tz_obj = pytz.timezone(data.tz)
        except pytz.exceptions.UnknownTimeZoneError:
            return {"status": "error", "message": f"Unknown timezone: '{data.tz}'."}

        naive_dt = datetime(data.year, data.month, data.day, data.hour, data.minute)
        try:
            local_dt = tz_obj.localize(naive_dt, is_dst=None)
        except pytz.exceptions.AmbiguousTimeError:
            local_dt = tz_obj.localize(naive_dt, is_dst=False)
        except pytz.exceptions.NonExistentTimeError:
            local_dt = tz_obj.localize(
                naive_dt.replace(minute=naive_dt.minute + 1), is_dst=True
            )

        utc_dt = local_dt.astimezone(pytz.utc)

        if data.lat == 0.0 and data.lon == 0.0:
            return {
                "status": "error",
                "message": "Could not determine birth location. Please select a city from suggestions.",
            }

        subject = AstrologicalSubject(
            name=data.name,
            year=utc_dt.year,
            month=utc_dt.month,
            day=utc_dt.day,
            hour=utc_dt.hour,
            minute=utc_dt.minute,
            city=data.city,
            nation=data.nation,
            lat=data.lat,
            lng=data.lon,
            tz_str="UTC",
            zodiac_type="Sidereal",
            sidereal_mode="LAHIRI",
            houses_system_identifier="W",
        )

        def planet_data(p):
            raw_sign = getattr(p, "sign", "") or ""
            sign_short = raw_sign[:3]
            house = (getattr(p, "house", None)
                     or getattr(p, "house_name", None) or "")
            pos = getattr(p, "position", None)
            if pos is None:
                pos = getattr(p, "abs_pos", 0.0)
            return {
                "name": p.name,
                "jyotish_name": PLANET_NAMES.get(p.name, p.name),
                "sign": raw_sign,
                "sign_jyotish": SIGN_NAMES.get(sign_short, raw_sign),
                "sign_short": sign_short,
                "degree": round(float(pos), 2),
                "house": house,
                "retrograde": bool(getattr(p, "retrograde", False)),
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

        moon_sign_short = subject.moon.sign[:3] if subject.moon.sign else ""
        natal_in_pisces = [p["jyotish_name"] for p in planets if p["in_pisces"]]

        # Sidereal Ascendant: apply Lahiri ayanamsa to tropical first_house.position
        try:
            import swisseph as swe
            swe.set_sid_mode(swe.SIDM_LAHIRI)
            jd = swe.julday(
                utc_dt.year, utc_dt.month, utc_dt.day,
                utc_dt.hour + utc_dt.minute / 60.0
            )
            ayanamsa_deg = swe.get_ayanamsa_ut(jd)
        except Exception:
            ayanamsa_deg = 24.130  # Lahiri fallback for 2026

        asc_tropical = (
            getattr(subject.first_house, "position", None)
            or getattr(subject.first_house, "abs_pos", None)
        )

        if asc_tropical is not None:
            asc_sidereal = (float(asc_tropical) - ayanamsa_deg) % 360
            sign_index = int(asc_sidereal // 30)
            asc_short = SIGN_ORDER[sign_index]
            asc_raw   = SIGN_FULL[sign_index]
        else:
            asc_raw = (
                getattr(subject.first_house, "sign", None)
                or getattr(subject.first_house, "sign_name", None) or ""
            )
            asc_short = asc_raw[:3] if asc_raw else ""

        return {
            "status": "ok",
            "name": data.name,
            "moon_sign": subject.moon.sign,
            "moon_sign_jyotish": SIGN_NAMES.get(moon_sign_short, subject.moon.sign),
            "moon_sign_short": moon_sign_short,
            "ascendant": asc_raw,
            "ascendant_jyotish": SIGN_NAMES.get(asc_short, asc_raw),
            "planets": planets,
            "natal_in_pisces": natal_in_pisces,
            "city": data.city,
        }

    except Exception as e:
        return {"status": "error", "message": str(e), "detail": traceback.format_exc()}
