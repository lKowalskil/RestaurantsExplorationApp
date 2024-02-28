import requests
import os
import datetime
from telebot import TeleBot, types
import redis
import logging
from geopy.distance import geodesic
import urllib
from bs4 import BeautifulSoup
import re
from googletrans import Translator

logging.basicConfig(filename="logs.txt" ,format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

redis_client = redis.Redis()

translator = Translator()

API_KEY = os.environ.get("GOOGLE_API_KEY")

def generate_map_link(place_id):
    map_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
    return map_url

def get_places(latitude, longitude, search_radius, keywords):
    base_nearby_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    place_types = ["cafe", "restaurant"]

    nearby_params = {
        "location": f"{latitude},{longitude}",
        "radius": search_radius,
        "keywords": keywords,
        "type": "|".join(place_types),
        "key": API_KEY,
    }

    nearby_response = requests.get(base_nearby_url, params=nearby_params)

    if nearby_response.status_code != 200:
        print("Помилка запиту пошуку поблизу. Код відповіді:", nearby_response.status_code)
        return []

    else:
        nearby_data = nearby_response.json()

        if nearby_data['status'] == 'OK':
            places = []

            for place in nearby_data['results']:
                place_id = place['place_id']

                details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=opening_hours,formatted_address,rating,place_id,photos&key={API_KEY}"

                details_response = requests.get(details_url)

                user_location = (latitude, longitude)
                place_location = (place['geometry']['location']['lat'], place['geometry']['location']['lng'])
                distance = geodesic(user_location, place_location).meters 
                
                if details_response.status_code != 200:
                    print(f"Помилка отримання деталей для {place['name']}: Код відповіді:", details_response.status_code)
                    continue

                else:
                    details_data = details_response.json()
                    if details_data['status'] == 'OK':
                        result = details_data['result']
                        photo_url = None
                        if "photos" in result:
                            photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={result['photos'][1]['width']+ 1}&photo_reference={result['photos'][1]['photo_reference']}&key={API_KEY}"
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
                                "place_id" : result["place_id"],
                                "photo_url": photo_url
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
                                "place_id" : result["place_id"],
                                "photo_url": photo_url
                            }

                            places.append(place_data)

            return places

        else:
            print("Результатів пошуку поблизу не знайдено.")
            return []

BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TeleBot(BOT_TOKEN)

commands = [
    types.BotCommand("start", "Почати роботу з ботом"),
    types.BotCommand("search", "Знайти кафе або ресторан"),
    types.BotCommand("set_range", "Виставити максимальну відстань до закладу (250м-5000м)"),
    types.BotCommand("settings", "Змінити налаштування"),
]

bot.set_my_commands(commands)

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, 
                     """Вітаю! Цей бот допоможе вам знайти кафе та ресторани поблизу. 
                     \nДля пошуку введіть команду /search та через пробіл keywords.
                     \nНадішліть мені своє місцеположення, щоб я знав де шукати""")

@bot.message_handler(content_types=['location'])
def save_location(message):
    location_string = f"{message.location.latitude},{message.location.longitude}"
    redis_client.set(message.chat.id, location_string)
    bot.send_message(message.chat.id, "Запам'ятав")

@bot.message_handler(commands=['set_range'])
def set_range(message):
    args = message.text.split(' ')
    if len(args) > 2:
        bot.send_message(message.chat.id, f"Надто багато аргументів, спробуйте ще раз")
    elif len(args) < 2:
        bot.send_message(message.chat.id, f"Надто мало аргументів, спробуйте ще раз")
    else:
        try:
            range = int(args[1])
            if range < 250:
                bot.send_message(message.chat.id, "Відстань не може біть менше ніж 250м")
            elif range > 5000: 
                bot.send_message(message.chat.id, "Відстань не може бути більше ніж 5000м")
            else:
                redis_client.set(str(message.chat.id) + "_range", range)
                bot.send_message(message.chat.id, f"Запам'ятав, максимальна відстань - {range}")
        except ValueError:
            bot.send_message(message.chat.id, f"Щось пішло не так, введіть число")
        
def replace_weekdays(text):
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
    text = re.sub(pattern, ukrainian_weekday, text, flags=re.IGNORECASE)

  return text  

@bot.message_handler(commands=['search'])
def search(message):
    location_string = redis_client.get(message.chat.id)
    
    if location_string:
        args = message.text.split(' ')
        bot.send_message(message.chat.id, "Зачекайте трошки, збираю інформацію")
        if len(args) < 2:
            keywords = "кафе ресторан бар паб"

        keywords = ' '.join(args[1:])
        latitude, longitude = location_string.decode().split(',') 
        search_radius = int(redis_client.get(str(message.chat.id) + "_range"))

        places = get_places(latitude, longitude, search_radius, keywords)

        if not places:
            bot.send_message(message.chat.id, "За вашим запитом нічого не знайдено.")
            return

        for place in places:
            address = str(place['address'])
            translated_address = translator.translate(address, src='en', dest='uk').text
            response = f"Назва: {place['name']}\nАдреса: {translated_address}\nСтатус роботи: {'Відкрито' if place['open_now'] else 'Закрито'}\nВідстань: {int(place['distance'])} метрів\nРейтинг: {place['rating'] if place['rating'] is not None else 'Невідомо'}"

            if place['weekday_text']:
                response += "\n\nГрафік роботи:"
                for day_text in place['weekday_text']:
                    if "Closed" in day_text:
                        response += f"\n- {day_text}"
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
            if place["photo_url"] is not None:
                image_url = place["photo_url"]
                filename = place["place_id"] + "_photo.jpg"

                bot.send_photo(message.chat.id, caption=response, photo=image_url, reply_markup=types.InlineKeyboardMarkup(
                    [[types.InlineKeyboardButton(text="Відобразити на мапі", url=map_link)]]
                ))
            else:
                bot.send_message(message.chat.id, response, reply_markup=types.InlineKeyboardMarkup(
                    [[types.InlineKeyboardButton(text="Відобразити на мапі", url=map_link)]]
                ))
    else:
        bot.send_message(message.chat.id, "Я не знаю де ви знаходитесь, надішліть вашу геолокацію")
        
if __name__ == '__main__':
    bot.polling()