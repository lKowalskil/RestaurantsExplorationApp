import requests
import os
import mysql.connector
import logging
import json
import datetime
import re
from googletrans import Translator

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

API_KEY = os.environ.get("GOOGLE_API_KEY")

conn = mysql.connector.connect(
    host="localhost",
    user="phpmyadmin",
    password=os.environ.get("MYSQL_PASSWORD"),
    database="PlacesExploration"
)

if conn.is_connected():
    print("Connected to the MySQL database")

cursor = conn.cursor()

translator = Translator()

"""for json_file in os.listdir("/home/koval/RestaurantsExplorationApp/details_jsons"):
    place_id = json_file.replace("details_data_", "").replace(".json", "")
    print(place_id)
    insert_query = "INSERT INTO Places (place_id) VALUES (%s)"
    cursor.execute(insert_query, (place_id,))
    conn.commit()
"""
try:
    cursor.execute("SELECT place_id FROM Places")
    place_ids = cursor.fetchall()
    place_ids = [row[0] for row in place_ids]
    print("All place_id values:")
    for place_id in place_ids:
        print(place_id)
except mysql.connector.Error as error:
    print("Error retrieving data from MySQL:", error)

def replace_weekdays(text):
    logger.debug(f"Replacing weekdays in text: {text}")
    weekdays = {
        "Monday": "Понеділок",
        "Tuesday": "Вівторок",
        "Wednesday": "Середа",
        "Thursday": "Четвер",
        "Friday": "П'ятниця",
        "Saturday": "Субота",
        "Sunday": "Неділя",
    }

    for weekday, ukrainian_weekday in weekdays.items():
        pattern = rf"\b{weekday}\b"
        logger.debug(f"Replacing '{weekday}' with '{ukrainian_weekday}'")
        text = re.sub(pattern, ukrainian_weekday, text, flags=re.IGNORECASE)

    logger.debug(f"Weekday replacement completed. Text after replacement: {text}")
    return text
i = 0
num_photos = 0
for place_id in place_ids:
    i += 1
    print(i)
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
                if i > 0:
                    continue
                photo_reference = result["photos"][i]["photo_reference"]
                width = result['photos'][0]['width'] + 1
                os.makedirs(f"./photos/{place_id}_photos", exist_ok=True)
                photo_path = f"./photos/{place_id}_photos/{photo_reference}.jpg"
                if os.path.exists(photo_path):
                    #print("Exists")
                    continue
                else:
                    #photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={width}&photo_reference={photo_reference}&key={API_KEY}"
                    #download_photo(photo_url, photo_path)
                    #time.sleep(0.09)
                    #num_photos += 1"""
                
        formatted_address = result["formatted_address"] if "formatted_address" in result else None
        formatted_address = translator.translate(formatted_address, dest="uk", src="en").text
        print(formatted_address)
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
        serves_dinner = result["serves_dinner"] if "serves_dinner" in result else None
        serves_lunch = result["serves_lunch"] if "serves_lunch" in result else None
        serves_breakfast = result["serves_breakfast"] if "serves_breakfast" in result else None
        serves_brunch = result["serves_brunch"] if "serves_brunch" in result else None
        serves_vegetarian_food = result["serves_vegetarian_food"] if "serves_vegetarian_food" in result else None
        takeout = result["takeout"] if "takeout" in result else None
        dine_in = result["dine_in"] if "dine_in" in result else None
        delivery = result["delivery"] if "delivery" in result else None
        url = result["url"] if "url" in result else None
        business_status = result["business_status"] if "business_status" in result else None
        curbside_pickup = result["curbside_pickup"] if "curbside_pickup" in result else None
        opening_hours = result["opening_hours"] if "opening_hours" in result else None
        reviews = result["reviews"] if "reviews" in result else None
        if reviews is not None:
            for review in reviews:
                review["text"] = translator.translate(review["text"], dest="uk").text
        website = result["website"] if "website" in result else None
        photos = result["photos"] if "photos" in result else None
        types = ''.join(result["types"]) if "types" in result else None
        weekday_text = None
        response_weekday_text = ''
        if opening_hours is not None and "weekday_text" in opening_hours:
            weekday_text = opening_hours["weekday_text"]
            for day_text in weekday_text:
                if "Closed" in day_text:
                    response_weekday_text += f"\n- {day_text}"
                elif "Open 24 hours" in day_text:
                    response_weekday_text += f"\n- {day_text.replace('Open 24 hours', 'Відчинено 24 години')}" 
                else:
                    day_text = day_text.replace("\u202f", " ")
                    day_text = day_text.replace("\u2009", " ")
                    parts = day_text.split('–')
                    time1_str = parts[0].strip()
                    time1_str = time1_str.split(":")
                    time1_str = time1_str[1].replace(" ", "") + ":" + time1_str[2]
                    time2_str = parts[1].strip()
                    try:
                        time1_obj = datetime.datetime.strptime(time1_str, '%I:%M %p')
                        time1_24hour = time1_obj.strftime('%H:%M')
                    except ValueError:
                        time1_24hour = time1_str
                    try:
                        time2_obj = datetime.datetime.strptime(time2_str, '%I:%M %p')
                        time2_24hour = time2_obj.strftime('%H:%M')
                    except ValueError:
                        time2_24hour = time2_str
                    response_weekday_text += f"\n- " + f"{day_text.split(':')[0]}: {time1_24hour} - {time2_24hour}"
        else:
            response_weekday_text += "Графік роботи невідомий :("
        response_weekday_text = replace_weekdays(response_weekday_text).replace("Closed", "Зачинено")
        wheelchair_accessible_entrance = result["wheelchair_accessible_entrance"] if "wheelchair_accessible_entrance" in result else None
        sql = """UPDATE Places SET
                    formatted_address=%s, formatted_phone_number=%s, international_phone_number=%s,
                    latitude=%s, longitude=%s, northeast_lat=%s, northeast_lng=%s, southwest_lat=%s, southwest_lng=%s,
                    icon_url=%s, name=%s, price_level=%s, rating=%s, reservable=%s, serves_beer=%s, serves_wine=%s,
                    takeout=%s, url=%s, wheelchair_accessible_entrance=%s, opening_hours=%s, weekday_text=%s,
                    dine_in=%s, delivery=%s, business_status=%s, curbside_pickup=%s, reviews=%s, website=%s, types=%s, photos=%s,
                    serves_breakfast=%s, serves_brunch=%s, serves_dinner=%s, serves_lunch=%s, serves_vegetarian_food=%s
                    WHERE place_id=%s"""
        values = (
            formatted_address, formatted_phone_number, international_phone_number,
            latitude, longitude, northeast_lat, northeast_lng, southwest_lat, southwest_lng,
            icon_url, name, price_level, rating, reservable, serves_beer, serves_wine,
            takeout, url, wheelchair_accessible_entrance, json.dumps(opening_hours), response_weekday_text,
            dine_in, delivery, business_status, curbside_pickup, json.dumps(reviews), website, types, json.dumps(photos),
            serves_breakfast, serves_brunch, serves_dinner, serves_lunch, serves_vegetarian_food,
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
        
print(num_photos)