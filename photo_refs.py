import json
import os
import mysql.connector

photos_directory = "/home/koval/RestaurantsExplorationApp/photos"
jsons_directory = "/home/koval/RestaurantsExplorationApp/details_jsons"
jsons_paths = os.listdir(jsons_directory)
jsons_paths = [os.path.join(jsons_directory, item) for item in jsons_paths]

conn = mysql.connector.connect(
    host="localhost",
    user="phpmyadmin",
    password=os.environ.get("MYSQL_PASSWORD"),
    database="PlacesExploration"
)

def image_to_bytes(image_path):
    with open(image_path, 'rb') as image_file:
        image_bytes = image_file.read()
    return image_bytes

for path in jsons_paths:
    with open(path, 'r') as file:
        data = json.load(file)
        if data["status"] == "OK":
            place_id = data["result"]["place_id"]
            if "photos" in data["result"]:
                photos = data["result"]["photos"]
                for i in range(len(photos)):
                    photo_reference = photos[i]["photo_reference"]
                    photo_path_new = os.path.join(photos_directory, f"{place_id}_photos", f"{photo_reference}.jpg")
                    if os.path.isfile(photo_path_new):
                        image_bytes = image_to_bytes(photo_path_new)
                        cursor = conn.cursor()
                        query = """
                                INSERT INTO PlacePhotos (place_id, photo_data)
                                VALUES (%s, %s)
                            """
                        values = (place_id, image_bytes)
                        try:
                            cursor.execute(query, values)
                            conn.commit()
                            print("Data inserted successfully!")
                        except mysql.connector.Error as error:
                            print("Failed to insert data: {}".format(error))
