import h3

# Example: Get H3 cell for a latitude and longitude at resolution 9
lat, lng = 23.797568, 90.413972
cell = h3.latlng_to_cell(lat, lng, 9)
print(f"H3 cell at resolution 9: {cell}")

# Check if two points are in the same cell
lat2, lng2 = 23.773770, 90.416780
cell2 = h3.latlng_to_cell(lat2, lng2, 9)
print(f"Same cell: {cell == cell2}")