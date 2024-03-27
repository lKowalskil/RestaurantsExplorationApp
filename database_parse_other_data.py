import requests
import os
import math
import folium
import mysql.connector
import time
import logging
from bs4 import BeautifulSoup
import json
import mimetypes

logging.basicConfig(#filename="logs.txt", 
                    filemode="a", 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
                    level=logging.INFO)
logger = logging.getLogger(__name__)

def download_photo(url, file_path):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            with open(file_path, "wb") as photo_file:
                photo_file.write(response.content)
            print(f"Photo downloaded successfully and saved as {file_path}")
        else:
            print(f"Error: Unable to download photo from {url}")
    except Exception as e:
        print(f"Error: {e}")

#API_KEY = os.environ.get("GOOGLE_API_KEY")

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password=os.environ.get("MySQL_PASSWORD"),
    database="PlacesExploraion"
)

if conn.is_connected():
    print("Connected to the MySQL database")

cursor = conn.cursor()
try:
    cursor.execute("SELECT place_id FROM Places")
    place_ids = cursor.fetchall()
    place_ids = [row[0] for row in place_ids]
    print("All place_id values:")
    for place_id in place_ids:
        print(place_id)
except mysql.connector.Error as error:
    print("Error retrieving data from MySQL:", error)

for place_id in place_ids:
    """details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=address_components,adr_address,business_status,formatted_address,geometry,icon,icon_mask_base_uri,icon_background_color,name,photo,place_id,plus_code,type,url,utc_offset,vicinity,wheelchair_accessible_entrance,current_opening_hours,formatted_phone_number,international_phone_number,opening_hours,secondary_opening_hours,website,curbside_pickup,delivery,dine_in,editorial_summary,price_level,rating,reservable,reviews,serves_beer,serves_breakfast,serves_brunch,serves_dinner,serves_lunch,serves_vegetarian_food,serves_wine,takeout,user_ratings_total&key={API_KEY}"
    details_response = requests.get(details_url)

    if details_response.status_code == 200:
        details_data = details_response.json()

        file_path = f"./details_jsons/details_data_{place_id}.json"

        with open(file_path, "w", encoding="utf-8") as json_file:
            json.dump(details_data, json_file, ensure_ascii=False)

        logger.info(f"Details data saved to {file_path}")
    else:
        logger.info("Error: Unable to fetch details data")"""
        
    filepath = f"./details_jsons/details_data_{place_id}.json"
    with open(filepath, "r") as json_file:
        details_data = json.load(json_file)
        
    if details_data['status'] == 'OK':
        logger.info("Place details fetched successfully.")
        result = details_data['result']
        """if "photos" in result:
            for i in range(len(result["photos"])):
                photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={result['photos'][0]['width']+ 1}&photo_reference={result['photos'][i]['photo_reference']}&key={API_KEY}"
                os.makedirs(f"./photos/{place_id}_photos", exist_ok=True)
                photo_path = f"./photos/{place_id}_photos/{i}_{place_id}.jpg"
                if os.path.exists(photo_path):
                    continue
                download_photo(photo_url, photo_path)"""
                
        formatted_address = result["formatted_address"] if "formatted_address" in result else None
        formatted_phone_number = result["formatted_phone_number"] if "formatted_phone_number" in result else None
        international_phone_number = result["international_phone_number"] if "international_phone_number" in result else None
        latitude = result["geometry"]["location"]["lat"] if "geometry" in result else None
        longitude = result["geometry"]["location"]["lng"] if "geometry" in result else None
        northeast_lat = result["geometry"]["viewport"]["northeast"]["lat"] if "geometry" in result else None
        northeast_lng = result["geometry"]["viewport"]["northeast"]["lng"] if "geometry" in result else None
        southwest_lat = result["geometry"]["viewport"]["southwest"]["lat"] if "geometry" in result else None
        southwest_lng = result["geometry"]["viewport"]["southwest"]["lng"] if "geometry" in result else None
        icon_url = result["icon"] if "icon" in result else None
        name = result["name"] if "name" in result else None
        price_level = result["price_level"] if "price_level" in result else None
        rating = result["rating"] if "rating" in result else None
        reservable = result["reservable"] if "reservable" in result else None
        serves_beer = result["serves_beer"] if "serves_beer" in result else None
        serves_wine = result["serves_wine"] if "serves_wine" in result else None
        takeout = result["takeout"] if "takeout" in result else None
        url = result["url"] if "url" in result else None
        wheelchair_accessible_entrance = result["wheelchair_accessible_entrance"] if "wheelchair_accessible_entrance" in result else None
        sql = """UPDATE Places SET
                formatted_address=%s, formatted_phone_number=%s, international_phone_number=%s,
                latitude=%s, longitude=%s, northeast_lat=%s, northeast_lng=%s, southwest_lat=%s, southwest_lng=%s,
                icon_url=%s, name=%s, price_level=%s, rating=%s, reservable=%s, serves_beer=%s, serves_wine=%s,
                takeout=%s, url=%s, wheelchair_accessible_entrance=%s
                WHERE place_id=%s"""
        values = (
            formatted_address, formatted_phone_number, international_phone_number,
            latitude, longitude, northeast_lat, northeast_lng, southwest_lat, southwest_lng,
            icon_url, name, price_level, rating, reservable, serves_beer, serves_wine,
            takeout, url, wheelchair_accessible_entrance,
            place_id
        )
        cursor.execute(sql, values)
        conn.commit()
        if cursor.rowcount > 0:
            logger.info("Update successful.")
        else:
            logger.info("Update failed.")
    else:
        logger.error(f"details_data['status'] is not OK")
        