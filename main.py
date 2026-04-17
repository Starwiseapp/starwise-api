from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from kerykeion import AstrologicalSubject
import traceback
import pytz
import math
import os
import requests as http_req
from datetime import datetime

app = FastAPI(title="Starwise Jyotish API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── HubSpot ──────────────────────────────────────────────────────────────────
# Set HS_ACCESS_TOKEN as an environment variable in Render.
# Never hard-code the token here.
HS_ACCESS_TOKEN = os.environ.get("HS_ACCESS_TOKEN", "")
HS_API_BASE = "https://api.hubapi.com"


def upsert_hubspot_contact(props: dict):
    """
    Create or update a HubSpot contact by email (server-side, non-blocking).
    Runs inside a FastAPI BackgroundTask so it never delays the chart response.
    """
    if not HS_ACCESS_TOKEN:
        return
    email = props.get("email", "").strip()
    if not email:
        return

    headers = {
        "Authorization": f"Bearer {HS_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        # 1. Try to create the contact
        r = http_req.post(
            f"{HS_API_BASE}/crm/v3/objects/contacts",
            headers=headers,
            json={"properties": props},
            timeout=10,
        )

        if r.status_code == 409:
            # Contact already exists → update by email
            http_req.patch(
                f"{HS_API_BASE}/crm/v3/objects/contacts/{email}",
                headers=headers,
                params={"idProperty": "email"},
                json={"properties": props},
                timeout=10,
            )
        elif not r.ok:
            # Log any unexpected errors (visible in Render logs)
            print(f"[HubSpot] Error {r.status_code}: {r.text}")

    except Exception as e:
        print(f"[HubSpot] Exception: {e}")


# ── Astrology constants ───────────────────────────────────────────────────────

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


def julian_day(year, month, day, hour_decimal):
    """Julian Day Number for a UTC datetime."""
    y, m = year, month
    if m <= 2:
        y -= 1
        m += 12
    A = int(y / 100)
    B = 2 - A + int(A / 4)
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day + B - 1524.5 + hour_decimal / 24.0


def lahiri_ayanamsa(jd):
    """Lahiri ayanamsa in degrees for a given Julian Day."""
    # Precise Lahiri: 22°27'37.76" at JD 2415020.0 (J1900), rate 50.2564"/year
    return 22.4605 + (jd - 2415020.0) * (50.2564 / 3600.0 / 365.25)


def sidereal_ascendant(utc_dt, lat, lon):
    """
    Calculate the sidereal (Lahiri) Ascendant for given UTC datetime and location.

    Uses the standard Placidus/Koch ascending point formula with proper
    quadrant correction, then subtracts Lahiri ayanamsa.

    Verified correct for: 15 Feb 1985 02:10 AM Luhansk (48.57N 39.34E, UTC+3)
    -> Scorpio 5.88° Lagna.
    """
    jd = julian_day(utc_dt.year, utc_dt.month, utc_dt.day,
                    utc_dt.hour + utc_dt.minute / 60.0)

    # Greenwich Mean Sidereal Time → Local Sidereal Time (RAMC)
    gmst = (280.46061837 + 360.98564724 * (jd - 2451545.0)) % 360
    ramc = (gmst + lon) % 360  # degrees

    # Obliquity of the ecliptic
    T = (jd - 2451545.0) / 36525.0
    eps = 23.439291111 - 0.013004167 * T  # degrees
    eps_r = math.radians(eps)
    lat_r = math.radians(lat)
    ramc_r = math.radians(ramc)

    # Tropical Ascendant — atan with quadrant correction
    raw = math.atan(
        -math.cos(ramc_r) /
        (math.sin(ramc_r) * math.cos(eps_r) + math.tan(lat_r) * math.sin(eps_r))
    )
    asc_tropical = math.degrees(raw)
    if 0 <= ramc < 180:
        asc_tropical += 180
    asc_tropical %= 360

    # Lahiri ayanamsa → sidereal Ascendant
    ayanamsa = lahiri_ayanamsa(jd)
    asc_sidereal = (asc_tropical - ayanamsa) % 360

    sign_index = int(asc_sidereal // 30)
    return {
        "sign_short": SIGN_ORDER[sign_index],
        "sign_full":  SIGN_FULL[sign_index],
        "degree":     round(asc_sidereal % 30, 2),
        "ayanamsa":   round(ayanamsa, 4),
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
    email: Optional[str] = ""
    lang: Optional[str] = "en"


@app.get("/")
def root():
    return {"status": "Starwise API is running ✨"}


@app.post("/chart")
def get_chart(data: BirthData, background_tasks: BackgroundTasks):
    try:
        # --- Timezone → UTC ---
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

        # --- Kerykeion for planets only (not ascendant) ---
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
            house = getattr(p, "house", None) or getattr(p, "house_name", None) or ""
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
        moon_sign_jyotish = SIGN_NAMES.get(moon_sign_short, subject.moon.sign)
        natal_in_pisces = [p["jyotish_name"] for p in planets if p["in_pisces"]]

        # --- Sidereal Ascendant (our own calculation — correct quadrant) ---
        asc = sidereal_ascendant(utc_dt, data.lat, data.lon)
        asc_short = asc["sign_short"]
        asc_raw   = asc["sign_full"]

        # --- HubSpot: upsert contact in background (non-blocking) ---
        if data.email:
            hs_props = {
                "email":              data.email.strip(),
                "firstname":          data.name,
                "city":               data.city,
                "birth_date__time":   f"{data.year}-{data.month:02d}-{data.day:02d} {data.hour:02d}:{data.minute:02d}",
                "preferred_language": (data.lang or "en").upper(),
                "source_website":     "Starwise",
                "moon_sign":          moon_sign_jyotish,
            }
            background_tasks.add_task(upsert_hubspot_contact, hs_props)

        return {
            "status": "ok",
            "name": data.name,
            "moon_sign": subject.moon.sign,
            "moon_sign_jyotish": moon_sign_jyotish,
            "moon_sign_short": moon_sign_short,
            "ascendant": asc_raw,
            "ascendant_jyotish": SIGN_NAMES.get(asc_short, asc_raw),
            "planets": planets,
            "natal_in_pisces": natal_in_pisces,
            "city": data.city,
        }

    except Exception as e:
        return {"status": "error", "message": str(e), "detail": traceback.format_exc()}
