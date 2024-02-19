import requests
import os
import datetime

API_KEY = os.environ.get("GOOGLE_API_KEY")

user_latitude = 50.4050316 
user_longitude = 30.6666277 

search_radius = 250 

keywords = "кафе ресторан"

base_nearby_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
base_details_url = "https://maps.googleapis.com/maps/api/place/details/json"
place_types = ["cafe", "restaurant"]

nearby_params = {
    "location": f"{user_latitude},{user_longitude}",
    "radius": search_radius,
    "keywords": keywords,
    "type": "|".join(place_types),
    "key": API_KEY,
}

nearby_response = requests.get(base_nearby_url, params=nearby_params)

if nearby_response.status_code != 200:
    print("Помилка запиту пошуку поблизу. Код відповіді:", nearby_response.status_code)

else:
    nearby_data = nearby_response.json()

    if nearby_data['status'] == 'OK':
        for place in nearby_data['results']:
            name = place['name']
            address = place['vicinity']
            place_id = place['place_id']

            details_url = f"{base_details_url}?place_id={place_id}&fields=opening_hours,formatted_address&key={API_KEY}"

            details_response = requests.get(details_url)

            if details_response.status_code != 200:
                print(f"Помилка отримання деталей для {name}: Код відповіді:", details_response.status_code)

            else:
                details_data = details_response.json()

                if details_data['status'] == 'OK':
                    result = details_data['result']

                    if 'opening_hours' in result:
                        opening_hours = result['opening_hours']
                        open_now = opening_hours.get('open_now', False)
                        weekday_text = opening_hours.get('weekday_text', [])

                        print(f"Назва: {name}")
                        print(f"Адреса: {result.get('formatted_address')}") 
                        print(f"Статус роботи: {'Відкрито' if open_now else 'Закрито'}")

                        for day_text in weekday_text:
                            print(day_text)

                    else:
                        print(f"Назва: {name}")
                        print(f"Адреса: {result.get('formatted_address')}")
                        print(f"Інформація про години роботи недоступна")

                    print("--------") 

                else:
                    print(f"Помилка отримання деталей для {name}")

    else:
        print("Результатів пошуку поблизу не знайдено.")
