import requests
import os
import datetime
from telebot import TeleBot, types
import redis
import logging
from geopy.distance import geodesic
import mysql.connector
import re
from googletrans import Translator
from math import radians, sin, cos, sqrt, atan2
import time
import json
import tempfile

logging.basicConfig(filename="logs.txt", 
                    filemode="a", 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)

redis_client = redis.Redis()

translator = Translator()

db_connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password=os.environ.get("MYSQL_PASSWORD"),
    database="PlacesExploraion"
)

def generate_map_link(place_id):
    logger.debug(f"Generating map link for place ID: {place_id}")  
    map_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
    logger.debug(f"Generated map link: {map_url}") 
    return map_url

def haversine(lat1, lon1, lat2, lon2):
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = 6371 * c * 1000
    return distance

def is_in_range(user_lat, user_lon, place_lat, place_lon, range_meters):
    distance = haversine(user_lat, user_lon, place_lat, place_lon)
    return distance <= range_meters

def compute_distance(lat1, lon1, lat2, lon2):
    point1 = (lat1, lon1)
    
    point2 = (lat2, lon2)
    
    distance = geodesic(point1, point2).meters
    return distance

def get_places_in_bounding_box(user_lat, user_lon, range_meters):
    lat_delta = range_meters / 111111 
    lon_delta = range_meters / (111111 * cos(radians(user_lat))) 
    min_lat = user_lat - lat_delta
    max_lat = user_lat + lat_delta
    min_lon = user_lon - lon_delta
    max_lon = user_lon + lon_delta

    cursor = db_connection.cursor()

    query = """
    SELECT place_id, latitude, longitude
    FROM Places
    WHERE latitude BETWEEN %s AND %s
    AND longitude BETWEEN %s AND %s
    """
    cursor.execute(query, (min_lat, max_lat, min_lon, max_lon))
    places_in_bounding_box = cursor.fetchall()

    return places_in_bounding_box

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

def is_open_now(data):
    now = datetime.datetime.now()
    current_day = now.weekday()  
    current_time = now.strftime("%H%M")

    for period in data["periods"]:
        if period["open"]["day"] <= current_day:  
            if "close" in period and period["close"]["day"] >= current_day: 
                if period["open"]["day"] > period["close"]["day"]:
                    if current_time >= period["open"]["time"] or current_time < period["close"]["time"]:
                        return True                
                else:
                    if current_time >= period["open"]["time"]:
                        return True
            else:
                return True

    return False

def get_places(latitude, longitude, search_radius, keywords, type):
    logger.info(f"Get places triggered {latitude}, {longitude}, {search_radius}, {keywords}, {type}")
    places_in_bounding_box = get_places_in_bounding_box(latitude, longitude, search_radius)
    places = []
    for place_id, place_lat, place_lon in places_in_bounding_box:
        if is_in_range(latitude, longitude, place_lat, place_lon, search_radius):
                query = f"SELECT place_id, latitude, longitude, name, formatted_address, weekday_text, rating, price_level, url, website, serves_beer, serves_breakfast, serves_brunch, serves_dinner, serves_lunch, serves_vegetarian_food, serves_wine, opening_hours, photos, types FROM Places WHERE place_id = '{place_id}'"
                cursor = db_connection.cursor()
                cursor.execute(query)
                place = cursor.fetchall()[0]
                open_now = None
                if place[17] is not None:
                    opening_hours = json.loads(place[17])
                    if opening_hours is not None:
                        if is_open_now(opening_hours):
                            open_now = True
                        else:
                            open_now = False
                place_data = {
                                "name": place[3],
                                "address": place[4],
                                "weekday_text": place[5],
                                "distance": compute_distance(latitude, longitude, place[1], place[2]),
                                "rating": place[6],
                                "price_level": place[7],
                                "place_id" : place_id,
                                "url": place[8],
                                "website": place[9],
                                "serves_beer": place[10],
                                "serves_breakfast": place[11],
                                "serves_brunch": place[12],
                                "serves_dinner": place[13],
                                "serves_lunch": place[14],
                                "serves_vegetarian_food": place[15],
                                "serves_wine": place[16],
                                "open_now": open_now,
                                "photos": json.loads(place[18])
                            }
                if type in place[19]:
                    places.append(place_data)
    return places
            
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TeleBot(BOT_TOKEN)
logger.info("Bot is started")

start_keyboard_list = ["Пошук закладів", "Налаштування"]
start_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in start_keyboard_list:
    start_keyboard.add(types.KeyboardButton(text=button))

location_keyboard_button_list = ["Змінити радіус пошуку"]
settings_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in location_keyboard_button_list:
    settings_keyboard.add(types.KeyboardButton(text=button))
    
filters_keyboard_button_list = ['Подають пиво', 'Подають вино', 'Подають сніданок', 'Подають бранч', 'Подають обід', 'Подають вечерю', 'Подають вегетаріанську їжу']
filters_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in filters_keyboard_button_list:
    filters_keyboard.add(types.KeyboardButton(text=button))

location_keyboard_buttons_list = ["Пошук закладів", "Налаштування"]
location_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in location_keyboard_buttons_list:
    location_keyboard.add(types.KeyboardButton(text=button))

ranges_list = ["250", "500", "750", "1000", "1500", "2000", "2500", "3000", "3500", "4500", "5000"]
set_range_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
ranges_chunks = [ranges_list[i:i+2] for i in range(0, len(ranges_list), 2)]
for chunk in ranges_chunks[:-1]:
    set_range_keyboard.add(types.KeyboardButton(text=chunk[0]), types.KeyboardButton(text=chunk[1]))
if len(ranges_list) % 2 != 0:
    last_chunk = ranges_chunks[-1]
    set_range_keyboard.add(types.KeyboardButton(text=last_chunk[0]))

search_option_keyboard_buttons_list = ["Кафе", "Ресторан", "Бар"]
search_option_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in search_option_keyboard_buttons_list:
    search_option_keyboard.add(types.KeyboardButton(text=button))


@bot.message_handler(commands=['start'])
def start(message):
    redis_client.set(str(message.chat.id) + "_range", 300)
    bot.send_message(message.chat.id, 
                     """Вітаю! Цей бот допоможе вам знайти кафе та ресторани поблизу. \n
                     Оберіть дію: """,
                     reply_markup=start_keyboard)

@bot.message_handler(content_types=['location'])
def save_location(message):
    location_string = f"{message.location.latitude},{message.location.longitude}"
    redis_client.set(message.chat.id, location_string)
    bot.send_message(message.chat.id, "Запам'ятав", reply_markup=location_keyboard)
    
@bot.message_handler(content_types=['text']) 
def handle_settings(message):
    if message.text == "Налаштування":
        bot.send_message(message.chat.id, "Оберіть налаштування:", reply_markup=settings_keyboard)
    elif message.text == "Пошук закладів":
        bot.send_message(message.chat.id, "Оберіть тип закладу для пошуку:", reply_markup=search_option_keyboard)
        bot.register_next_step_handler(message, handle_keywords_for_search)
    elif message.text == "Змінити радіус пошуку":
        bot.send_message(message.chat.id, "Оберіть бажаний радіус пошуку", reply_markup=set_range_keyboard)
    elif message.text in ranges_list:
        bot.send_message(message.chat.id, "Обрано", reply_markup=start_keyboard)
        try:
            redis_client.set(str(message.chat.id) + "_range", int(message.text))
        except ValueError:
            bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз", reply_markup=start_keyboard)
    
    else:
        bot.send_message(message.chat.id, "Такої команди не існує, почніть заново", reply_markup=start_keyboard)
        
def handle_keywords_for_search(message):
    if message.text in search_option_keyboard_buttons_list:
        if message.text == "Кафе":
            search(message, type="cafe")
        elif message.text == "Ресторан":
            search(message, type="restaurant")
        elif message.text == "Бар":
            search(message, type="bar")

def search(message, keywords=None, type=None):
    logger.info(f"Search triggered, keywords:{keywords}, type:{type}")
    if message.location:
        location_string = f"{message.location.latitude},{message.location.longitude}"
        redis_client.set(message.chat.id, location_string)
        
    location_string = redis_client.get(message.chat.id)
    if location_string:
        bot.send_message(message.chat.id, "Зачекайте трошки, збираю інформацію", reply_markup=types.ReplyKeyboardRemove())
        try:
            if not type:
                logger.error("No type specified")
                type="cafe"
            
            logger.info(f"Search keywords: {keywords}")
            
            latitude, longitude = location_string.decode().split(',') 
            search_radius = int(redis_client.get(str(message.chat.id) + "_range"))

            logger.info(f"Search location: ({latitude}, {longitude}). Radius: {search_radius}")
            places = get_places(float(latitude), float(longitude), search_radius, keywords, type=type)

            if not places:
                bot.send_message(message.chat.id, "За вашим запитом нічого не знайдено.", reply_markup=start_keyboard)
                logger.debug("No places found for the search query.")
                return
            try:
                places = sorted(places, key=lambda x: x["distance"])
            except:
                pass
            for place in places:
                address = str(place['address'])
                translated_address = translator.translate(address, src='en', dest='uk').text
                response = (f"Назва: {place['name']}\nАдреса: {translated_address}\n"
                            f"Статус роботи: {'Відкрито' if place['open_now'] else 'Закрито'}\n"
                            f"Відстань: {int(place['distance'])} метрів\n"
                            f"Рейтинг: {place['rating'] if place['rating'] is not None else 'Невідомо'}"
                            + (f"\nРівень Ціни: {place['price_level']}" if place['price_level'] is not None else '') + 
                            f"{'Подають пиво' if place.get('serves_beer', False) else ''}"
                            f"{'Подають вино' if place.get('serves_wine', False) else ''}"
                            f"{'Подають сніданок' if place.get('serves_breakfast', False) else ''}"
                            f"{'Подають бранч' if place.get('serves_brunch', False) else ''}"
                            f"{'Подають обід' if place.get('serves_lunch', False) else ''}"
                            f"{'Подають вечерю' if place.get('serves_dinner', False) else ''}"
                            f"{'Подають вегетаріанську їжу' if place.get('serves_vegetarian_food', False) else ''}"
                            )
                if place['weekday_text']:
                    response += "\n\nГрафік роботи:"
                    response += place['weekday_text']
                else:
                    response += "\nГрафік роботи невідомий :("
                response = replace_weekdays(response).replace("Closed", "Зачинено")
                map_link = generate_map_link(place["place_id"])
                inline_keyboard = types.InlineKeyboardMarkup()
                inline_keyboard.add(types.InlineKeyboardButton(text="Відобразити на мапі", url=map_link))
                if "website" in place:
                    if place["website"] is not None:
                        inline_keyboard.add(types.InlineKeyboardButton(text="Веб-сайт", url=place["website"]))
                place_id = place["place_id"]
                if place["photos"] is not None:
                    query = f"SELECT photo_data FROM PlacePhotos WHERE place_id = '{place_id}'"
                    cursor = db_connection.cursor()
                    cursor.execute(query)
                    blob_data_list = cursor.fetchall()
                    media_group = []
                    for blob_data in blob_data_list:
                        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                            temp_file.write(blob_data[0])
                            media_group.append(types.InputMediaPhoto(open(temp_file.name, 'rb')))
                    logger.debug(f"Sending details for place: {place['name']}")
                    if len(media_group) > 0:
                        bot.send_media_group(message.chat.id, media_group)
                logger.debug(f"Sending details for place: {place['name']}")
                bot.send_message(message.chat.id, response, reply_markup=inline_keyboard)
            bot.send_message(message.chat.id, "Оберіть дію:", reply_markup=start_keyboard)
            redis_client.delete(message.chat.id)
        except Exception as e:
            bot.send_message(message.chat.id, "Виникла помилка, почніть заново", reply_markup=start_keyboard)
            logger.error(f"Error : {e}")
    else:
        logger.warning(f"Location not found for chat ID: {message.chat.id}")
        bot.send_message(message.chat.id, "Будь ласка, поділіться вашим місцезнаходженням для здійснення пошуку", 
        reply_markup=types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True, selective=True).add(types.KeyboardButton(text="Надіслати розташування", request_location=True)))
        bot.register_next_step_handler(message, search, keywords, type)
        
if __name__ == '__main__':
    while True:
        try:
            bot.polling()
        except Exception as e: 
            logger.critical(f"Bot crashed: {e}")
            time.sleep(2) 