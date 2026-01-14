import re
import sys
import pandas as pd
import requests
import time
import argparse
from typing import Optional, Tuple

# ---------- CONFIG ----------
OSRM_BASE = "https://map-debug.pathaointernal.com"  # URL for the OSRM API
RETRIES = 3
RETRY_BACKOFF = 1.5  # Seconds multiplier for backoff
REQUEST_TIMEOUT = 10  # Timeout per OSRM request
# ----------------------------

# Regex pattern to match coordinates in the input CSV
COORD_RE = re.compile(r"(-?\d+(?:\.\d+)?)[^0-9\-]+(-?\d+(?:\.\d+)?)")


def parse_latlon(text: str) -> Optional[Tuple[float, float]]:
    """Extracts latitude and longitude from the string (lat, lon)."""
    if pd.isna(text):
        return None
    s = str(text).strip()
    if not s:
        return None
    m = COORD_RE.search(s)
    if not m:
        return None
    lat = float(m.group(1))
    lon = float(m.group(2))
    return (lat, lon)


def latlon_to_osrm_coords(lat: float, lon: float) -> str:
    """OSRM expects lon,lat."""
    return f"{lon:.7f},{lat:.7f}"


def build_osrm_url(profile: str, lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    c1 = latlon_to_osrm_coords(lat1, lon1)
    c2 = latlon_to_osrm_coords(lat2, lon2)

    if profile == "car":
        return f"{OSRM_BASE}/pmap_car/car/{c1};{c2}?overview=false&steps=false"
    elif profile == "bike":
        return f"{OSRM_BASE}/pmap_bike/bike/{c1};{c2}?overview=false&steps=false"
    else:
        raise ValueError(f"Unsupported profile: {profile}")


def call_osrm_distance(
    session: requests.Session, profile: str,
    lat1: float, lon1: float, lat2: float, lon2: float
) -> Optional[float]:
    """Calls OSRM and returns distance in KM, or None on failure."""
    url = build_osrm_url(profile, lat1, lon1, lat2, lon2)
    backoff = 1.0

    for attempt in range(1, RETRIES + 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != "Ok":
                raise RuntimeError(f"OSRM {profile} returned code {data.get('code')}")

            routes = data.get("routes") or []
            if not routes:
                raise RuntimeError("No routes found")

            distance_m = routes[0].get("distance")
            if distance_m is None:
                raise RuntimeError("No distance field in route")

            return float(distance_m) / 1000.0

        except Exception as e:
            if attempt == RETRIES:
                print(f"[WARN] OSRM {profile} failed: {e} | url={url}", file=sys.stderr)
                return None
            time.sleep(backoff)
            backoff *= RETRY_BACKOFF


def process_routes(input_csv: str, output_csv: str):
    df = pd.read_csv(input_csv)
    print(f"[INFO] Loaded {len(df)} rows from {input_csv}")

    # Ensure Google Distance is numeric
    df["Google Distance"] = pd.to_numeric(df["Google Distance"], errors="coerce")

    # Create only the needed output columns
    df["bike"] = pd.NA
    df["car"] = pd.NA
    df["deviation_bike"] = pd.NA
    df["deviation_car"] = pd.NA

    session = requests.Session()

    for idx, row in df.iterrows():
        pickup = row.get("Pickup")
        dropoff = row.get("Dropoff")
        gd = row.get("Google Distance")

        pickup_coords = parse_latlon(pickup)
        dropoff_coords = parse_latlon(dropoff)

        if not pickup_coords or not dropoff_coords or pd.isna(gd):
            print(f"[WARN] Skipping row {idx + 1} (invalid coords or Google Distance)")
            continue

        lat1, lon1 = pickup_coords
        lat2, lon2 = dropoff_coords

        bike_distance = call_osrm_distance(session, "bike", lat1, lon1, lat2, lon2)
        if bike_distance is not None:
            df.at[idx, "bike"] = round(bike_distance, 2)
            df.at[idx, "deviation_bike"] = round(bike_distance - float(gd), 2)

        car_distance = call_osrm_distance(session, "car", lat1, lon1, lat2, lon2)
        if car_distance is not None:
            df.at[idx, "car"] = round(car_distance, 2)
            df.at[idx, "deviation_car"] = round(car_distance - float(gd), 2)

    # Output ONLY these columns, in this order
    out_cols = [
        "Name",
        "Pickup",
        "Dropoff",
        "Google Distance",
        "bike",
        "car",
        "deviation_bike",
        "deviation_car",
    ]

    # Keep only columns that exist (prevents crash if Name missing, etc.)
    out_cols = [c for c in out_cols if c in df.columns]
    out_df = df[out_cols]

    out_df.to_csv(output_csv, index=False)
    print(f"[INFO] Saved output (only selected columns) -> {output_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process route distances using OSRM")
    parser.add_argument("--input", required=True, help="Input CSV file")
    parser.add_argument("--output", required=True, help="Output CSV file")

    args = parser.parse_args()
    process_routes(args.input, args.output)
