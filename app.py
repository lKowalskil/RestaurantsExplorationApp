import requests
import os
import datetime
from telebot import TeleBot, types
import redis
import logging
from geopy.distance import geodesic
import re
from googletrans import Translator
import time

logging.basicConfig(filename="logs.txt", 
                    filemode="a", 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)

redis_client = redis.Redis()

translator = Translator()

API_KEY = os.environ.get("GOOGLE_API_KEY")

def generate_map_link(place_id):
    logger.debug(f"Generating map link for place ID: {place_id}")  
    map_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
    logger.debug(f"Generated map link: {map_url}") 
    return map_url

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


def get_places(latitude, longitude, search_radius, keywords, type):
    logger.info(f"Get places triggered {latitude}, {longitude}, {search_radius}, {keywords}, {type}")
    base_nearby_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    #place_types = ["restaurant"]
    type = translator.translate(type, src='uk', dest='en').text.lower()
    nearby_params = {
        "location": f"{latitude},{longitude}",
        "radius": search_radius,
        "keywords": keywords,
        "type": type,
        "key": API_KEY,
    }
    logger.debug(f"Nearby search parameters: {nearby_params}")
    nearby_response = requests.get(base_nearby_url, params=nearby_params)

    if nearby_response.status_code != 200:
        logger.error(f"Nearby search request failed. Response code: {nearby_response.status_code}")
        return []
    else:
        logger.debug("Nearby search request successful.")
        nearby_data = nearby_response.json()

        if nearby_data['status'] == 'OK':
            logger.info("Nearby search returned valid results.")
            places = []

            for place in nearby_data['results']:
                place_id = place['place_id']
                logger.debug(f"Fetching details for place ID: {place_id}")
                
                details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=opening_hours,formatted_address,rating,place_id,photos,price_level,website,serves_beer,serves_breakfast,serves_brunch,serves_dinner,serves_lunch,serves_vegetarian_food,serves_wine&key={API_KEY}"
                details_response = requests.get(details_url)
                user_location = (latitude, longitude)
                place_location = (place['geometry']['location']['lat'], place['geometry']['location']['lng'])
                distance = geodesic(user_location, place_location).meters 
                
                if details_response.status_code != 200:
                    logger.warning(f"Details request for {place['name']} failed. Response code: {details_response.status_code}")
                    continue

                else:
                    details_data = details_response.json()
                    if details_data['status'] == 'OK':
                        logger.debug("Place details fetched successfully.")
                        result = details_data['result']
                        photo_url = None
                        if "photos" in result:
                            photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={result['photos'][0]['width']+ 1}&photo_reference={result['photos'][0]['photo_reference']}&key={API_KEY}"
                        if 'opening_hours' in result:
                            opening_hours = result['opening_hours']
                            open_now = opening_hours.get('open_now', False)
                            weekday_text = opening_hours.get('weekday_text', [])

                            place_data = {
                                "name": place['name'],
                                "address": result.get('formatted_address'),
                                "open_now": open_now,
                                "weekday_text": weekday_text,
                                "distance": distance,
                                "rating": result['rating'] if 'rating' in result else None,
                                "price_level": result["price_level"] if "price_level" in result else None,
                                "place_id" : result["place_id"],
                                "photo_url": photo_url,
                                "website": result["website"] if "website" in result else None,
                                "serves_beer": result["serves_beer"] if "serves_beer" in result else None,
                                "serves_breakfast": result["serves_breakfast"] if "serves_breakfast" in result else None,
                                "serves_brunch": result["serves_brunch"] if "serves_brunch" in result else None,
                                "serves_dinner": result["serves_dinner"] if "serves_dinner" in result else None,
                                "serves_lunch": result["serves_lunch"] if "serves_lunch" in result else None,
                                "serves_vegetarian_food": result["serves_vegetarian_food"] if "serves_vegetarian_food" in result else None,
                                "serves_wine": result["serves_wine"] if "serves_wine" in result else None
                            }

                            places.append(place_data)

                        else:
                            place_data = {
                                "name": place['name'],
                                "address": result.get('formatted_address'),
                                "open_now": None,
                                "weekday_text": None,
                                "distance": distance,
                                "rating": result['rating'] if 'rating' in result else None,
                                "price_level": result["price_level"] if "price_level" in result else None,
                                "place_id" : result["place_id"],
                                "photo_url": photo_url,
                                "website": result["website"] if "website" in result else None,
                                "serves_beer": result["serves_beer"] if "serves_beer" in result else None,
                                "serves_breakfast": result["serves_breakfast"] if "serves_breakfast" in result else None,
                                "serves_brunch": result["serves_brunch"] if "serves_brunch" in result else None,
                                "serves_dinner": result["serves_dinner"] if "serves_dinner" in result else None,
                                "serves_lunch": result["serves_lunch"] if "serves_lunch" in result else None,
                                "serves_vegetarian_food": result["serves_vegetarian_food"] if "serves_vegetarian_food" in result else None,
                                "serves_wine": result["serves_wine"] if "serves_wine" in result else None
                            }

                            places.append(place_data)
            logger.info(f"Found {len(places)} places.")  
            return places

        else:
            logger.warning(f"Nearby search response status: {nearby_data['status']}. No places found.")
            return []

BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TeleBot(BOT_TOKEN)
logger.info("Bot is started")

start_keyboard_list = ["Пошук закладів", "Налаштування"]
start_keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
for button in start_keyboard_list:
    start_keyboard.add(types.KeyboardButton(text=button))

location_keyboard_button_list = ["Змінити радіус пошуку", "Фільтри"]
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
    elif message.text == "Фільтри":
        
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
        search(message, type=message.text)

def search(message, keywords=None, type=None):
    logger.info(f"Search triggered, keywords:{keywords}, type:{type}")
    if message.location:
        location_string = f"{message.location.latitude},{message.location.longitude}"
        redis_client.set(message.chat.id, location_string)
        
    location_string = redis_client.get(message.chat.id)
    if location_string:
        bot.send_message(message.chat.id, "Зачекайте трошки, збираю інформацію", reply_markup=types.ReplyKeyboardRemove())
        try:
            """ if not keywords:
                try:
                    keywords = str(redis_client.get(str(message.chat.id)+"_default_keywords"))
                    translated_address = translator.translate(address, src='uk', dest='en').text
                except Exception as e:
                    logger.error(f"Error while retrieving default_keywords {e}")"""
            if not type:
                logger.error("No type specified")
                type="cafe"
            
            logger.info(f"Search keywords: {keywords}")
            
            latitude, longitude = location_string.decode().split(',') 
            search_radius = int(redis_client.get(str(message.chat.id) + "_range"))

            logger.info(f"Search location: ({latitude}, {longitude}). Radius: {search_radius}")
            places = get_places(latitude, longitude, search_radius, keywords, type=type)

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
                            f"Відстань: {int(place['distance'])} метрів"
                            f"\nРейтинг: {place['rating'] if place['rating'] is not None else 'Невідомо'}"
                            + (f"\nРівень Ціни: {place['price_level']}" if place['price_level'] is not None else '') + 
                            f"\nПодають пиво: {'Так' if place.get('serves_beer', False) else 'Ні' if 'serves_beer' in place else 'невідомо'}"
                            f"\nПодають вино: {'Так' if place.get('serves_wine', False) else 'Ні' if 'serves_wine' in place else 'невідомо'}"
                            f"\nПодають сніданок: {'Так' if place.get('serves_breakfast', False) else 'Ні' if 'serves_breakfast' in place else 'невідомо'}"
                            f"\nПодають бранч: {'Так' if place.get('serves_brunch', False) else 'Ні' if 'serves_brunch' in place else 'невідомо'}"
                            f"\nПодають обід: {'Так' if place.get('serves_lunch', False) else 'Ні' if 'serves_lunch' in place else 'невідомо'}"
                            f"\nПодають вечерю:{'Так' if place.get('serves_dinner', False) else 'Ні' if 'serves_dinner' in place else 'невідомо'}"
                            f"\nПодають вегетаріанську їжу: {'Так' if place.get('serves_vegetarian_food', False) else 'Ні' if 'serves_vegetarian_food' in place else 'невідомо'}"
                            )
                if place['weekday_text']:
                    response += "\n\nГрафік роботи:"
                    for day_text in place['weekday_text']:
                        if "Closed" in day_text:
                            response += f"\n- {day_text}"
                        elif "Open 24 hours" in day_text:
                            response += f"\n- {day_text.replace('Open 24 hours', 'Відчинено 24 години')}" 
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

                            response += f"\n- " + f"{day_text.split(':')[0]}: {time1_24hour} - {time2_24hour}"
                else:
                    response += "\nГрафік роботи невідомий :("
                response = replace_weekdays(response).replace("Closed", "Зачинено")
                map_link = generate_map_link(place["place_id"])
                inline_keyboard = types.InlineKeyboardMarkup()
                inline_keyboard.add(types.InlineKeyboardButton(text="Відобразити на мапі", url=map_link))
                if "website" in place:
                    if place["website"] is not None:
                        inline_keyboard.add(types.InlineKeyboardButton(text="Веб-сайт", url=place["website"]))

                if place["photo_url"] is not None:
                    image_url = place["photo_url"]
                    filename = place["place_id"] + "_photo.jpg"
                    logger.debug(f"Sending details for place: {place['name']}")
                    bot.send_photo(message.chat.id, caption=response, photo=image_url, reply_markup=inline_keyboard)
                else:
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