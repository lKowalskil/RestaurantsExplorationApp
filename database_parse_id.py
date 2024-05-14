import requests
import os
import math
import folium
import mysql.connector

API_KEY = os.environ.get("GOOGLE_API_KEY")

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password=os.environ.get("MySQL_PASSWORD"),
    database="PlacesExploration"
)
if conn.is_connected():
    print("Connected to the MySQL database")

def km_to_degrees(latitude, km):
    earth_radius_km = 6371.0
    lat_rad = math.radians(latitude)
    circumference = 2 * math.pi * earth_radius_km * math.cos(lat_rad)
    conversion_factor = 360 / circumference
    degrees = km * conversion_factor
    return degrees

def generate_circle_coordinates(min_lon, max_lon, min_lat, max_lat, radius_km, offset_meters=250):
    radius_degrees = km_to_degrees((min_lat + max_lat) / 2, radius_km)
    lon_step = km_to_degrees((min_lat + max_lat) / 2, offset_meters / 1000)
    lat_step = km_to_degrees((min_lat + max_lat) / 2, offset_meters / 1000)

    circles = []
    lon = min_lon
    while lon <= max_lon:
        lat = min_lat
        while lat <= max_lat:
            circles.append({'latitude': lat, 'longitude': lon})
            lat += lat_step
        lon += lon_step

    return circles

min_longitude = 30.28375
max_longitude = 30.71647
min_latitude = 50.32881
max_latitude = 50.58280
circle_radius_km = 0.25

circle_coordinates = generate_circle_coordinates(min_longitude, max_longitude, min_latitude, max_latitude, circle_radius_km)
#print(circle_coordinates)

center_lat = (min_latitude + max_latitude) / 2
center_lon = (min_longitude + max_longitude) / 2

my_map = folium.Map(location=[center_lat, center_lon], zoom_start=12)

for circle in circle_coordinates:
    folium.Circle(
        location=[circle['latitude'], circle['longitude']],
        radius=circle_radius_km*1000,
        color='blue',
        fill=True,
        fill_color='blue',
        fill_opacity=0.3
    ).add_to(my_map)

# Save the map as an HTML file
my_map.save("circle_map.html")

base_nearby_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
place_types = ["restaurant", "cafe", "bar"]
for circle in circle_coordinates:
    for place_type in place_types:
        latitude = circle["latitude"]
        longitude = circle["longitude"]
        nearby_params = {
            "location": f"{latitude},{longitude}",
            "radius": circle_radius_km*1000,
            "type": place_type,
            "key": API_KEY,
        }
        nearby_response = requests.get(base_nearby_url, params=nearby_params)
        if nearby_response.status_code != 200:
            print(f"ERROR Response code: {nearby_response.status_code}")
        else:
            nearby_data = nearby_response.json()

            if nearby_data['status'] == 'OK':
                for place in nearby_data['results']:
                    place_id = place['place_id']
                    #print(place_id)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM Places WHERE place_id = %s", (place_id,))
                    exists = cursor.fetchone()[0]
                    if not exists:
                        cursor.execute("INSERT INTO Places (place_id) VALUES (%s)", (place_id,))
                        conn.commit()
                        print(f"Added {place_id} to the Places table")
                    else:
                        print(f"{place_id} already exists in the Places table")
