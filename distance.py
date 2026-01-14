import re
import os
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple, Optional

import pandas as pd
import requests
from tqdm import tqdm

# ---------- CONFIG ----------

OSRM_BASE = "https://map-debug.pathaointernal.com"  # we'll add /pmap_car/car or /pmap_bike/bike
SAVE_EVERY = 50                             # save every N processed rows
RETRIES = 3
RETRY_BACKOFF = 1.5                         # seconds multiplier
REQUEST_TIMEOUT = 10                        # seconds per OSRM request
# ----------------------------

COORD_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)[^0-9\-]+(-?\d+(?:\.\d+)?)"
)

def is_empty_coord(cell) -> bool:
    if pd.isna(cell):
        return True
    s = str(cell).strip().lower()
    if s == "":
        return True
    if s in {"na", "n/a", "none", "null", "nan", "-"}:
        return True
    return False

def parse_latlon(text: str) -> Optional[Tuple[float, float]]:
    if pd.isna(text):
        return None
    s = str(text).strip()
    if not s:
        return None
    m = COORD_RE.search(s)
    if not m:
        return None
    a = float(m.group(1))
    b = float(m.group(2))
    return (a, b)

def latlon_to_osrm_coords(lat: float, lon: float) -> str:
    return f"{lon:.7f},{lat:.7f}"

def build_osrm_url(profile: str, lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    c1 = latlon_to_osrm_coords(lat1, lon1)
    c2 = latlon_to_osrm_coords(lat2, lon2)
    if profile == "car":
        return f"{OSRM_BASE}/pmap_car/car/{c1};{c2}?overview=full&steps=true"
    elif profile == "bike":
        return f"{OSRM_BASE}/pmap_bike/bike/{c1};{c2}?overview=full&steps=true"
    else:
        raise ValueError(f"Unsupported profile: {profile}")

def call_osrm_distance(session: requests.Session, profile: str, lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
    url = build_osrm_url(profile, lat1, lon1, lat2, lon2)
    backoff = 1.0
    for attempt in range(1, RETRIES + 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "Ok":
                raise RuntimeError(f"OSRM {profile} returned code {data.get('code')}")
            routes = data.get("routes")
            if not routes:
                raise RuntimeError(f"No routes in OSRM {profile} response")
            distance_m = routes[0].get("distance")
            if distance_m is None:
                raise RuntimeError(f"No distance field in OSRM {profile} route")
            return float(distance_m) / 1000.0
        except Exception as e:
            if attempt == RETRIES:
                print(f"[WARN] OSRM {profile} request failed for {url}: {e}", file=sys.stderr)
                return None
            else:
                time.sleep(backoff)
                backoff *= RETRY_BACKOFF

def call_osrm_both(session: requests.Session, lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[Optional[float], Optional[float]]:
    driving_km = call_osrm_distance(session, "car", lat1, lon1, lat2, lon2)
    bike_km = call_osrm_distance(session, "bike", lat1, lon1, lat2, lon2)
    return driving_km, bike_km

def detect_coordinate_columns(df: pd.DataFrame):
    cols = [c.lower() for c in df.columns]
    pickup_col = None
    dest_col = None
    for c_orig, c_low in zip(df.columns, cols):
        if ("pickup" in c_low and ("lat" in c_low or "lon" in c_low or "," in c_low)) or \
           (c_low.strip() == "popular pickup lat,lon"):
            pickup_col = c_orig
        if ("destination" in c_low and ("lat" in c_low or "lon" in c_low or "," in c_low)) or \
           (c_low.strip() == "popular destination lat, lon"):
            dest_col = c_orig
    if pickup_col is None or dest_col is None:
        if len(df.columns) >= 4:
            pickup_col = pickup_col or df.columns[1]
            dest_col = dest_col or df.columns[3]
    return pickup_col, dest_col

def safe_extract_latlon(cell):
    if is_empty_coord(cell):
        return None
    parsed = parse_latlon(cell)
    if parsed is None:
        return None
    lat, lon = parsed
    return (lat, lon)

def main():
    parser = argparse.ArgumentParser(description="Process route distances using OSRM")
    
    # Changed the argument to accept "--input-csv --routes-clean.csv" format
    parser.add_argument("--input-csv", required=True, help="Input CSV file containing the route data")
    parser.add_argument("--output-csv", required=True, help="Output CSV file to save the results")
    parser.add_argument("--max-workers", type=int, default=8, help="Number of concurrent workers for OSRM requests")

    args = parser.parse_args()

    # Load routes_clean.csv (auto-detect delimiter)
    df = pd.read_csv(args.input_csv, sep=None, engine='python')
    print(f"[INFO] Loaded {len(df)} rows from {args.input_csv}")
    print(f"[INFO] Columns: {list(df.columns)}")

    pickup_col, dest_col = detect_coordinate_columns(df)
    if pickup_col is None or dest_col is None:
        raise RuntimeError("Could not detect pickup/destination coordinate columns. Check CSV headers.")

    print(f"[INFO] Using pickup column: '{pickup_col}' and destination column: '{dest_col}'")

    # Add columns for distance and diff
    df["OSRM_distance_km_car"] = pd.NA
    df["OSRM_distance_km_bike"] = pd.NA
    df["diff_car"] = pd.NA  # Difference for car
    df["diff_bike"] = pd.NA  # Difference for bike

    to_process = list(df.index)
    print(f"[INFO] {len(to_process)} rows to process (full recompute).")

    session = requests.Session()
    processed_count = 0
    saved_count = 0

    # Use ThreadPoolExecutor to allow concurrent requests (IO-bound)
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {}
        # submit tasks
        for idx in to_process:
            pickup_val = df.at[idx, pickup_col]
            dest_val = df.at[idx, dest_col]
            p = safe_extract_latlon(pickup_val)
            d = safe_extract_latlon(dest_val)
            if p is None or d is None:
                if not (is_empty_coord(pickup_val) and is_empty_coord(dest_val)):
                    print(
                        f"[WARN] Could not parse coordinates at row {idx}. "
                        f"pickup='{pickup_val}' dest='{dest_val}'. Skipping.",
                        file=sys.stderr,
                    )
                df.at[idx, "OSRM_distance_km_car"] = pd.NA
                df.at[idx, "OSRM_distance_km_bike"] = pd.NA
                df.at[idx, "diff_car"] = pd.NA
                df.at[idx, "diff_bike"] = pd.NA
                processed_count += 1
                continue

            lat1, lon1 = p
            lat2, lon2 = d
            futures[executor.submit(call_osrm_both, session, lat1, lon1, lat2, lon2)] = idx

        # gather completed futures and write results as they come
        for fut in tqdm(as_completed(futures), total=len(futures), desc="OSRM requests"):
            idx = futures[fut]
            try:
                driving_km, bike_km = fut.result()
            except Exception as e:
                print(f"[ERROR] worker raised exception for row {idx}: {e}", file=sys.stderr)
                driving_km = None
                bike_km = None

            if driving_km is None:
                df.at[idx, "OSRM_distance_km_car"] = pd.NA
            else:
                df.at[idx, "OSRM_distance_km_car"] = round(driving_km, 2)

            if bike_km is None:
                df.at[idx, "OSRM_distance_km_bike"] = pd.NA
            else:
                df.at[idx, "OSRM_distance_km_bike"] = round(bike_km, 2)

            # Difference columns
            if driving_km is not None and bike_km is not None:
                df.at[idx, "diff_car"] = round(driving_km - bike_km, 2)
                df.at[idx, "diff_bike"] = round(bike_km - driving_km, 2)

            df.at[idx, "diff_car"] = pd.NA
            df.at[idx, "diff_bike"] = pd.NA

            processed_count += 1

            # Save periodically
            if processed_count % SAVE_EVERY == 0:
                df.to_csv(args.output_csv, index=False)
                saved_count += 1
                print(f"[INFO] Saved after {processed_count} processed rows to {args.output_csv}")

        # final save
        df.to_csv(args.output_csv, index=False)
        print(f"[INFO] Final save to {args.output_csv}. Total processed: {processed_count}. Saves performed: {saved_count + 1}")

if __name__ == "__main__":
    main()
