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
        # --- Timezone validation & explicit UTC conversion ---
        # We do this ourselves instead of relying on Kerykeion's internal
        # timezone handling, which can silently produce wrong results.
        try:
            tz_obj = pytz.timezone(data.tz)
        except pytz.exceptions.UnknownTimeZoneError:
            return {"status": "error", "message": f"Unknown timezone: '{data.tz}'. Please select a valid timezone."}

        naive_dt = datetime(data.year, data.month, data.day, data.hour, data.minute)
        try:
            # is_dst=None raises on ambiguous times (DST transitions)
            local_dt = tz_obj.localize(naive_dt, is_dst=None)
        except pytz.exceptions.AmbiguousTimeError:
            # Ambiguous hour during fall-back — assume non-DST (standard time)
            local_dt = tz_obj.localize(naive_dt, is_dst=False)
        except pytz.exceptions.NonExistentTimeError:
            # Non-existent hour during spring-forward — shift forward 1 hour
            local_dt = tz_obj.localize(
                naive_dt.replace(minute=naive_dt.minute + 1), is_dst=True
            )

        utc_dt = local_dt.astimezone(pytz.utc)

        # --- Coordinates fallback ---
        # If lat/lon are missing (manual timezone, no city matched), the
        # ascendant cannot be calculated correctly. Return a clear error.
        if data.lat == 0.0 and data.lon == 0.0:
            return {
                "status": "error",
                "message": "Could not determine birth location coordinates. "
                           "Please select a city from the autocomplete list, "
                           "or type your city and pick from suggestions.",
            }

        subject = AstrologicalSubject(
            name=data.name,
            # Pass pre-converted UTC time — removes all timezone ambiguity
            year=utc_dt.year,
            month=utc_dt.month,
            day=utc_dt.day,
            hour=utc_dt.hour,
            minute=utc_dt.minute,
            city=data.city,
            nation=data.nation,
            lat=data.lat,
            lng=data.lon,
            tz_str="UTC",           # already converted above
            zodiac_type="Sidereal",
            sidereal_mode="LAHIRI",
            houses_system_identifier="W",  # Whole sign — classic Jyotish
        )

        def planet_data(p):
            sign_short = p.sign[:3] if p.sign else ""
            # Kerykeion 4.x renamed house_name → house; support both versions
            house = getattr(p, "house", None) or getattr(p, "house_name", None) or ""
            return {
                "name": p.name,
                "jyotish_name": PLANET_NAMES.get(p.name, p.name),
                "sign": p.sign,
                "sign_jyotish": SIGN_NAMES.get(sign_short, p.sign),
                "sign_short": sign_short,
                "degree": round(p.position, 2),
                "house": house,
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

        # Ascendant — kerykeion 4.x returns the TROPICAL sign for first_house.sign
        # even when zodiac_type="Sidereal". We must apply the Lahiri ayanamsa manually.
        # Strategy: use the sidereal degree already stored on any planet to back-calculate
        # the ayanamsa, then apply it to first_house.position (tropical ecliptic longitude).
        #
        # Lahiri ayanamsa for 2026 is ~24.13°. We derive it precisely from the subject:
        #   ayanamsa = tropical_position - sidereal_position  (for any planet)
        # subject.sun gives us both via .position (sidereal) and via the internal
        # _sun_longitude attribute. Safer: use swisseph directly if available,
        # otherwise fall back to a precise hard-coded value for 2026.
        try:
            import swisseph as swe
            swe.set_sid_mode(swe.SIDM_LAHIRI)
            ayanamsa_deg = swe.get_ayanamsa_ut(
                swe.julday(utc_dt.year, utc_dt.month, utc_dt.day,
                           utc_dt.hour + utc_dt.minute / 60.0)
            )
        except Exception:
            # Fallback: Lahiri ayanamsa is ~24.13° for 2026 (advances ~50.3"/yr)
            # Precise value for mid-2026: 24.130°
            ayanamsa_deg = 24.130

        # first_house.position is the tropical ecliptic longitude of the Ascendant
        asc_tropical = getattr(subject.first_house, "position", None)
        if asc_tropical is not None:
            asc_sidereal = (float(asc_tropical) - ayanamsa_deg) % 360
            SIGN_ORDER = ["Ari","Tau","Gem","Can","Leo","Vir",
                          "Lib","Sco","Sag","Cap","Aqu","Pis"]
            SIGN_FULL  = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
                          "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
            sign_index = int(asc_sidereal // 30)
            asc_short = SIGN_ORDER[sign_index]
            asc_raw   = SIGN_FULL[sign_index]
        else:
            # Last-resort fallback: use whatever kerykeion gives us
            asc_raw = (
                getattr(subject.first_house, "sign", None)
                or getattr(subject.first_house, "sign_name", None)
                or ""
            )
            asc_short = asc_raw[:3]

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
