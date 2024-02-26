import requests
import os
import datetime
from telebot import TeleBot, types
import redis
import logging
from geopy.distance import geodesic
import urllib

logger = logging.getLogger(__name__)
redis_client = redis.Redis()
logger.setLevel(logging.DEBUG)

API_KEY = os.environ.get("GOOGLE_API_KEY")

def generate_map_link(place):
    place_name = urllib.parse.quote_plus(place['name'])
    place_address = urllib.parse.quote_plus(place['address'])
    map_url = f"https://www.google.com/maps/search/?api=1&query={place_name},{place_address}"
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

                details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=opening_hours,formatted_address&key={API_KEY}"

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

                        if 'opening_hours' in result:
                            opening_hours = result['opening_hours']
                            open_now = opening_hours.get('open_now', False)
                            weekday_text = opening_hours.get('weekday_text', [])

                            place_data = {
                                "name": place['name'],
                                "address": result.get('formatted_address'),
                                "open_now": open_now,
                                "weekday_text": weekday_text,
                                "distance": distance 
                            }

                            places.append(place_data)

                        else:
                            place_data = {
                                "name": place['name'],
                                "address": result.get('formatted_address'),
                                "open_now": None,
                                "weekday_text": None,
                                "distance": distance 
                            }

                            places.append(place_data)

            return places

        else:
            print("Результатів пошуку поблизу не знайдено.")
            return []

BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TeleBot(BOT_TOKEN)

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

@bot.message_handler(commands=['search'])
def search(message):
    location_string = redis_client.get(message.chat.id)
    
    if location_string:
        args = message.text.split(' ')
        if len(args) < 2:
            bot.send_message(message.chat.id, "Введіть команду /search та через пробіл keywords.")
            return

        keywords = ' '.join(args[1:])
        latitude, longitude = location_string.decode().split(',') 
        search_radius = 250

        places = get_places(latitude, longitude, search_radius, keywords)

        if not places:
            bot.send_message(message.chat.id, "За вашим запитом нічого не знайдено.")
            return

        for place in places:
            response = f"Назва: {place['name']}\nАдреса: {place['address']}\nСтатус роботи: {'Відкрито' if place['open_now'] else 'Закрито'}\nВідстань: {int(place['distance'])} метрів"

            if place['weekday_text']:
                response += "\n\nГрафік роботи:"
                print(place["weekday_text"])
                for day_text in place['weekday_text']:
                    response += f"\n- {day_text}"
            map_link = generate_map_link(place)
            bot.send_message(message.chat.id, response, reply_markup=types.InlineKeyboardMarkup(
                [[types.InlineKeyboardButton(text="Відобразити на карті", url=map_link)]]
            ))
    else:
        bot.send_message(message.chat.id, "Я не знаю де ви знаходитесь, надішліть вашу геолокацію")
        
if __name__ == '__main__':
    bot.polling()