import requests
import os
import mysql.connector
from mysql.connector import pooling
import logging
import json
import datetime
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from googletrans import Translator

logging.basicConfig(filename="logs.txt",
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

dbconfig = {
    "host": "localhost",
    "user": "RestApp",
    "password": os.environ.get("MYSQL_PASSWORD"),
    "database": "PlacesExploration"
}
threads = 10
connection_pool = pooling.MySQLConnectionPool(pool_name="mypool",
                                              pool_size=threads,
                                              **dbconfig)

translator = Translator()

"""for json_file in os.listdir("./details_jsons"):
    place_id = json_file.replace("details_data_", "").replace(".json", "")
    print(place_id)
    insert_query = "INSERT INTO Places (place_id) VALUES (%s)"
    cursor.execute(insert_query, (place_id,))
    conn.commit()"""

def fetch_place_ids():
    try:
        conn = connection_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT place_id FROM Places")
        place_ids = cursor.fetchall()
        return [row[0] for row in place_ids]
    except mysql.connector.Error as error:
        logger.error("Error retrieving data from MySQL:", error)
        return []
    finally:
        cursor.close()
        conn.close()

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
def process_place(place_id):
    conn = connection_pool.get_connection()
    cursor = conn.cursor()
    
    try:
        filepath = f"./details_jsons/details_data_{place_id}.json"
        with open(filepath, "r", encoding="utf-8") as json_file:
            details_data = json.load(json_file)

        if details_data['status'] == 'OK':
            logger.info(f"Place details fetched successfully for {place_id}.")
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
            formatted_address = result.get("formatted_address")
            #formatted_address = translator.translate(formatted_address, dest="uk", src="en").text
            formatted_phone_number = result.get("formatted_phone_number")
            international_phone_number = result.get("international_phone_number")
            latitude = result.get("geometry", {}).get("location", {}).get("lat")
            longitude = result.get("geometry", {}).get("location", {}).get("lng")
            northeast_lat = result.get("geometry", {}).get("viewport", {}).get("northeast", {}).get("lat")
            northeast_lng = result.get("geometry", {}).get("viewport", {}).get("northeast", {}).get("lng")
            southwest_lat = result.get("geometry", {}).get("viewport", {}).get("southwest", {}).get("lat")
            southwest_lng = result.get("geometry", {}).get("viewport", {}).get("southwest", {}).get("lng")
            icon_url = result.get("icon")
            name = result.get("name")
            price_level = result.get("price_level")
            rating = result.get("rating")
            reservable = result.get("reservable")
            serves_beer = result.get("serves_beer")
            serves_wine = result.get("serves_wine")
            serves_dinner = result.get("serves_dinner")
            serves_lunch = result.get("serves_lunch")
            serves_breakfast = result.get("serves_breakfast")
            serves_brunch = result.get("serves_brunch")
            serves_vegetarian_food = result.get("serves_vegetarian_food")
            takeout = result.get("takeout")
            dine_in = result.get("dine_in")
            delivery = result.get("delivery")
            url = result.get("url")
            business_status = result.get("business_status")
            curbside_pickup = result.get("curbside_pickup")
            opening_hours = result.get("opening_hours")
            reviews = result.get("reviews")
            #if reviews is not None:
                #for review in reviews:
                    #review["text"] = translator.translate(review["text"], dest="uk").text
            website = result.get("website")
            photos = result.get("photos")
            types = ''.join(result.get("types", []))
            weekday_text = None
            response_weekday_text = ''
            if opening_hours and "weekday_text" in opening_hours:
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
                        time1_str = parts[0].strip().split(":")
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
            wheelchair_accessible_entrance = result.get("wheelchair_accessible_entrance")
            
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
                logger.info(f"Update successful for {place_id}.")
            else:
                logger.info(f"Update failed for {place_id}.")
        else:
            logger.error(f"details_data['status'] is not OK for {place_id}")
    except Exception as e:
        logger.error(f"Error processing place {place_id}: {e}")
    finally:
        cursor.close()
        conn.close()

place_ids = fetch_place_ids()

with ThreadPoolExecutor(max_workers=threads) as executor:
    with tqdm(total=len(place_ids)) as progress:
        futures = [executor.submit(process_place, place_id) for place_id in place_ids]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                logger.error(f"Generated an exception: {exc}")
            finally:
                progress.update(1)

