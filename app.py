import requests
import os

# Your Google Maps Places API key
API_KEY = os.environ.get("GOOGLE_API_KEY")

# Поточне місцезнаходження користувача (вам потрібно буде реалізувати його отримання)
user_latitude = 50.4050316  # Приклад широти (Київ)
user_longitude = 30.6666277  # Приклад довготи

# Радіус пошуку в метрах
search_radius = 250  # 5 кілометрів

# Ключові слова пошуку
keywords = "кафе ресторан"

# Базова URL-адреса API для пошуку поблизу
base_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
place_types = ["cafe", "restaurant"]
# Створення URL-адреси запиту API
params = {
    "location": f"{user_latitude},{user_longitude}",
    "radius": search_radius,
    "keywords": keywords,
    "type": "|".join(place_types),
    "key": API_KEY,
    "fields": "opening_hours"
}

# Здійснення запиту API
response = requests.get(base_url, params=params)

# Обробка помилок, якщо запит не вдасться
if response.status_code != 200:
    print("Виникла помилка. Код відповіді:", response.status_code)
    # Додайте більш детальну обробку помилок, якщо це необхідно
else: 
    data = response.json()
    print(data)
    if data['status'] == 'OK':
        # Обробка списку місць поблизу
        for place in data['results']:
            name = place['name']
            address = place['vicinity']

            # Перевірка доступності годин роботи
            if 'opening_hours' in place:
                opening_hours = place['opening_hours']

                open_now = opening_hours.get('open_now', False)
                status = "Відкрито зараз" if open_now else "Закрито"

            else:
                status = "Статус роботи недоступний"

            print(f"Назва: {name}")
            print(f"Адреса: {address}")
            print(f"Статус: {status}")
            print("------")

    else:
        print("Результатів не знайдено.")