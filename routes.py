import csv

# ---- CONFIG ----
INPUT_FILE = "in.csv"   # your original 2-column file
OUTPUT_FILE = "routes_clean.csv"      # new clean routes file
# ----------------


def get_main_location(name: str) -> str:
    """
    'Main' location = first word of the pickup area.
    Example: 'Aftabnagar Block A' -> 'Aftabnagar'
    """
    if not name:
        return ""
    return name.strip().split()[0]


def read_locations(input_path: str):
    """
    Read the original pickup locations file and return a list of dicts:
    [
      {"Pickup Area": "...", "Popular Pickup Lat,Lon": "..."},
      ...
    ]
    """
    # --- Detect delimiter ---
    with open(input_path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ","  # fallback
        print(f"[INFO] Detected input delimiter: {repr(delimiter)}")

        reader = csv.DictReader(f, delimiter=delimiter)
        locations = []

        for raw_row in reader:
            # Strip whitespace from keys and values
            row = {
                (k.strip() if k else ""): (v.strip() if v else "")
                for k, v in raw_row.items()
            }

            # Expect these columns in some form
            pickup_area = row.get("Pickup Area", "")
            pickup_latlon = row.get("Popular Pickup Lat,Lon", "")

            # Skip rows without a pickup area or lat/lon
            if not pickup_area or not pickup_latlon:
                continue

            locations.append({
                "Pickup Area": pickup_area,
                "Popular Pickup Lat,Lon": pickup_latlon,
            })

    print(f"[INFO] Loaded {len(locations)} pickup locations")
    return locations


def generate_route_rows(locations):
    """
    From a list of locations, generate all unique pairs (i < j),
    skipping pairs where the main location (first word) is the same.
    """
    routes = []
    n = len(locations)
    for i in range(n):
        for j in range(i + 1, n):
            loc_i = locations[i]
            loc_j = locations[j]

            main_i = get_main_location(loc_i["Pickup Area"])
            main_j = get_main_location(loc_j["Pickup Area"])

            # Skip routes inside the same main location
            if main_i == main_j:
                continue

            routes.append({
                "Pickup Area": loc_i["Pickup Area"],
                "Popular Pickup Lat,Lon": loc_i["Popular Pickup Lat,Lon"],
                "Destination": loc_j["Pickup Area"],
                "Popular Destination Lat, Lon": loc_j["Popular Pickup Lat,Lon"],
            })

    print(f"[INFO] Generated {len(routes)} routes")
    return routes


def write_routes(output_path: str, routes):
    """
    Write all routes to a clean CSV with exactly 4 columns,
    comma-separated (Excel-friendly).
    """
    fieldnames = [
        "Pickup Area",
        "Popular Pickup Lat,Lon",
        "Destination",
        "Popular Destination Lat, Lon",
    ]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=",")
        writer.writeheader()
        for r in routes:
            writer.writerow(r)

    print(f"[INFO] Saved routes to {output_path}")


def main():
    locations = read_locations(INPUT_FILE)
    routes = generate_route_rows(locations)
    write_routes(OUTPUT_FILE, routes)


if __name__ == "__main__":
    main()
