import os
import datetime
from telebot import TeleBot, types
import redis
import logging
from geopy.distance import geodesic
import mysql.connector
from mysql.connector import pooling
import re
from math import radians, sin, cos, sqrt, atan2
import time
import json
import base64

logging.basicConfig(filename="logs.txt",
                    filemode="a",
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)

redis_client = redis.Redis()

db_config = {
    "host": "localhost",
    "user": "RestApp",
    "password": os.environ.get("MYSQL_PASSWORD"),
    "database": "PlacesExploration"
}

pool = pooling.MySQLConnectionPool(pool_name="RestAppPool", pool_size=20, **db_config)

def generate_map_link(place_id):
    logger.debug(f"Generating map link for place ID: {place_id}")
    map_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
    logger.debug(f"Generated map link: {map_url}")
    return map_url

def extract_address(full_address):
    parts = full_address.split(',')
    address = parts[0] + ',' + parts[1]
    return address.strip()

def number_to_emoji(number):
    digit_to_emoji = {
        '0': '0️⃣',
        '1': '1️⃣',
        '2': '2️⃣',
        '3': '3️⃣',
        '4': '4️⃣',
        '5': '5️⃣',
        '6': '6️⃣',
        '7': '7️⃣',
        '8': '8️⃣',
        '9': '9️⃣'
    }
    return ''.join(digit_to_emoji[digit] for digit in str(number))

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

    connection = pool.get_connection()

    try:
        cursor = connection.cursor()

        query = """
        SELECT place_id, latitude, longitude
        FROM Places
        WHERE latitude BETWEEN %s AND %s
        AND longitude BETWEEN %s AND %s
        """

        cursor.execute(query, (min_lat, max_lat, min_lon, max_lon))
        places_in_bounding_box = cursor.fetchall()
        cursor.close()
    finally:
        connection.close()

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

def is_favourite(place_id, tg_user_id):
    try:
        conn = pool.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
        SELECT COUNT(*) as count
        FROM Favourites
        WHERE place_id = %s AND tg_user_id = %s
        """
        cursor.execute(query, (place_id, tg_user_id))
        result = cursor.fetchone()
        
        is_fav = result['count'] > 0
        
        return is_fav
    
    except mysql.connector.Error as err:
        logger.error(f"Error: {err}")
        return False
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
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
    connection = pool.get_connection()
    try:
        for place_id, place_lat, place_lon in places_in_bounding_box:
            if is_in_range(latitude, longitude, place_lat, place_lon, search_radius):
                query = f"SELECT name, types, formatted_address FROM Places WHERE place_id = '{place_id}'"

                if connection.is_connected():
                    cursor = connection.cursor()
                    cursor.execute(query)
                    place = cursor.fetchall()[0]
                    cursor.close()
                else:
                    logger.error(f"Error while get_places, connection is not connected: {e}")

                name = place[0]
                if type in place[1]:
                    places.append({"place_id": place_id, "name": name, "distance": compute_distance(latitude, longitude, place_lat, place_lon), "formatted_address": place[2]})
    finally:
        connection.close()

    sorted_places = sorted(places, key=lambda x: x['distance'])
    return sorted_places

def convert_relative_time(description):
    if description == "in the last week":
        value = 1
        unit = "week"
    elif description == "a week ago":
        value = 1
        unit = "week"
    elif "a " in description:
        if "month" in description:
            value = 1
            unit = "month"
        elif "year" in description:
            value = 1
            unit = "year"
    else:
        value, unit, _ = description.split(" ")

    time_units = {
        'weeks': datetime.timedelta(weeks=int(value)),
        'week': datetime.timedelta(weeks=int(value)),
        'months': datetime.timedelta(days=30 * int(value)),
        'month': datetime.timedelta(days=30 * int(value)),
        'years': datetime.timedelta(days=365 * int(value)),
        'year': datetime.timedelta(days=365 * int(value))
    }

    return (datetime.datetime.now() - time_units[unit]).date()

def get_place_reviews(place_id):
    query = f"SELECT id, name, score, review, date FROM UsersReviews WHERE place_id = '{place_id}'"
    reviews = []

    connection = pool.get_connection()
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute(query)
            user_reviews = cursor.fetchall()
            cursor.close()
    finally:
        connection.close()

    for elem in user_reviews:
        reviews.append({"author_name": elem[1], "rating": elem[2], "date": elem[4].strftime('%d.%m.%Y'), "text": elem[3]})
    reviews = sorted(reviews, key=lambda x: datetime.datetime.strptime(x['date'], '%d.%m.%Y'), reverse=True)
    query = f"SELECT reviews FROM Places WHERE place_id = '{place_id}'"

    connection = pool.get_connection()
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute(query)
            reviews_str = cursor.fetchall()[0][0]
            cursor.close()
    finally:
        connection.close()


    reviews_google = json.loads(reviews_str)

    if reviews_google is None:
        return None

    for review in reviews_google:
        review["relative_time"] = convert_relative_time(review["relative_time_description"])
    reviews_google = sorted(reviews_google, key=lambda x: x['relative_time'], reverse=True)
    for review in reviews_google:
        reviews.append(review)
    return reviews

def get_photos_for_place(place_id):
    logger.debug(f"Fetching photos for place ID: {place_id}")
    connection = pool.get_connection()
    cursor = connection.cursor()
    try:
        query = "SELECT photo_data FROM PlacePhotos WHERE place_id = %s"
        cursor.execute(query, (place_id,))
        photos = cursor.fetchall()
        photo_list = [photo[0] for photo in photos]
        logger.debug(f"Fetched {len(photo_list)} photos for place ID: {place_id}")
        return photo_list
    except mysql.connector.Error as err:
        logger.error(f"Error fetching photos for place ID {place_id}: {err}")
        return []
    finally:
        cursor.close()
        connection.close()

def get_detailed_place_info(place_id, latitude, longitude, user_id):

    connection = pool.get_connection()
    try:
        if connection.is_connected():
            query = f"SELECT place_id, latitude, longitude, name, formatted_address, weekday_text, rating, price_level, url, website, serves_beer, serves_breakfast, serves_brunch, serves_dinner, serves_lunch, serves_vegetarian_food, serves_wine, opening_hours, photos, types, dine_in, delivery, reservable, reviews, international_phone_number FROM Places WHERE place_id = '{place_id}'"
            cursor = connection.cursor()
            cursor.execute(query)
            place = cursor.fetchall()[0]

            query = f"SELECT place_id FROM Favourites WHERE tg_user_id={user_id}"
            cursor.execute(query)
            favourite_places_db = cursor.fetchall()
            cursor.close()
    finally:
        connection.close()


    favourite_places = []
    for info in favourite_places_db:
        favourite_places.append(info[0])
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
                    "photos": json.loads(place[18]),
                    "types": place[19],
                    "dine_in": place[20],
                    "delivery": place[21],
                    "reservable": place[22],
                    "reviews": place[23],
                    "international_phone_number": place[24]
                }

    logger.info(f"{place_data}")

    address = str(place_data['address'])
    response = ''
    response += f"☕️ {place_data['name']}" + ("⭐️\n\n" if place_id in favourite_places else "\n\n")
    response += f"📍 Адреса: {address}\n"
    response += f"📞 Номер телефону: {place_data['international_phone_number'].replace(' ', '')}\n" if place_data['international_phone_number'] is not None else ''
    response += f"🕒 Статус роботи: {'Відкрито' if place_data['open_now'] else 'Закрито'}\n"
    response += f"📏 Відстань: {int(place_data['distance'])} метрів\n"
    response += f"⭐ Рейтинг: {place_data['rating'] if place_data['rating'] is not None else 'Невідомо 😕'}\n"
    response += f"💰 Рівень Ціни: {place_data['price_level']}\n" if place_data['price_level'] is not None else ''
    response += '🪑 Є місця всередині\n' if place_data.get('dine_in', False) else ''
    response += '🚚 Є доставка\n' if place_data.get('delivery', False) else ''
    response += '📅 Можливе бронювання\n' if place_data.get('reservable', False) else ''

    response += "\n🕓 Графік роботи:\n"
    if place_data["weekday_text"]:
        if "⏳ Графік роботи невідомий 😕" in place_data["weekday_text"]:
            response += " невідомо 😕"
        else:
            response += place_data['weekday_text']
    response = replace_weekdays(response).replace("Closed", "Зачинено 🔒")
    map_link = generate_map_link(place_data["place_id"])
    website = place_data["website"]
    return (response, map_link, website, get_photos_for_place(place_id))

def get_detailed_place_info_without_distance(place_id, user_id):
    connection = pool.get_connection()
    try:
        if connection.is_connected():
            query = f"SELECT place_id, latitude, longitude, name, formatted_address, weekday_text, rating, price_level, url, website, serves_beer, serves_breakfast, serves_brunch, serves_dinner, serves_lunch, serves_vegetarian_food, serves_wine, opening_hours, photos, types, dine_in, delivery, reservable, reviews, international_phone_number FROM Places WHERE place_id = '{place_id}'"
            cursor = connection.cursor()
            cursor.execute(query)
            place = cursor.fetchall()[0]
            query = f"SELECT place_id FROM Favourites WHERE tg_user_id={user_id}"
            cursor.execute(query)
            favourite_places_db = cursor.fetchall()
            cursor.close()
    except Exception as e:
        logger.error(f"Error while get_detailed_place_info_without_distance: {e}")
    finally:
        connection.close()

    favourite_places = []
    for info in favourite_places_db:
        favourite_places.append(info[0])
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
                    "photos": json.loads(place[18]),
                    "types": place[19],
                    "dine_in": place[20],
                    "delivery": place[21],
                    "reservable": place[22],
                    "reviews": place[23],
                    "international_phone_number": place[24]
                }

    address = str(place_data['address'])
    response = ''
    response += f"☕️ {place_data['name']}" + ("⭐️\n\n" if place_id in favourite_places else "\n\n")
    response += f"📍 Адреса: {address}\n"
    response += f"📞 Номер телефону: {place_data['international_phone_number'].replace(' ', '')}\n" if place_data['international_phone_number'] is not None else ''
    response += f"🕒 Статус роботи: {'Відкрито' if place_data['open_now'] else 'Закрито'}\n"
    response += f"⭐ Рейтинг: {place_data['rating'] if place_data['rating'] is not None else 'Невідомо 😕'}\n"
    response += f"💰 Рівень Ціни: {place_data['price_level']}\n" if place_data['price_level'] is not None else ''
    response += '🪑 Є місця всередині\n' if place_data.get('dine_in', False) else ''
    response += '🚚 Є доставка\n' if place_data.get('delivery', False) else ''
    response += '📅 Можливе бронювання\n' if place_data.get('reservable', False) else ''

    response += "\n🕓 Графік роботи:\n"
    
    if place_data["weekday_text"]:
        if "⏳ Графік роботи невідомий 😕" in place_data["weekday_text"]:
            response += " невідомо 😕"
        else:
            response += place_data['weekday_text']
    response = replace_weekdays(response).replace("Closed", "Зачинено 🔒")
    map_link = generate_map_link(place_data["place_id"])
    website = place_data["website"]
    return (response, map_link, website, get_photos_for_place(place_id))

def store_user_location(user_id, latitude, longitude):
    connection = pool.get_connection()
    cursor = connection.cursor()
    try:
        query = """
        INSERT INTO user_locations (user_id, latitude, longitude, timestamp)
        VALUES (%s, %s, %s, NOW())
        """
        cursor.execute(query, (user_id, latitude, longitude))
        connection.commit()
    except mysql.connector.Error as err:
        logger.error(f"Error: {err}")
    finally:
        cursor.close()
        connection.close()

def get_latest_position(user_id, time_limit_minutes):
    connection = pool.get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        time_limit = datetime.datetime.now() - datetime.timedelta(minutes=time_limit_minutes)
        
        query = """
        SELECT latitude, longitude, timestamp
        FROM user_locations
        WHERE user_id = %s AND timestamp >= %s
        ORDER BY timestamp DESC
        LIMIT 1
        """
        cursor.execute(query, (user_id, time_limit))
        result = cursor.fetchone()
        
        if result:
            return {
                'latitude': result['latitude'],
                'longitude': result['longitude'],
                'timestamp': result['timestamp']
            }
        else:
            return None 

    except mysql.connector.Error as err:
        logger.error(f"Error: {err}")
        return None
    finally:
        cursor.close()
        connection.close()

BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TeleBot(BOT_TOKEN)
logger.info("Bot is started")

start_keyboard_list_non_auth = ["🔍Пошук закладів", "⚙️Налаштування"]
start_keyboard_non_auth = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in start_keyboard_list_non_auth:
    start_keyboard_non_auth.add(types.KeyboardButton(text=button))

start_keyboard_list_auth = ["🔍Пошук закладів", "⚙️Налаштування", "📝Редагувати відгуки", "🌟Обрані заклади"]
start_keyboard_auth = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in start_keyboard_list_auth:
    start_keyboard_auth.add(types.KeyboardButton(text=button))

settings_keyboard_button_list = ["📏Змінити радіус пошуку"]
settings_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in settings_keyboard_button_list:
    settings_keyboard.add(types.KeyboardButton(text=button))

location_keyboard_buttons_list = ["🔍Пошук закладів", "⚙️Налаштування"]
location_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in location_keyboard_buttons_list:
    location_keyboard.add(types.KeyboardButton(text=button))

ranges_list = ["250", "500", "1000", "1500", "2000", "3000", "4000", "5000"]
set_range_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
ranges_chunks = [ranges_list[i:i+2] for i in range(0, len(ranges_list), 2)]
for chunk in ranges_chunks[:-1]:
    set_range_keyboard.add(types.KeyboardButton(text=chunk[0]), types.KeyboardButton(text=chunk[1]))
if len(ranges_list) % 2 != 0:
    last_chunk = ranges_chunks[-1]
    set_range_keyboard.add(types.KeyboardButton(text=last_chunk[0]))
else:
    last_chunk = ranges_chunks[-1]
    set_range_keyboard.add(types.KeyboardButton(text=chunk[0]), types.KeyboardButton(text=chunk[1]))

search_option_keyboard_buttons_list = ["☕Кафе", "🍽️Ресторан", "🍹Бар"]
search_option_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in search_option_keyboard_buttons_list:
    search_option_keyboard.add(types.KeyboardButton(text=button))

class States:
    MAIN_MENU = "MAIN_MENU"
    SETTINGS = "SETTINGS"
    CHANGE_SEARCH_RADIUS = "CHANGE_SEARCH_RADIUS"
    EDIT_REVIEWS = "EDIT_REVIEWS"
    FAVOURITES = "FAVOURITES"
    HANDLE_KEYWORDS_FOR_SEARCH = "HANDLE_KEYWORDS_FOR_SEARCH"
    SEARCHING = "SEARCHING"

def set_user_state(user_id, state):
    redis_client.set(f"state_{user_id}", state)

def get_user_state(user_id):
    state_bytes = redis_client.get(f"state_{user_id}")
    if state_bytes is not None:
        return state_bytes.decode('utf-8')
    return None

def send_main_menu(chat_id, user_id):
    if check_if_user_auth(user_id):
        bot.send_message(chat_id,
                        """👋 Вітаю! Цей бот допоможе вам знайти ☕ кафе та 🍽️ ресторани поблизу. \n
                          🔽Оберіть дію:""",
                        reply_markup=start_keyboard_auth)
    else:
        bot.send_message(chat_id,
                        """👋 Вітаю! Цей бот допоможе вам знайти ☕ кафе та 🍽️ ресторани поблизу. \n
                          🔽Оберіть дію:""",
                        reply_markup=start_keyboard_non_auth)

@bot.message_handler(commands=['main_menu'])
def main_menu_handler(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    set_user_state(user_id, States.MAIN_MENU)
    send_main_menu(chat_id, user_id)

@bot.message_handler(commands=['back'])
def back_handler(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    state = get_user_state(user_id)
    print(state)
    print(States.CHANGE_SEARCH_RADIUS)
    if state == States.MAIN_MENU:
        set_user_state(user_id, States.MAIN_MENU)
        send_main_menu(chat_id, user_id)
    elif state == States.SETTINGS:
        set_user_state(user_id, States.MAIN_MENU)
        send_main_menu(chat_id, user_id)
    elif state == States.CHANGE_SEARCH_RADIUS:
        set_user_state(user_id, States.SETTINGS)
        bot.send_message(chat_id, "Оберіть налаштування:", reply_markup=settings_keyboard)
    elif state == States.EDIT_REVIEWS:
        set_user_state(user_id, States.MAIN_MENU)
        send_main_menu(chat_id, user_id)
    elif state == States.FAVOURITES:
        set_user_state(user_id, States.MAIN_MENU)
        send_main_menu(chat_id, user_id)
    elif state == States.HANDLE_KEYWORDS_FOR_SEARCH:
        set_user_state(user_id, States.MAIN_MENU)
        send_main_menu(chat_id, user_id)
    elif state == States.SEARCHING:
        set_user_state(user_id, States.HANDLE_KEYWORDS_FOR_SEARCH)
        bot.send_message(chat_id, "Оберіть тип закладу для пошуку:", reply_markup=search_option_keyboard)
        bot.register_next_step_handler(message, handle_keywords_for_search)
    else:
        bot.send_message(chat_id, "Неможливо повернутись назад, повертаю в головне меню", reply_markup=start_keyboard_auth)
        
def check_if_user_auth(user_id):
    connection = pool.get_connection()
    try:
        if connection.is_connected():
            query = f"SELECT * FROM Users WHERE tg_user_id = {user_id}"
            cursor = connection.cursor()
            cursor.execute(query)
            result = cursor.fetchall()
            cursor.close()
    finally:
        connection.close()
    return result != None

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    redis_client.delete(message.chat.id)
    redis_client.set(str(message.chat.id) + "_range", 300)

    if check_if_user_auth(user_id):
        bot.send_message(message.chat.id,
                    """👋 Вітаю! Цей бот допоможе вам знайти ☕ кафе та 🍽️ ресторани поблизу. \n
                      🔽Оберіть дію:""",
                    reply_markup=start_keyboard_auth)
    else:
        bot.send_message(message.chat.id, "📞Будь-ласка, поділіться вашим номером телефону для авторизації:", reply_markup=types.ReplyKeyboardMarkup(
                            one_time_keyboard=True,
                            resize_keyboard=True,
                            selective=True
                        ).add(types.KeyboardButton(text="📞Поділитися номером телефону", request_contact=True)))

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    phone_number = message.contact.phone_number
    user_id = message.from_user.id

    connection = pool.get_connection()
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM Users WHERE tg_user_id = %s", (user_id,))
            existing_user = cursor.fetchone()
            connection.commit()
            cursor.close()
    finally:
        connection.close()

    if existing_user:
        pass
    else:
        connection = pool.get_connection()
        try:
            if connection.is_connected():
                sql = """INSERT INTO Users (tg_user_id, phone_number) VALUES (%s, %s)"""
                values = (user_id, phone_number)
                cursor = connection.cursor()
                cursor.execute(sql, values)
                connection.commit()
                cursor.close()
        finally:
            connection.close()

    bot.send_message(message.chat.id, "✅Авторизація успішна!")
    bot.send_message(message.chat.id,
                        """👋 Вітаю! Цей бот допоможе вам знайти ☕ кафе та 🍽️ ресторани поблизу. \n
                        🔽Оберіть дію:""",
                        reply_markup=start_keyboard_auth)

@bot.message_handler(content_types=['location'])
def save_location(message):
    location_string = f"{message.location.latitude},{message.location.longitude}"
    redis_client.set(message.chat.id, location_string)
    store_user_location(message.from_user.id, message.location.latitude, message.location.longitude)
    bot.send_message(message.chat.id, "📝Запам'ятав", reply_markup=location_keyboard)

def show_favourites(user_id, chat_id):
    connection = pool.get_connection()
    try:
        if connection.is_connected():
            query = f"SELECT place_id FROM Favourites WHERE tg_user_id = {user_id}"
            cursor = connection.cursor()
            cursor.execute(query)
            place_ids = cursor.fetchall()
            cursor.close()
    finally:
        connection.close()
    places = []
    for place in place_ids:
        places.append({"place_id": place[0]})
    if not places:
        bot.send_message(chat_id, "🔍За вашим запитом нічого не знайдено.", reply_markup=start_keyboard_auth)
        logger.debug("No places found for the search query.")
        return
    redis_client.delete(f'{chat_id}_places')
    for dictionary in places:
        redis_client.rpush(f'{chat_id}_places', json.dumps(dictionary))
    first_place = redis_client.lindex(f'{chat_id}_places', 0)
    if first_place:
        first_place = json.loads(first_place)
        response_places, map_link, website, photos = get_detailed_place_info_without_distance(first_place["place_id"], user_id)
        keyboard_places = types.InlineKeyboardMarkup(row_width=2)
        if map_link:
            keyboard_places.add(types.InlineKeyboardButton(text="🗺️Відобразити на мапі", url=map_link))
        if website is not None:
            keyboard_places.add(types.InlineKeyboardButton(text="🌐Вебсайт", url=website))
        keyboard_places.add(
                types.InlineKeyboardButton("❌Прибрати з обраних", callback_data=f"removefromfavourites_{user_id}_{first_place['place_id']}"),
        )
        keyboard_places.add(
                types.InlineKeyboardButton("📝Переглянути відгуки", callback_data=f"sendreviews_{first_place['place_id']}"),
            )
        keyboard_places.add(
                types.InlineKeyboardButton("➕Додати відгук", callback_data=f"addreview_{first_place['place_id']}"),
            )
        keyboard_places.add(
            types.InlineKeyboardButton("➡️", callback_data=f"placefavourites_{1}"),
        )
        redis_client.delete(f"{chat_id}_places_message")
        sent_message_places = bot.send_message(chat_id, response_places, reply_markup=keyboard_places)
        redis_client.set(f"{chat_id}_places_message", sent_message_places.message_id)

@bot.message_handler(content_types=['text'])
def handle_commands(message):
    if message.text == "⚙️Налаштування":
        set_user_state(message.from_user.id, States.SETTINGS)
        bot.send_message(message.chat.id, "Оберіть налаштування:", reply_markup=settings_keyboard)
    elif message.text == "/back":
        back_handler(message)
    elif message.text == "🌟Обрані заклади":
        set_user_state(message.from_user.id, States.FAVOURITES)
        show_favourites(message.from_user.id, message.chat.id)
    elif message.text == "🔍Пошук закладів":
        set_user_state(message.from_user.id, States.HANDLE_KEYWORDS_FOR_SEARCH)
        bot.send_message(message.chat.id, "Оберіть тип закладу для пошуку:", reply_markup=search_option_keyboard)
        bot.register_next_step_handler(message, handle_keywords_for_search)
    elif message.text == "📝Редагувати відгуки":
        set_user_state(message.from_user.id, States.EDIT_REVIEWS)
        user_id = message.from_user.id
        connection = pool.get_connection()
        try:
            if connection.is_connected():
                query = f"SELECT id, place_id, name, score, review, date FROM UsersReviews WHERE tg_user_id = {user_id}"
                cursor = connection.cursor()
                cursor.execute(query)
                user_reviews = cursor.fetchall()
                cursor.close()
        finally:
            connection.close()

        user_reviews_list = []
        for review in user_reviews:
            user_reviews_list.append({"id": review[0], "place_id": review[1], "name": review[2], "score": review[3], "review": review[4], "date": review[5].strftime('%Y-%m-%d %H:%M:%S')})

        redis_client.delete(f'{message.chat.id}_reviews_edit')
        if len(user_reviews_list) != 0:
            for dictionary in user_reviews_list:
                redis_client.rpush(f'{message.chat.id}_reviews_edit', json.dumps(dictionary))

            inline_keyboard = types.InlineKeyboardMarkup(row_width=2)
            if len(user_reviews_list) > 1:
                inline_keyboard.add(
                        types.InlineKeyboardButton("➡️", callback_data=f"reviewedit_{1}"),
                    )
            inline_keyboard.add(
                    types.InlineKeyboardButton("✏️Редагувати", callback_data=f"editreview_{review[0]}"),
                )
            response_first_review = get_review_response(user_reviews_list[0]["name"], user_reviews_list[0]["score"], user_reviews_list[0]["date"], user_reviews_list[0]["review"])
            sent_message_reviews = bot.send_message(message.chat.id, response_first_review, reply_markup=inline_keyboard)
            redis_client.set(f"{message.chat.id}_message_reviews_edit", sent_message_reviews.message_id)
        else:
            set_user_state(message.from_user.id, States.MAIN_MENU)
            bot.send_message(message.chat.id, "Ви ще не залишали відгуків", reply_markup=start_keyboard_auth)
    elif message.text == "📏Змінити радіус пошуку":
        set_user_state(message.from_user.id, States.CHANGE_SEARCH_RADIUS)
        bot.send_message(message.chat.id, "📏Оберіть бажаний радіус пошуку", reply_markup=set_range_keyboard)
    elif message.text in ranges_list:
        bot.send_message(message.chat.id, "✅Обрано", reply_markup=start_keyboard_auth)
        try:
            redis_client.set(str(message.chat.id) + "_range", int(message.text))
        except ValueError:
            set_user_state(message.from_user.id, States.MAIN_MENU)
            bot.send_message(message.chat.id, "❗️Виникла помилка, спробуйте ще раз", reply_markup=start_keyboard_auth)
    else:
        set_user_state(message.from_user.id, States.MAIN_MENU)
        bot.send_message(message.chat.id, "🚫Такої команди не існує, почніть заново", reply_markup=start_keyboard_auth)

def handle_keywords_for_search(message):
    if message.text in search_option_keyboard_buttons_list:
        if message.text == "☕Кафе":
            search(message, type="cafe")
        elif message.text == "🍽️Ресторан":
            search(message, type="restaurant")
        elif message.text == "🍹Бар":
            search(message, type="bar")

def show_next_or_prev_favourite_place(user_id, chat_id, call_id, index):
    message_id = redis_client.get(f"{chat_id}_places_message")
    if message_id is None:
        bot.answer_callback_query(call_id, "Сталася помилка. Спробуйте ще раз")
        return
    message_id = message_id.decode()
    place_data = redis_client.lindex(f'{chat_id}_places', index)
    len_places = redis_client.llen(f'{chat_id}_places')
    if place_data is None:
        bot.answer_callback_query(call_id, "No more results.")
        return
    place_data = json.loads(place_data)
    response, map_link, website, place_photos = get_detailed_place_info_without_distance(place_data["place_id"], chat_id)
    inline_keyboard = types.InlineKeyboardMarkup(row_width=2)
    if map_link:
        inline_keyboard.add(types.InlineKeyboardButton(text="🗺️Відобразити на мапі", url=map_link))
    if website is not None:
        inline_keyboard.add(types.InlineKeyboardButton(text="🌐Вебсайт", url=website))
    inline_keyboard.add(
            types.InlineKeyboardButton("❌Прибрати з обраних", callback_data=f"removefromfavourites_{chat_id}_{place_data['place_id']}"),
        )
    inline_keyboard.add(
            types.InlineKeyboardButton("📝Переглянути відгуки", callback_data=f"sendreviews_{place_data['place_id']}"),
        )
    inline_keyboard.add(
            types.InlineKeyboardButton("➕Додати відгук", callback_data=f"addreview_{place_data['place_id']}"),
        )
    if index > 0 and index < len_places - 1:
        inline_keyboard.add(
            types.InlineKeyboardButton("⬅️", callback_data=f"placefavourites_{index - 1}"),
            types.InlineKeyboardButton("➡️", callback_data=f"placefavourites_{index + 1}"),
        )
    elif index == 0 and index < len_places - 1:
        inline_keyboard.add(
            types.InlineKeyboardButton("➡️", callback_data=f"placefavourites_{index + 1}"),
        )
    elif index > 0 and index >= len_places - 1:
        inline_keyboard.add(
            types.InlineKeyboardButton("⬅️", callback_data=f"placefavourites_{index - 1}"),
        )
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response, reply_markup=inline_keyboard, parse_mode="html")
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        bot.answer_callback_query(call_id, "Сталася помилка. Спробуйте ще раз")

def send_next_review_for_edit(chat_id, call_id, index):
    message_id = redis_client.get(f"{chat_id}_message_reviews_edit")
    len_reviews = redis_client.llen(f'{chat_id}_reviews_edit')
    review_data = json.loads(redis_client.lindex(f'{chat_id}_reviews_edit', index))
    inline_keyboard = types.InlineKeyboardMarkup(row_width=2)
    if index > 0 and index < len_reviews - 1:
        inline_keyboard.add(
            types.InlineKeyboardButton("⬅️", callback_data=f"reviewedit_{index - 1}"),
            types.InlineKeyboardButton("➡️", callback_data=f"reviewedit_{index + 1}"),
        )
    elif index == 0 and index < len_reviews - 1:
        inline_keyboard.add(
            types.InlineKeyboardButton("➡️", callback_data=f"reviewedit_{index + 1}"),
        )
    elif index > 0 and index >= len_reviews - 1:
        inline_keyboard.add(
            types.InlineKeyboardButton("⬅️", callback_data=f"reviewedit_{index - 1}"),
        )
    inline_keyboard.add(
            types.InlineKeyboardButton("✏️Редагувати", callback_data=f"editreview_{review_data['id']}"),
        )
    response_reviews = get_review_response(review_data["name"], review_data["score"], review_data["date"], review_data["review"])
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response_reviews, reply_markup=inline_keyboard)
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        bot.answer_callback_query(call_id, "Сталася помилка. Спробуйте ще раз")

def add_place_to_favourites(call_id, place_id, user_id):
    query_insert = f"INSERT IGNORE INTO Favourites (place_id, tg_user_id) VALUES ('{place_id}', '{user_id}')"
    connection = pool.get_connection()
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute(query_insert)
            connection.commit()
            cursor.close()
            bot.answer_callback_query(call_id, "Заклад успішно додано до обраних")
    except Exception as e:
        connection.rollback()
        logger.error(f"An error occurred while adding to favourites: {e}")
    finally:
        connection.close()

def show_next_place(chat_id, call_id, index, latitude, longitude, user_id):
    message_id = redis_client.get(f"{chat_id}_places_message")
    if message_id is None:
        bot.answer_callback_query(call_id, "Сталася помилка. Спробуйте ще раз")
        return
    message_id = message_id.decode()
    place_data = redis_client.lindex(f'{chat_id}_places', index)
    len_places = redis_client.llen(f'{chat_id}_places')
    if place_data is None:
        bot.answer_callback_query(call_id, "Більше результатів немає")
        return
    place_data = json.loads(place_data)
    if redis_client.exists(f"{chat_id}_reviews_message"):
        message_id_reviews = redis_client.get(f"{chat_id}_reviews_message")
        try:
            bot.delete_message(chat_id=chat_id, message_id=message_id_reviews)
        except Exception as e:
            logger.exception(f"Error while deleting message: {e}")
        redis_client.delete(f"{chat_id}_reviews_message")
    response, map_link, website = get_detailed_place_info(place_data["place_id"], latitude, longitude, user_id)
    inline_keyboard = types.InlineKeyboardMarkup(row_width=2)
    if map_link:
        inline_keyboard.add(types.InlineKeyboardButton(text="🗺️Відобразити на мапі", url=map_link))
    if website is not None:
        inline_keyboard.add(types.InlineKeyboardButton(text="🌐Вебсайт", url=website))
    inline_keyboard.add(
            types.InlineKeyboardButton("⭐Додати до обраних", callback_data=f"favourites_{place_data['place_id']}"),
        )
    inline_keyboard.add(
            types.InlineKeyboardButton("📝Переглянути відгуки", callback_data=f"sendreviews_{place_data['place_id']}"),
        )
    inline_keyboard.add(
            types.InlineKeyboardButton("➕Додати відгук", callback_data=f"addreview_{place_data['place_id']}"),
        )
    if index > 0 and index < len_places - 1:
        inline_keyboard.add(
            types.InlineKeyboardButton("⬅️", callback_data=f"place_{index - 1}_{latitude}_{longitude}_{type}"),
            types.InlineKeyboardButton("➡️", callback_data=f"place_{index + 1}_{latitude}_{longitude}_{type}"),
        )
    elif index == 0 and index < len_places - 1:
        inline_keyboard.add(
            types.InlineKeyboardButton("➡️", callback_data=f"place_{index + 1}_{latitude}_{longitude}_{type}"),
        )
    elif index > 0 and index >= len_places - 1:
        inline_keyboard.add(
            types.InlineKeyboardButton("⬅️", callback_data=f"place_{index - 1}_{latitude}_{longitude}_{type}"),
        )
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response, reply_markup=inline_keyboard, parse_mode="html")
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        bot.answer_callback_query(call_id, "Сталася помилка. Спробуйте ще раз")

def show_next_review(chat_id, call_id, index):
    message_id = redis_client.get(f"{chat_id}_reviews_message")
    if message_id is None:
        bot.answer_callback_query(call_id, "Сталася помилка. Спробуйте ще раз")
        return
    message_id = message_id.decode()
    review_data = redis_client.lindex(f'{chat_id}_reviews', index)
    len_reviews = redis_client.llen(f'{chat_id}_reviews')
    if review_data is None:
        bot.answer_callback_query(call_id, "Більше нема :)")
        return
    review_data = json.loads(review_data)
    if "relative_time_description" in review_data:
        response_reviews = get_review_response(review_data["author_name"], str(review_data["rating"]), review_data["relative_time"], review_data["text"])
    elif "date" in review_data:
        response_reviews = get_review_response(review_data["author_name"], str(review_data["rating"]), review_data["date"], review_data["text"])
    inline_keyboard = types.InlineKeyboardMarkup(row_width=2)
    if index > 0 and index < len_reviews - 1:
        inline_keyboard.add(
            types.InlineKeyboardButton("⬅️", callback_data=f"review_{index - 1}"),
            types.InlineKeyboardButton("➡️", callback_data=f"review_{index + 1}"),
        )
    elif index == 0 and index < len_reviews - 1:
        inline_keyboard.add(
            types.InlineKeyboardButton("➡️", callback_data=f"review_{index + 1}"),
        )
    elif index > 0 and index >= len_reviews - 1:
        inline_keyboard.add(
            types.InlineKeyboardButton("⬅️", callback_data=f"review_{index - 1}"),
        )
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response_reviews, reply_markup=inline_keyboard)
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        bot.answer_callback_query(call_id, "Сталася помилка. Спробуйте ще раз")

def send_place_reviews(call_id, chat_id, place_id):
    reviews = get_place_reviews(place_id)
    chat_id = str(chat_id)
    redis_client.delete(f'{chat_id}_reviews')
    if reviews is None:
        bot.answer_callback_query(call_id, "Для цього закладу ще немає відгуків")
        return
    if "date" in reviews[0]:
        response_reviews = get_review_response(reviews[0]["author_name"], str(reviews[0]["rating"]), reviews[0]["date"], reviews[0]["text"])
    elif "relative_time_description":
        response_reviews = get_review_response(reviews[0]["author_name"], str(reviews[0]["rating"]), reviews[0]["relative_time"], reviews[0]["text"])
    keyboard_reviews = types.InlineKeyboardMarkup(row_width=2)
    keyboard_reviews.add(
        types.InlineKeyboardButton("➡️", callback_data=f"review_{1}"),
    )
    if len(reviews) != 0:
        for dictionary in reviews:
            if "date" in dictionary:
                dictionary["date"] = dictionary["date"]
            if "relative_time" in dictionary:
                dictionary["relative_time"] = datetime.datetime.strftime(dictionary['relative_time'], '%d.%m.%Y')
            redis_client.rpush(f'{chat_id}_reviews', json.dumps(dictionary))
    else:
        keyboard_reviews = None
    redis_client.delete(f"{chat_id}_reviews_message")
    sent_message_reviews = bot.send_message(chat_id, response_reviews, reply_markup=keyboard_reviews)
    redis_client.set(f"{chat_id}_reviews_message", sent_message_reviews.message_id)

def get_review_response(name, score, date_or_str, review):
    if isinstance(date_or_str, datetime.date):
        date = date_or_str.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(date_or_str, str):
        date = date_or_str
    else:
        logger.error("Invalid type in get_review_response")

    response_review = f"👤Автор: {name}\n⭐Оцінка: {score}\n📅Дата: {date}\n📝Відгук: {review}"
    return response_review

def add_review(message, chat_id, place_id):
    chat_id = str(chat_id)
    bot.send_message(chat_id, "👤Введіть ваше ім'я:")
    bot.register_next_step_handler(message, handle_name, place_id=place_id)

def edit_review(message, chat_id, review_id):
    chat_id = str(chat_id)
    bot.send_message(chat_id, "👤Введіть ваше ім'я:")
    bot.register_next_step_handler(message, handle_name, review_id=review_id)

def show_next_page(page_size, index, chat_id, latitude, longitude):
    page_size = 5
    places_length = redis_client.llen(f"{chat_id}_places")
    index = int(index)
    start_index =  index * page_size
    end_index = start_index + page_size
    if end_index >= places_length:
        end_index = places_length - 1
    places = redis_client.lrange(f"{chat_id}_places", start_index, end_index - 1)
    places = [json.loads(place) for place in places]
    names = [elem["name"] for elem in places]
    response = "☕️ Топ заклади поруч з вами\n"
    for i in range(start_index, end_index):
        response += f"{i+1}. {names[i - start_index]}\n"
        distance = int(places[i - start_index]["distance"])
        formatted_address = extract_address(places[i - start_index]["formatted_address"])
        response += f"🧭 {distance}м\n"
        response += f"📍 {formatted_address}\n"
    keyboard_places = types.InlineKeyboardMarkup()
    if end_index < places_length - 1 and start_index > 0:
        keyboard_places.row(types.InlineKeyboardButton("⬅️", callback_data=f"prevpage_{index-1}_{chat_id}_{latitude}_{longitude}"), types.InlineKeyboardButton("➡️", callback_data=f"nextpage_{index+1}_{chat_id}_{latitude}_{longitude}"))
    elif start_index > 0 and end_index >= places_length - 1:
        keyboard_places.row(types.InlineKeyboardButton("⬅️", callback_data=f"prevpage_{index-1}_{chat_id}_{latitude}_{longitude}"))
    elif start_index <= 0 and end_index < places_length - 1:
        keyboard_places.row(types.InlineKeyboardButton("➡️", callback_data=f"nextpage_{index+1}_{chat_id}_{latitude}_{longitude}"))
    number_buttons = []
    for i in range(len(places)):
        number_buttons.append(types.InlineKeyboardButton(f"{number_to_emoji(i+start_index+1)}", callback_data=f"sendplace_{latitude}_{longitude}_{places[i]['place_id']}"))
    keyboard_places.row(*number_buttons)
    message_id = redis_client.get(f"sentmessageplaces_{chat_id}")
    bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response, reply_markup=keyboard_places)

def show_prev_page(page_size, index, chat_id, latitude, longitude):
    places_length = redis_client.llen(f"{chat_id}_places")
    index = int(index)
    start_index =  index * page_size
    end_index = start_index + page_size
    if end_index >= places_length:
        end_index = places_length - 1
    places = redis_client.lrange(f"{chat_id}_places", start_index, end_index - 1)
    places = [json.loads(place) for place in places]
    names = [elem["name"] for elem in places]
    response = "☕️ Топ заклади поруч з вами\n"
    for i in range(start_index, end_index):
        response += f"{i+1}. {names[i - start_index]}\n"
        distance = int(places[i - start_index]["distance"])
        formatted_address = extract_address(places[i - start_index]["formatted_address"])
        response += f"🧭 {distance}м\n"
        response += f"📍 {formatted_address}\n"
    keyboard_places = types.InlineKeyboardMarkup()
    if end_index < places_length - 1 and start_index > 0:
        keyboard_places.row(types.InlineKeyboardButton("⬅️", callback_data=f"prevpage_{index-1}_{chat_id}_{latitude}_{longitude}"), types.InlineKeyboardButton("➡️", callback_data=f"nextpage_{index+1}_{chat_id}_{latitude}_{longitude}"))
    elif start_index > 0 and end_index >= places_length - 1:
        keyboard_places.row(types.InlineKeyboardButton("⬅️", callback_data=f"prevpage_{index-1}_{chat_id}_{latitude}_{longitude}"))
    elif start_index <= 0 and end_index < places_length - 1:
        keyboard_places.row(types.InlineKeyboardButton("➡️", callback_data=f"nextpage_{index+1}_{chat_id}_{latitude}_{longitude}"))
    number_buttons = []
    for i in range(len(places)):
        number_buttons.append(types.InlineKeyboardButton(f"{number_to_emoji(i+start_index+1)}", callback_data=f"sendplace_{latitude}_{longitude}_{places[i]['place_id']}"))
    keyboard_places.row(*number_buttons)
    message_id = redis_client.get(f"sentmessageplaces_{chat_id}")
    bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response, reply_markup=keyboard_places)

def remove_from_favourites(place_id, user_id):
    query = f"DELETE FROM Favourites WHERE place_id='{place_id}' AND tg_user_id={user_id}"
    connection = pool.get_connection()
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute(query)
            connection.commit()
            cursor.close()
    except Exception as e:
        connection.rollback()
        logger.error(f"An error occurred while adding to favourites: {e}")
    finally:
        connection.close()

def send_place_info(chat_id, user_id, place_id, latitude, longitude):
    sent_message_id = redis_client.get(f"place_message_id_{chat_id}")
    photos_message_ids = redis_client.lrange(f"place_photos_id_{chat_id}", 0, -1)
    if photos_message_ids:
        for message_id in photos_message_ids:
            try:
                bot.delete_message(chat_id=chat_id, message_id=message_id)
            except:
                pass
        redis_client.delete(f"place_photos_id_{chat_id}")
    
    if sent_message_id: 
        try:
            bot.delete_message(chat_id=chat_id, message_id=sent_message_id)
        except:
            pass
    
    place_is_favourite = is_favourite(place_id, chat_id)
    
    response, map_link, website, photos = get_detailed_place_info(place_id, latitude, longitude, chat_id)
    inline_keyboard = types.InlineKeyboardMarkup(row_width=2)
    if map_link:
        inline_keyboard.add(types.InlineKeyboardButton(text="🗺️Відобразити на мапі", url=map_link))
    if website is not None:
        inline_keyboard.add(types.InlineKeyboardButton(text="🌐Вебсайт", url=website))
    if place_is_favourite:
        inline_keyboard.add(
                types.InlineKeyboardButton("❌Прибрати з обраних", callback_data=f"removefromfavourites_{user_id}_{place_id}"),
        )
    else:
        inline_keyboard.add(
            types.InlineKeyboardButton("⭐Додати до обраних", callback_data=f"favourites_{place_id}"),
        )
    inline_keyboard.add(
        types.InlineKeyboardButton("📝Переглянути відгуки", callback_data=f"sendreviews_{place_id}"),
    )
    inline_keyboard.add(
        types.InlineKeyboardButton("➕Додати відгук", callback_data=f"addreview_{place_id}"),
    )
    media = []
    for index, photo in enumerate(photos):
        media.append(types.InputMediaPhoto(photo))
    
    if media:
        media_messages = bot.send_media_group(chat_id, media)
        photo_message_ids = [msg.message_id for msg in media_messages]
    else:
        photo_message_ids = []
    
    for message_id in photo_message_ids:
        redis_client.rpush(f"place_photos_id_{chat_id}", message_id)
        
    place_message_id = bot.send_message(chat_id, response, reply_markup=inline_keyboard).message_id
    redis_client.set(f"place_message_id_{chat_id}", place_message_id)

@bot.callback_query_handler(func=lambda call: True)
def handle_navigation(call):
    data = call.data.split("_")
    try:
        if data[0] == "place":
            prefix, index, latitude, longitude, type = data
            index = int(index)
            show_next_place(chat_id, call.id, index, latitude, longitude, user_id)
        elif data[0] == "review":
            prefix, index = data
            index = int(index)
            show_next_review(call.id, chat_id, place_id)
        elif data[0] == "favourites":
            prefix = data[0]
            place_id = '_'.join(data[1:])
            add_place_to_favourites(call.id, place_id, user_id)
        elif data[0] == "placefavourites":
            prefix, index = data
            index = int(index)
            chat_id = call.message.chat.id
            show_next_or_prev_favourite_place(user_id, chat_id, call.id, index)
        elif data[0] == "sendreviews":
            prefix = data[0]
            place_id = '_'.join(data[1:])
            send_place_reviews(call.id, chat_id, place_id)
        elif data[0] == "addreview":
            prefix = data[0]
            place_id = '_'.join(data[1:])
            add_review(call.message, chat_id, place_id)
        elif data[0] == "reviewedit":
            prefix, index = data
            index = int(index)
            send_next_review_for_edit(chat_id, call.id, index)
        elif data[0] == "editreview":
            prefix, review_id = data
            edit_review(call.message, chat_id, review_id)
        elif data[0] == "removefromfavourites":
            prefix = data[0]
            user_id = data[1]
            place_id = '_'.join(data[2:])
            remove_from_favourites(place_id, user_id)
            bot.answer_callback_query(call.id, "Заклад успішно прибрано з обраних")
        elif data[0] == "nextpage":
            prefix = data[0]
            index = data[1]
            user_id = data[2]
            latitude = data[3]
            longitude = data[4]
            chat_id = call.message.chat.id
            show_next_page(5, index, chat_id, latitude, longitude)
        elif data[0] == "prevpage":
            prefix = data[0]
            index = data[1]
            user_id = data[2]
            latitude = data[3]
            longitude = data[4]
            chat_id = call.message.chat.id
            show_prev_page(5, index, chat_id, latitude, longitude)
        elif data[0] == "sendplace":
            prefix = data[0]
            latitude = data[1]
            longitude = data[2]
            place_id = '_'.join(data[3:])
            chat_id = call.message.chat.id
            user_id = call.message.from_user.id
            send_place_info(chat_id, user_id, place_id, latitude, longitude)  
            
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        bot.answer_callback_query(call.id, "Сталася помилка. Спробуйте ще раз")

def handle_name(message, place_id=None, review_id=None):
    if message.text == "/start":
        bot.send_message(message.chat.id,
                    """Вітаю! Цей бот допоможе вам знайти кафе та ресторани поблизу. \n
                    🔽Оберіть дію:""",
                    reply_markup=start_keyboard_auth)
        return
    if message.text:
        redis_client.set(f"review_{place_id}_name_{message.chat.id}", message.text)
        bot.send_message(message.chat.id, "⭐Введіть оцінку від 1 до 5:")
        bot.register_next_step_handler(message, handle_score, place_id=place_id, review_id=review_id)
    else:
        bot.send_message(message.chat.id, "⚠️Ви надіслали порожнє повідомлення, введіть ім'я:")
        bot.register_next_step_handler(message, handle_name, place_id=place_id, review_id=review_id)

def handle_score(message, place_id=None, review_id=None):
    if message.text == "/start":
        bot.send_message(message.chat.id,
                    """Вітаю! Цей бот допоможе вам знайти кафе та ресторани поблизу. \n
                    🔽Оберіть дію:""",
                    reply_markup=start_keyboard_auth)
        return
    if message.text:
        try:
            score = int(message.text)
        except Exception as e:
            logger.exception(f"Error while getting score for review: {e}")
            bot.send_message(message.chat.id, "⚠️Треба ввести оцінку від 1 до 5:")
            bot.register_next_step_handler(message, handle_score, place_id=place_id, review_id=review_id)
            return
        if score < 1 or score > 5:
            bot.send_message(message.chat.id, "⚠️Треба ввести оцінку від 1 до 5:")
            bot.register_next_step_handler(message, handle_score, place_id=place_id, review_id=review_id)
            return
        redis_client.set(f"review_{place_id}_score_{message.chat.id}", message.text)
        bot.send_message(message.chat.id, "📝Введіть відгук:")
        bot.register_next_step_handler(message, handle_review, place_id=place_id, review_id=review_id)
    else:
        bot.send_message(message.chat.id, "⚠️Ви надіслали порожнє повідомлення, введіть оцінку:")
        bot.register_next_step_handler(message, handle_score, place_id=place_id, review_id=review_id)

def handle_review(message, place_id=None, review_id=None):
    if message.text == "/start":
        bot.send_message(message.chat.id,
                    """Вітаю! Цей бот допоможе вам знайти кафе та ресторани поблизу. \n
                    🔽Оберіть дію:""",
                    reply_markup=start_keyboard_auth)
        return
    if message.text:
        name = redis_client.get(f"review_{place_id}_name_{message.chat.id}")
        name = name.decode('utf-8')
        score = int(redis_client.get(f"review_{place_id}_score_{message.chat.id}"))
        review = message.text
        date = datetime.datetime.now()
        connection = pool.get_connection()
        if place_id:
            query = f"INSERT INTO UsersReviews (place_id, name, tg_user_id, score, review, date) VALUES ('{place_id}', '{name}', {message.from_user.id}, {score}, '{review}', '{date.strftime('%Y-%m-%d %H:%M:%S')}')"
            try:
                if connection.is_connected():
                    cursor = connection.cursor()
                    cursor.execute(query)
                    connection.commit()
                    cursor.close()
                    bot.send_message(message.chat.id, "✅Ваш відгук успішно додано!")
            finally:
                connection.close()
        elif review_id:
            query = f"UPDATE UsersReviews SET name='{name}', tg_user_id={message.from_user.id}, score={score}, review='{review}', date='{date.strftime('%Y-%m-%d %H:%M:%S')}' WHERE id={review_id}"
            try:
                if connection.is_connected():
                    cursor = connection.cursor()
                    cursor.execute(query)
                    connection.commit()
                    cursor.close()
                    bot.send_message(message.chat.id, "✅Ваш відгук успішно відредаговано!")
            finally:
                connection.close()
    else:
        bot.send_message(message.chat.id, "⚠️Ви надіслали порожнє повідомлення, введіть відгук:")
        bot.register_next_step_handler(message, handle_review)

def search(message, keywords=None, type=None):
    logger.info(f"Search triggered, keywords:{keywords}, type:{type}")
    user_id = message.from_user.id
    if message.location:
        location_string = f"{message.location.latitude},{message.location.longitude}"
        store_user_location(message.from_user.id, message.location.latitude, message.location.longitude)
        
    set_user_state(user_id, States.SEARCHING)
    
    chat_id = message.chat.id
    if redis_client.exists(f"{chat_id}_reviews_message"):
        message_id_reviews = redis_client.get(f"{chat_id}_reviews_message")

        try:
            bot.delete_message(chat_id=message.chat.id, message_id=message_id_reviews)
        except Exception as e:
            logger.exception(f"Error while deleting message: {e}")

        redis_client.delete(f"{chat_id}_reviews_message")

    if redis_client.exists(f"{chat_id}_places_message"):
        message_id_places = redis_client.get(f"{chat_id}_places_message")

        try:
            bot.delete_message(chat_id=message.chat.id, message_id=message_id_places)
        except Exception as e:
            logger.exception(f"Error while deleting message: {e}")

        redis_client.delete(f"{chat_id}_places_message")

    location = get_latest_position(user_id, 5)
    if location:
        latitude, longitude = location["latitude"], location["longitude"]
    if location and latitude and longitude:
        search_radius = redis_client.get(str(chat_id) + "_range")
        if(search_radius is None):
            search_radius = 300
            redis_client.set(str(chat_id) + "_range", search_radius)
        else:
            search_radius = int(search_radius)

        bot.send_message(chat_id, f"⏳Зачекайте трошки, збираю інформацію, ваш радіус пошуку - {search_radius}м", reply_markup=types.ReplyKeyboardRemove())
        try:
            if not type:
                logger.error("No type specified")
                type="cafe"

            logger.info(f"Search keywords: {keywords}")

            logger.info(f"Search location: ({latitude}, {longitude}). Radius: {search_radius}")
            places = get_places(float(latitude), float(longitude), search_radius, keywords, type=type)

            if not places:
                bot.send_message(message.chat.id, "🙄За вашим запитом нічого не знайдено.", reply_markup=start_keyboard_auth)
                logger.debug("No places found for the search query.")
                return

            redis_client.delete(f'{message.chat.id}_places')
            for dictionary in places:
                redis_client.rpush(f'{message.chat.id}_places', json.dumps(dictionary))

            first_five = places[:5]
            names = [elem["name"] for elem in first_five]
            response = "☕️ Топ заклади поруч з вами\n"
            for i in range(len(names)):
                response += f"{i+1}.{names[i]}\n"
                distance = int(places[i]["distance"])
                formatted_address = extract_address(places[i]["formatted_address"])
                response += f"🧭 {distance}м\n"
                response += f"📍 {formatted_address}\n"
            keyboard_places = types.InlineKeyboardMarkup()
            if len(places) > 5:
                keyboard_places.row(types.InlineKeyboardButton("➡️", callback_data=f"nextpage_{1}_{message.chat.id}_{latitude}_{longitude}"))
            number_buttons = []
            for i in range(len(first_five)):
                number_buttons.append(types.InlineKeyboardButton(f"{number_to_emoji(i+1)}", callback_data=f"sendplace_{latitude}_{longitude}_{first_five[i]['place_id']}"))
            keyboard_places.row(*number_buttons)
            sent_message_places = bot.send_message(message.chat.id, response, reply_markup=keyboard_places, parse_mode="")
            redis_client.set(f"sentmessageplaces_{message.chat.id}", sent_message_places.message_id)
        except Exception as e:
            bot.send_message(message.chat.id, "Виникла помилка, почніть заново", reply_markup=start_keyboard_auth)
            logger.error(f"Error : {e}")

    else:
        logger.warning(f"Location not found for chat ID: {message.chat.id}")
        bot.send_message(message.chat.id, "🌍Будь ласка, поділіться вашим місцезнаходженням для здійснення пошуку",
        reply_markup=types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True, selective=True).add(types.KeyboardButton(text="Надіслати розташування", request_location=True)))
        bot.register_next_step_handler(message, search, keywords, type)

if __name__ == '__main__':
    while True:
        try:
            bot.polling()
        except Exception as e:
            logger.critical(f"Bot crashed: {e}")
            time.sleep(2)