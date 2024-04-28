import os
import datetime
from telebot import TeleBot, types
import redis
import logging
from geopy.distance import geodesic
import mysql.connector
import re
from math import radians, sin, cos, sqrt, atan2
import time
import json

logging.basicConfig(filename="logs.txt", 
                    filemode="a", 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)

redis_client = redis.Redis()


db_connection = mysql.connector.connect(
    host="localhost",
    user="phpmyadmin",
    password=os.environ.get("MYSQL_PASSWORD"),
    database="PlacesExploration"
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
            query = f"SELECT name, types FROM Places WHERE place_id = '{place_id}'"
            cursor = db_connection.cursor()
            cursor.execute(query)
            place = cursor.fetchall()[0]
            name = place[0]
            if type in place[1]:
                places.append({"place_id": place_id, "name": name})
    return places
            
def get_place_reviews(place_id):
    query = f"SELECT reviews FROM Places WHERE place_id = '{place_id}'"      
    cursor = db_connection.cursor()
    cursor.execute(query)
    reviews_str = cursor.fetchall()[0][0]
    reviews = json.loads(reviews_str)
    return reviews
    
def get_detailed_place_info(place_id, latitude, longitude, user_id):
    query = f"SELECT place_id, latitude, longitude, name, formatted_address, weekday_text, rating, price_level, url, website, serves_beer, serves_breakfast, serves_brunch, serves_dinner, serves_lunch, serves_vegetarian_food, serves_wine, opening_hours, photos, types, dine_in, delivery, reservable, reviews, international_phone_number FROM Places WHERE place_id = '{place_id}'"
    cursor = db_connection.cursor()
    cursor.execute(query)
    place = cursor.fetchall()[0]
    query = f"SELECT place_id FROM Favourites WHERE tg_user_id={user_id}"
    cursor = db_connection.cursor()
    cursor.execute(query)
    favourite_places_db = cursor.fetchall()
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
    
    address = str(place_data['address'])
    response = ''
    response += f"Назва: {place_data['name']}" + "⭐️\n" if place_id in favourite_places else "\n"
    response += f"Адреса: {address}\n"
    response += f"Номер телефону: {place_data['international_phone_number'].replace(' ', '')}" + "\n" if place_data['international_phone_number'] is not None else ''
    response += f"Статус роботи: {'Відкрито' if place_data['open_now'] else 'Закрито'}\n"
    response += f"Відстань: {int(place_data['distance'])} метрів\n"
    response += f"Рейтинг: {place_data['rating'] if place_data['rating'] is not None else 'Невідомо'}"
    response += f"\nРівень Ціни: {place_data['price_level']}" if place_data['price_level'] is not None else ''
    response += '\nЄ місця всередині' if place_data.get('dine_in', False) else ''
    response += '\nЄ доставка' if place_data.get('delivery', False) else ''
    response += '\nМожливе бронювання' if place_data.get('reservable', False) else ''
    response += "\n\nГрафік роботи:"
    if place_data["weekday_text"]:
        if "Графік роботи невідомий :(" in place_data["weekday_text"]:
            response += " невідомо :("
        else:
            response += place_data['weekday_text']
    response = replace_weekdays(response).replace("Closed", "Зачинено")
    map_link = generate_map_link(place_data["place_id"])
    website = place_data["website"]
    return (response, map_link, website)

def get_detailed_place_info_without_distance(place_id, user_id):
    query = f"SELECT place_id, latitude, longitude, name, formatted_address, weekday_text, rating, price_level, url, website, serves_beer, serves_breakfast, serves_brunch, serves_dinner, serves_lunch, serves_vegetarian_food, serves_wine, opening_hours, photos, types, dine_in, delivery, reservable, reviews, international_phone_number FROM Places WHERE place_id = '{place_id}'"
    cursor = db_connection.cursor()
    cursor.execute(query)
    place = cursor.fetchall()[0]
    query = f"SELECT place_id FROM Favourites WHERE tg_user_id={user_id}"
    cursor = db_connection.cursor()
    cursor.execute(query)
    favourite_places_db = cursor.fetchall()
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
    response += f"Назва: {place_data['name']}" + "⭐️\n" if place_id in favourite_places else "\n"
    response += f"Адреса: {address}\n"
    response += f"Номер телефону: {place_data['international_phone_number'].replace(' ', '')}" + "\n" if place_data['international_phone_number'] is not None else ''
    response += f"Статус роботи: {'Відкрито' if place_data['open_now'] else 'Закрито'}\n"
    response += f"Рейтинг: {place_data['rating'] if place_data['rating'] is not None else 'Невідомо'}"
    response += f"\nРівень Ціни: {place_data['price_level']}" if place_data['price_level'] is not None else ''
    response += '\nЄ місця всередині' if place_data.get('dine_in', False) else ''
    response += '\nЄ доставка' if place_data.get('delivery', False) else ''
    response += '\nМожливе бронювання' if place_data.get('reservable', False) else ''
    response += "\n\nГрафік роботи:"
    if place_data["weekday_text"]:
        if "Графік роботи невідомий :(" in place_data["weekday_text"]:
            response += " невідомо :("
        else:
            response += place_data['weekday_text']
    response = replace_weekdays(response).replace("Closed", "Зачинено")
    map_link = generate_map_link(place_data["place_id"])
    website = place_data["website"]
    return (response, map_link, website)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TeleBot(BOT_TOKEN)
logger.info("Bot is started")

start_keyboard_list_non_auth = ["Пошук закладів", "Налаштування"]
start_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in start_keyboard_list_non_auth:
    start_keyboard.add(types.KeyboardButton(text=button))

start_keyboard_list_auth = ["Пошук закладів", "Налаштування", "Редагувати відгуки", "Обрані заклади"]
start_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in start_keyboard_list_auth:
    start_keyboard.add(types.KeyboardButton(text=button))
    
settings_keyboard_button_list = ["Змінити радіус пошуку"]
settings_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in settings_keyboard_button_list:
    settings_keyboard.add(types.KeyboardButton(text=button))

location_keyboard_buttons_list = ["Пошук закладів", "Налаштування"]
location_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in location_keyboard_buttons_list:
    location_keyboard.add(types.KeyboardButton(text=button))

ranges_list = ["250", "500", "1000", "1500", "2000", "3000", "4000", "5000", "Повернутися"]
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

search_option_keyboard_buttons_list = ["Кафе", "Ресторан", "Бар"]
search_option_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in search_option_keyboard_buttons_list:
    search_option_keyboard.add(types.KeyboardButton(text=button))


@bot.message_handler(commands=['start'])
def start(message):
    redis_client.delete(message.chat.id) 
    redis_client.set(str(message.chat.id) + "_range", 300)
    bot.send_message(message.chat.id, "Будь-ласка, поділіться вашим номером телефону для авторизації:", reply_markup=types.ReplyKeyboardMarkup(
                        one_time_keyboard=True, 
                        resize_keyboard=True, 
                        selective=True
                    ).add(types.KeyboardButton(text="Поділитися номером телефону", request_contact=True)))

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    phone_number = message.contact.phone_number
    user_id = message.from_user.id
    
    cursor = db_connection.cursor()
    cursor.execute("SELECT * FROM Users WHERE tg_user_id = %s", (user_id,))
    existing_user = cursor.fetchone()
    
    db_connection.commit()
    if existing_user:
        pass
    else:
        sql = """INSERT INTO Users (tg_user_id, phone_number) VALUES (%s, %s)"""
        values = (user_id, phone_number)
        cursor.execute(sql, values)
        db_connection.commit()
    
    bot.send_message(message.chat.id, "Авторизація успішна!")
    bot.send_message(message.chat.id, 
                        """Вітаю! Цей бот допоможе вам знайти кафе та ресторани поблизу. \n
                        Оберіть дію:""",
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
    elif message.text == "Обрані заклади":
        user_id = message.from_user.id
        query = f"SELECT place_id FROM Favourites WHERE tg_user_id = {user_id}"
        cursor = db_connection.cursor()
        cursor.execute(query)
        place_ids = cursor.fetchall()
        
        places = []
        for place in place_ids:
            places.append({"place_id": place[0]})
        
        if not places:
            bot.send_message(message.chat.id, "За вашим запитом нічого не знайдено.", reply_markup=start_keyboard)
            logger.debug("No places found for the search query.")
            return
        
        redis_client.delete(f'{message.chat.id}_places')
        for dictionary in places:
            redis_client.rpush(f'{message.chat.id}_places', json.dumps(dictionary))
        
            
        first_place = redis_client.lindex(f'{message.chat.id}_places', 0)
        if first_place:
            first_place = json.loads(first_place)
            print(first_place)
            response_places, map_link, website = get_detailed_place_info_without_distance(first_place["place_id"], user_id)
            keyboard_places = types.InlineKeyboardMarkup(row_width=2)
            if map_link:
                keyboard_places.add(types.InlineKeyboardButton(text="Відобразити на мапі", url=map_link))
            if website is not None:
                keyboard_places.add(types.InlineKeyboardButton(text="Вебсайт", url=website))
            keyboard_places.add( 
                types.InlineKeyboardButton("Додати до обраних", callback_data=f"favourites_{first_place['place_id']}"), 
            )
            keyboard_places.add( 
                types.InlineKeyboardButton("Наступний", callback_data=f"placefavourites_{1}"), 
            )
            redis_client.delete(f"{message.chat.id}_places_message")
            sent_message_places = bot.send_message(message.chat.id, response_places, reply_markup=keyboard_places)
            redis_client.set(f"{message.chat.id}_places_message", sent_message_places.message_id)
            
    elif message.text == "Пошук закладів":
        bot.send_message(message.chat.id, "Оберіть тип закладу для пошуку:", reply_markup=search_option_keyboard)
        bot.register_next_step_handler(message, handle_keywords_for_search)
    elif message.text == "Редагувати відгуки":
        user_id = message.from_user.id
        query = f"SELECT id, place_id, name, score, review, date FROM UsersReviews WHERE tg_user_id = {user_id}"
        cursor = db_connection.cursor()
        cursor.execute(query)
        user_reviews = cursor.fetchall()
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
                        types.InlineKeyboardButton("Наступний", callback_data=f"reviewedit_{1}"), 
                    )
            inline_keyboard.add( 
                    types.InlineKeyboardButton("Редагувати", callback_data=f"editreview_{review[0]}"),
                )
            response_first_review = get_review_response(user_reviews_list[0]["name"], user_reviews_list[0]["score"], user_reviews_list[0]["date"], user_reviews_list[0]["review"])
            sent_message_reviews = bot.send_message(message.chat.id, response_first_review, reply_markup=inline_keyboard)
            redis_client.set(f"{message.chat.id}_message_reviews_edit", sent_message_reviews.message_id)
        else:
            bot.send_message(message.chat.id, "Ви ще не залишали відгуків", start_keyboard_list_auth)
    elif message.text == "Змінити радіус пошуку":
        bot.send_message(message.chat.id, "Оберіть бажаний радіус пошуку", reply_markup=set_range_keyboard)
    elif message.text == "Повернутися":
        bot.send_message(message.chat.id, "Оберіть дію:", reply_markup=start_keyboard)
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

def get_review_response(name, score, date_or_str, review):
    if isinstance(date_or_str, datetime.datetime):
        date = date_or_str.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(date_or_str, str):
        date = date_or_str
    else:
        logger.error("Invalid type in get_review_response")

    response_review = f"Автор: {name}\nОцінка: {score}\nДата: {date}\nВідгук: {review}"
    return response_review

@bot.callback_query_handler(func=lambda call: True)
def handle_navigation(call):
    data = call.data.split("_")
    if data[0] == "place":
        prefix, index, latitude, longitude, type = data
        index = int(index)
    elif data[0] == "review":
        prefix, index = data
        index = int(index)
    elif data[0] == "favourites":
        prefix = data[0]
        place_id = '_'.join(data[1:])
    elif data[0] == "placefavourites":
        prefix, index = data
    elif data[0] == "sendreviews":
        prefix = data[0]
        place_id = '_'.join(data[1:])
    elif data[0] == "addreview":
        prefix = data[0]
        place_id = '_'.join(data[1:])
    elif data[0] == "reviewedit":
        prefix, index = data
        index = int(index)
    elif data[0] == "editreview":
        prefix, review_id = data


    user_id = call.from_user.id
    try:
        if prefix == "reviewedit":
            chat_id = str(call.message.chat.id)
            message_id = redis_client.get(f"{chat_id}_message_reviews_edit")
            len_reviews = redis_client.llen(f'{chat_id}_reviews_edit')
            review_data = json.loads(redis_client.lindex(f'{chat_id}_reviews_edit', index))
            
            inline_keyboard = types.InlineKeyboardMarkup(row_width=2)
            if index > 0 and index < len_reviews - 1:
                inline_keyboard.add(
                    types.InlineKeyboardButton("Попередній", callback_data=f"reviewedit_{index - 1}"),
                    types.InlineKeyboardButton("Наступний", callback_data=f"reviewedit_{index + 1}"),
                )
            elif index == 0 and index < len_reviews - 1:
                inline_keyboard.add( 
                    types.InlineKeyboardButton("Наступний", callback_data=f"reviewedit_{index + 1}"),
                )
            elif index > 0 and index >= len_reviews - 1:
                inline_keyboard.add( 
                    types.InlineKeyboardButton("Попередній", callback_data=f"reviewedit_{index - 1}"),
                )
            inline_keyboard.add( 
                    types.InlineKeyboardButton("Редагувати", callback_data=f"editreview_{review_data['id']}"),
                )
            response_reviews = get_review_response(review_data["name"], review_data["score"], review_data["date"], review_data["review"])
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response_reviews, reply_markup=inline_keyboard)
            except Exception as e: 
                logger.error(f"Error editing message: {e}")
                bot.answer_callback_query(call.id, "Сталася помилка. Спробуйте ще раз") 
            
        elif prefix == "place":
            chat_id = str(call.message.chat.id)
            message_id = redis_client.get(f"{chat_id}_places_message")
            if message_id is None:
                bot.answer_callback_query(call.id, "Сталася помилка. Спробуйте ще раз") 
                return
            message_id = message_id.decode() 
            
            place_data = redis_client.lindex(f'{chat_id}_places', index)
            len_places = redis_client.llen(f'{chat_id}_places')
            
            if place_data is None:
                bot.answer_callback_query(call.id, "No more results.")
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
                inline_keyboard.add(types.InlineKeyboardButton(text="Відобразити на мапі", url=map_link))
            if website is not None:
                inline_keyboard.add(types.InlineKeyboardButton(text="Вебсайт", url=website))
            inline_keyboard.add( 
                    types.InlineKeyboardButton("Додати до обраних", callback_data=f"favourites_{place_data['place_id']}"),
                )
            inline_keyboard.add( 
                    types.InlineKeyboardButton("Переглянути відгуки", callback_data=f"sendreviews_{place_data['place_id']}"),
                )
            inline_keyboard.add( 
                    types.InlineKeyboardButton("Додати відгук", callback_data=f"addreview_{place_data['place_id']}"),
                )
            
            if index > 0 and index < len_places - 1:
                inline_keyboard.add(
                    types.InlineKeyboardButton("Попередній", callback_data=f"place_{index - 1}_{latitude}_{longitude}_{type}"),
                    types.InlineKeyboardButton("Наступний", callback_data=f"place_{index + 1}_{latitude}_{longitude}_{type}"),
                )
            elif index == 0 and index < len_places - 1:
                inline_keyboard.add( 
                    types.InlineKeyboardButton("Наступний", callback_data=f"place_{index + 1}_{latitude}_{longitude}_{type}"),
                )
            elif index > 0 and index >= len_places - 1:
                inline_keyboard.add( 
                    types.InlineKeyboardButton("Попередній", callback_data=f"place_{index - 1}_{latitude}_{longitude}_{type}"),
                )

            try:
                bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response, reply_markup=inline_keyboard, parse_mode="html")
            except Exception as e: 
                logger.error(f"Error editing message: {e}")
                bot.answer_callback_query(call.id, "Сталася помилка. Спробуйте ще раз")
        elif prefix == "review":
            chat_id = str(call.message.chat.id)
            message_id = redis_client.get(f"{chat_id}_reviews_message")
            if message_id is None:
                bot.answer_callback_query(call.id, "Сталася помилка. Спробуйте ще раз")
                return
            message_id = message_id.decode() 
            review_data = redis_client.lindex(f'{chat_id}_reviews', index)
            len_reviews = redis_client.llen(f'{chat_id}_reviews')
            
            if review_data is None:
                bot.answer_callback_query(call.id, "Більше нема :)")
                return
            
            review_data = json.loads(review_data)
            
            response_reviews = get_review_response(reviews[0]["author_name"], str(reviews[0]["rating"]), reviews[0]["relative_time_description"], reviews[0]["text"])
            
            inline_keyboard = types.InlineKeyboardMarkup(row_width=2)
            if index > 0 and index < len_reviews - 1:
                inline_keyboard.add(
                    types.InlineKeyboardButton("Попередній", callback_data=f"review_{index - 1}"), 
                    types.InlineKeyboardButton("Наступний", callback_data=f"review_{index + 1}"), 
                )
            elif index == 0 and index < len_reviews - 1:
                inline_keyboard.add( 
                    types.InlineKeyboardButton("Наступний", callback_data=f"review_{index + 1}"), 
                )
            elif index > 0 and index >= len_reviews - 1:
                inline_keyboard.add( 
                    types.InlineKeyboardButton("Попередній", callback_data=f"review_{index - 1}"), 
                )
            
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response_reviews, reply_markup=inline_keyboard)
            except Exception as e: 
                logger.error(f"Error editing message: {e}")
                bot.answer_callback_query(call.id, "Сталася помилка. Спробуйте ще раз") 
        elif prefix == "favourites":
            print(place_id, ":", user_id)
            query_insert = f"INSERT IGNORE INTO Favourites (place_id, tg_user_id) VALUES ('{place_id}', '{user_id}')"
            try:
                cursor = db_connection.cursor()
                cursor.execute(query_insert)
                db_connection.commit()
                print("Successfully added to favourites.")
            except Exception as e:
                print(f"An error occurred while adding to favourites: {e}")
                db_connection.rollback()
        elif prefix == "placefavourites":
            chat_id = str(call.message.chat.id)
            message_id = redis_client.get(f"{chat_id}_places_message")
            if message_id is None:
                bot.answer_callback_query(call.id, "Сталася помилка. Спробуйте ще раз") 
                return
            message_id = message_id.decode() 
            
            place_data = redis_client.lindex(f'{chat_id}_places', index)
            len_places = redis_client.llen(f'{chat_id}_places')
            
            if place_data is None:
                bot.answer_callback_query(call.id, "No more results.")
                return

            place_data = json.loads(place_data)
                
            response, map_link, website = get_detailed_place_info(place_data["place_id"], latitude, longitude) 

            inline_keyboard = types.InlineKeyboardMarkup(row_width=2)
            if map_link:
                inline_keyboard.add(types.InlineKeyboardButton(text="Відобразити на мапі", url=map_link))
            if website is not None:
                inline_keyboard.add(types.InlineKeyboardButton(text="Вебсайт", url=website))
            inline_keyboard.add( 
                    types.InlineKeyboardButton("Додати до обраних", callback_data=f"favourites_{place_data['place_id']}"), 
                )
            inline_keyboard.add( 
                    types.InlineKeyboardButton("Переглянути відгуки", callback_data=f"sendreviews_{place_data['place_id']}"),
                )
            inline_keyboard.add( 
                    types.InlineKeyboardButton("Додати відгук", callback_data=f"addreview_{place_data['place_id']}"),
                )
            if index > 0 and index < len_places - 1:
                inline_keyboard.add(
                    types.InlineKeyboardButton("Попередній", callback_data=f"placefavourites_{index - 1}_{type}"), 
                    types.InlineKeyboardButton("Наступний", callback_data=f"placefavourites_{index + 1}_{type}"), 
                )
            elif index == 0 and index < len_places - 1:
                inline_keyboard.add( 
                    types.InlineKeyboardButton("Наступний", callback_data=f"placefavourites_{index + 1}_{type}"), 
                )
            elif index > 0 and index >= len_places - 1:
                inline_keyboard.add( 
                    types.InlineKeyboardButton("Попередній", callback_data=f"placefavourites_{index - 1}_{type}"), 
                )

            try:
                bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response, reply_markup=inline_keyboard, parse_mode="html")
            except Exception as e: 
                logger.error(f"Error editing message: {e}")
                bot.answer_callback_query(call.id, "Сталася помилка. Спробуйте ще раз") 
        elif prefix == "sendreviews":
            reviews = get_place_reviews(place_id)
            chat_id = str(call.message.chat.id)
            redis_client.delete(f'{chat_id}_reviews')

            response_reviews = get_review_response(reviews[0]["author_name"], str(reviews[0]["rating"]), reviews[0]["relative_time_description"], reviews[0]["text"])
            
            keyboard_reviews = types.InlineKeyboardMarkup(row_width=2)
            keyboard_reviews.add( 
                types.InlineKeyboardButton("Наступний", callback_data=f"review_{1}"), 
            )
            
            if len(reviews) != 0:
                for dictionary in reviews:
                    redis_client.rpush(f'{chat_id}_reviews', json.dumps(dictionary))
            else:
                keyboard_reviews = None
                
            redis_client.delete(f"{chat_id}_reviews_message")
            sent_message_reviews = bot.send_message(chat_id, response_reviews, reply_markup=keyboard_reviews)
            redis_client.set(f"{chat_id}_reviews_message", sent_message_reviews.message_id)
        elif prefix == "addreview":
            chat_id = str(call.message.chat.id)
            bot.send_message(chat_id, "Введіть ваше ім'я:")
            bot.register_next_step_handler(call.message, handle_name, place_id=place_id)
        elif prefix == "editreview":
            chat_id = str(call.message.chat.id)
            bot.send_message(chat_id, "Введіть ваше ім'я:")
            bot.register_next_step_handler(call.message, handle_name, review_id=review_id)
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        bot.answer_callback_query(call.id, "Сталася помилка. Спробуйте ще раз") 

def handle_name(message, place_id=None, review_id=None):
    if message.text:
        redis_client.set(f"review_{place_id}_name_{message.chat.id}", message.text)
        bot.send_message(message.chat.id, "Введіть оцінку від 1 до 5:")
        bot.register_next_step_handler(message, handle_score, place_id=place_id, review_id=review_id)
    else:
        bot.send_message(message.chat.id, "Ви надіслали порожнє повідомлення, введіть ім'я:")
        bot.register_next_step_handler(message, handle_name, place_id=place_id, review_id=review_id)

def handle_score(message, place_id=None, review_id=None):
    if message.text:
        try:
            score = int(message.text)
        except Exception as e:
            logger.exception(f"Error while getting score for review: {e}")
            bot.send_message(message.chat.id, "Треба ввести оцінку від 1 до 5:")
            bot.register_next_step_handler(message, handle_score, place_id=place_id, review_id=review_id)
            return
        if score < 1 or score > 5:
            bot.send_message(message.chat.id, "Треба ввести оцінку від 1 до 5:")
            bot.register_next_step_handler(message, handle_score, place_id=place_id, review_id=review_id)
            return
        redis_client.set(f"review_{place_id}_score_{message.chat.id}", message.text)
        bot.send_message(message.chat.id, "Введіть відгук:")
        bot.register_next_step_handler(message, handle_review, place_id=place_id, review_id=review_id)
    else:
        bot.send_message(message.chat.id, "Ви надіслали порожнє повідомлення, введіть оцінку:")
        bot.register_next_step_handler(message, handle_score, place_id=place_id, review_id=review_id)
        
def handle_review(message, place_id=None, review_id=None):
    if message.text:
        name = redis_client.get(f"review_{place_id}_name_{message.chat.id}")
        name = name.decode('utf-8')
        score = int(redis_client.get(f"review_{place_id}_score_{message.chat.id}"))
        review = message.text
        date = datetime.datetime.now()
        if place_id:
            query = f"INSERT INTO UsersReviews (place_id, name, tg_user_id, score, review, date) VALUES ('{place_id}', '{name}', {message.from_user.id}, {score}, '{review}', '{date.strftime('%Y-%m-%d %H:%M:%S')}')"
            cursor = db_connection.cursor()
            cursor.execute(query)
            db_connection.commit()
            bot.send_message(message.chat.id, "Ваш відгук успішно додано!")
        elif review_id:
            query = f"UPDATE UsersReviews SET name='{name}', tg_user_id={message.from_user.id}, score={score}, review='{review}', date='{date.strftime('%Y-%m-%d %H:%M:%S')}' WHERE id={review_id}"
            cursor = db_connection.cursor()
            cursor.execute(query)
            db_connection.commit()
            bot.send_message(message.chat.id, "Ваш відгук успішно відредаговано!")
            

    else:
        bot.send_message(message.chat.id, "Ви надіслали порожнє повідомлення, введіть відгук:")
        bot.register_next_step_handler(message, handle_review)
        
def search(message, keywords=None, type=None):
    logger.info(f"Search triggered, keywords:{keywords}, type:{type}")
    user_id = message.from_user.id
    if message.location:
        location_string = f"{message.location.latitude},{message.location.longitude}"
        redis_client.set(message.chat.id, location_string)
    
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
        
    location_string = redis_client.get(chat_id)
    if location_string:
        bot.send_message(chat_id, "Зачекайте трошки, збираю інформацію", reply_markup=types.ReplyKeyboardRemove())
        try:
            if not type:
                logger.error("No type specified")
                type="cafe"
            
            logger.info(f"Search keywords: {keywords}")
            
            latitude, longitude = location_string.decode().split(',') 
            search_radius = int(redis_client.get(str(chat_id) + "_range"))

            logger.info(f"Search location: ({latitude}, {longitude}). Radius: {search_radius}")
            places = get_places(float(latitude), float(longitude), search_radius, keywords, type=type)

            if not places:
                bot.send_message(message.chat.id, "За вашим запитом нічого не знайдено.", reply_markup=start_keyboard)
                logger.debug("No places found for the search query.")
                return
            
            redis_client.delete(f'{message.chat.id}_places')
            for dictionary in places:
                redis_client.rpush(f'{message.chat.id}_places', json.dumps(dictionary))
            
            first_place = redis_client.lindex(f'{message.chat.id}_places', 0)
            if first_place:
                first_place = json.loads(first_place)
                response_places, map_link, website = get_detailed_place_info(first_place["place_id"], latitude, longitude, user_id)
                keyboard_places = types.InlineKeyboardMarkup(row_width=2)
                if map_link:
                    keyboard_places.add(types.InlineKeyboardButton(text="Відобразити на мапі", url=map_link))
                if website is not None:
                    keyboard_places.add(types.InlineKeyboardButton(text="Вебсайт", url=website))
                keyboard_places.add( 
                    types.InlineKeyboardButton("Додати до обраних", callback_data=f"favourites_{first_place['place_id']}"), 
                )
                keyboard_places.add( 
                    types.InlineKeyboardButton("Переглянути відгуки", callback_data=f"sendreviews_{first_place['place_id']}"),
                )
                keyboard_places.add( 
                    types.InlineKeyboardButton("Додати відгук", callback_data=f"addreview_{first_place['place_id']}"),
                )
                keyboard_places.add( 
                    types.InlineKeyboardButton("Наступний", callback_data=f"place_{1}_{latitude}_{longitude}_{type}"), 
                )
                redis_client.delete(f"{message.chat.id}_places_message")
                sent_message_places = bot.send_message(message.chat.id, response_places, reply_markup=keyboard_places)
                redis_client.set(f"{message.chat.id}_places_message", sent_message_places.message_id)
            
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
