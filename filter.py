import h3
import pandas as pd  
import itertools  

def get_hex_for_locations(bq_route_data, resolution=9):
    """
    Find which H3 hexagons the pickup and dropoff locations belong to.
    
    Args:
        bq_route_data: DataFrame with columns like 'pickup_lat', 'pickup_lon', 
                      'destination_lat', 'destination_lon'
        resolution: H3 resolution level (0-15, higher = smaller hexagons)
    
    Returns:
        DataFrame with added columns 'pickup_hex' and 'dropoff_hex'
    """
    bq_route_data['pickup_hex'] = bq_route_data.apply(
        lambda row: h3.latlng_to_cell(row['estimated_pickup_latitude'], row['estimated_pickup_longitude'], resolution),
        axis=1
    )
    
    bq_route_data['dropoff_hex'] = bq_route_data.apply(
        lambda row: h3.latlng_to_cell(row['estimated_dropoff_latitude'], row['estimated_dropoff_longitude'], resolution),
        axis=1
    )
    
    return bq_route_data

def filter_same_hex(bq_route_data):
    """
    Filter routes where pickup and dropoff are in the same H3 hexagon.
    
    Args:
        bq_route_data: DataFrame with 'pickup_hex' and 'dropoff_hex' columns
    
    Returns:
        DataFrame containing only routes with the same pickup and dropoff hexagons
    """
    return bq_route_data[bq_route_data['pickup_hex'] == bq_route_data['dropoff_hex']]

def save_hex_locations_to_csv(bq_route_data, output_path='hex_locations.csv'):
    """
    Save location and hex mapping to a CSV file.
    
    Args:
        bq_route_data: DataFrame with hex and location columns
        output_path: Path where the CSV file will be saved
    """
    hex_data = bq_route_data[[
        'estimated_pickup_latitude', 
        'estimated_pickup_longitude', 
        'pickup_hex',
        'estimated_dropoff_latitude',
        'estimated_dropoff_longitude',
        'dropoff_hex'
    ]].copy()
    
    hex_data.to_csv(output_path, index=False)
    print(f"Saved hex locations to {output_path}")

# Example usage - uncomment and modify as needed
# Load the CSV data
bq_route_data = pd.read_csv('bq_route_data.csv')

# Get hexagons for locations
bq_route_data = get_hex_for_locations(bq_route_data, resolution=9)

# Group pickup and destination areas by hex, calculate total count of rides from one hex to another
hex_map = bq_route_data.groupby(['pickup_hex', 'dropoff_hex']).size().reset_index(name='ride_count')

# Save the hex map to a new CSV
hex_map.to_csv('hex map.csv', index=False)
print("Saved hex map to hex map.csv")

# Filter routes where pickup and dropoff are in the same hexagon
filtered_data = filter_same_hex(bq_route_data)

# Save the filtered hex locations to a new CSV
save_hex_locations_to_csv(filtered_data, output_path='filtered_hex_locations.csv')