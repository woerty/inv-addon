from flask import Flask, request, jsonify
import sqlite3
import requests
from flask_cors import CORS
from datetime import date, datetime
import os
import openai
import time
import threading
from pydantic import BaseModel
from typing import List



app = Flask(__name__)
CORS(app, origins=['http://localhost:3000'])

DATABASE = 'inventory.db'

# OpenAI API Key aus Umgebungsvariablen holen
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Chatverlauf in SQLite speichern (optional)
def initialize_chat_table():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT,
            content TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

initialize_chat_table()

# Hilfsfunktion: Chatverlauf speichern
def save_message(role, content):
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO chat_history (role, content, timestamp)
        VALUES (?, ?, ?)
    ''', (role, content, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# Hilfsfunktion: Chatverlauf abrufen
def get_chat_history():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT role, content FROM chat_history ORDER BY id ASC')
    history = [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
    conn.close()
    return history

@app.route('/assistant/chat', methods=['POST'])
def chat_with_assistant():
    data = request.json
    user_message = data.get("message", "").strip()
    use_ingredients = data.get("useIngredients", False)  # Schalterstatus

    if not user_message:
        return jsonify({"error": "Leere Nachricht kann nicht verarbeitet werden."}), 400

    # Chatverlauf abrufen
    chat_history = get_chat_history()

    # Prüfen, ob dies die erste Nachricht in der Konversation ist
    first_message = len(chat_history) == 0

    # Falls gewünscht, Zutaten nur bei der ersten Nachricht hinzufügen
    if use_ingredients and first_message:
        conn = get_db_connection()
        cursor = conn.cursor()
        inventory = cursor.execute('SELECT name FROM inventory WHERE quantity > 0').fetchall()
        cursor.close()
        conn.close()

        if inventory:
            ingredients = ", ".join([item["name"] for item in inventory])
            chat_history.append({"role": "system", "content": f"Der Nutzer hat folgende Zutaten im Haushalt: {ingredients}."})

    # Aktuelle Benutzernachricht hinzufügen
    chat_history.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "Du bist ein hilfreicher Kochassistent."}] + chat_history,
            max_tokens=5000
        )

        ai_message = response.choices[0].message.content

        # KI-Antwort speichern
        save_message("user", user_message)
        save_message("assistant", ai_message)

        return jsonify({"response": ai_message})

    except Exception as e:
        return jsonify({"error": f"Fehler bei der OpenAI API: {str(e)}"}), 500

@app.route('/assistant/clear-chat', methods=['POST'])
def clear_chat():
    """Löscht den gesamten Chatverlauf"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_history")  # Löscht alle Nachrichten
    conn.commit()
    conn.close()
    return jsonify({"message": "Chatverlauf wurde gelöscht."}), 200


# Initialize database with WAL mode
def initialize_database():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")  # Enable WAL mode
    cursor.execute("PRAGMA busy_timeout = 5000;")  # Set timeout to avoid immediate locks
    conn.commit()
    conn.close()

initialize_database()  # Run once at startup

# Helper function to establish a database connection
def get_db_connection():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Ensure results are dict-like
    conn.execute("PRAGMA busy_timeout = 5000;")  # Set busy timeout for transactions
    return conn

# Function to log inventory actions asynchronously
def log_inventory_action(barcode, action):
    threading.Thread(target=_log_inventory_action, args=(barcode, action)).start()

def _log_inventory_action(barcode, action):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO inventory_log (barcode, action, timestamp)
            VALUES (?, ?, ?)
        ''', (barcode, action, datetime.now().isoformat()))
        conn.commit()
    except sqlite3.OperationalError as e:
        print(f"Fehler beim Logging: {e}")
    finally:
        cursor.close()
        conn.close()

# Endpoint: Get inventory
@app.route('/inventory', methods=['GET'])
def get_inventory():
    conn = get_db_connection()
    cursor = conn.cursor()
    inventory = cursor.execute('SELECT * FROM inventory').fetchall()
    result = [dict(row) for row in inventory]
    cursor.close()
    conn.close()
    return jsonify(result)

# Endpoint: Get storage locations
@app.route('/storage-locations', methods=['GET'])
def get_storage_locations():
    conn = get_db_connection()
    cursor = conn.cursor()
    locations = cursor.execute('SELECT * FROM storage_locations').fetchall()
    result = [dict(row) for row in locations]
    cursor.close()
    conn.close()
    return jsonify(result)

# Endpoint: Add new storage location
@app.route('/storage-locations', methods=['POST'])
def add_storage_location():
    data = request.json
    location_name = data.get('location_name')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if location exists
    existing = cursor.execute('SELECT * FROM storage_locations WHERE location_name = ?', (location_name,)).fetchone()
    if not existing:
        cursor.execute('INSERT INTO storage_locations (location_name) VALUES (?)', (location_name,))
        conn.commit()
    
    cursor.close()
    conn.close()
    return jsonify({'message': f'Lagerplatz "{location_name}" gespeichert.'}), 201

# 🔹 Pydantic-Modell für strukturierten Output
class Recipe(BaseModel):
    name: str
    short_description: str
    ingredients: List[str]
    instructions: str

@app.route('/assistant/recipe-image', methods=['POST'])
def generate_recipe_image():
    data = request.json
    recipe_name = data.get("name", "").strip()
    generate_image = data.get("generate_image", True)  # Standard: Bild wird generiert

    if not recipe_name:
        return jsonify({"error": "Kein Rezeptname angegeben."}), 400

    if not generate_image:
        return jsonify({"image_url": None})  # Kein Bild generieren

    try:
        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=f"Ein realistisches Bild von '{recipe_name}', ein leckeres Gericht. Hochwertige Food-Fotografie, ästhetisch angerichtet.",
            n=1,
            size="1024x1024"
        )

        image_url = response.data[0].url
        return jsonify({"image_url": image_url})

    except Exception as e:
        return jsonify({"error": f"Fehler bei der Bildgenerierung: {str(e)}"}), 500


@app.route('/assistant/recipe-suggestions', methods=['GET'])
def get_recipe_suggestions():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    
    # Zutaten aus der Datenbank holen
    inventory = cursor.execute('SELECT name FROM inventory WHERE quantity > 0').fetchall()
    cursor.close()
    conn.close()
    
    if not inventory:
        return jsonify({"error": "Keine Lebensmittel im Inventar gefunden."}), 400

    ingredients = ", ".join([item[0] for item in inventory])

    # OpenAI API mit strict structured output
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Du bist ein Kochassistent."},
            {"role": "user", "content": f"Ich habe folgende Zutaten: {ingredients}. Bitte erstelle eine Liste von 5 Rezepten mit diesen Zutaten. Beachte: Die Ausgabe muss exakt dem JSON-Schema entsprechen."}
        ],
        response_format={"type":"json_object"},  # Erzwingt strukturierten Output
        max_tokens=5000
    )

    # JSON aus OpenAI Antwort extrahieren
    try:
        recipes = response.choices[0].message.content
        return jsonify({"recipes": recipes})  # OpenAI gibt eine JSON-Formatierte Antwort zurück
    except Exception as e:
        return jsonify({"error": f"Fehler bei der OpenAI API: {str(e)}"}), 500
# Endpoint: Add item by barcode
@app.route('/inventory/barcode', methods=['POST'])
def add_item_by_barcode():
    data = request.json
    barcode = data.get('barcode')
    storage_location = data.get('storage_location', 'Unbekannt')

    # Fetch product details from OpenFoodFacts
    openfoodfacts_url = f'https://world.openfoodfacts.org/api/v0/product/{barcode}.json'
    response = requests.get(openfoodfacts_url)
    product_data = response.json()

    if product_data['status'] == 1:
        name = product_data['product'].get('product_name', 'Unbekanntes Produkt')
        category = product_data['product'].get('categories', 'Unbekannt')
    else:
        return jsonify({'message': 'Produkt nicht gefunden'}), 404

    conn = get_db_connection()
    cursor = conn.cursor()

    existing_item = cursor.execute('SELECT * FROM inventory WHERE barcode = ?', (barcode,)).fetchone()

    if existing_item:
        cursor.execute('UPDATE inventory SET quantity = quantity + 1 WHERE barcode = ?', (barcode,))
        message = f'Produkt "{name}" existierte bereits. Menge um 1 erhöht.'
    else:
        cursor.execute('''
            INSERT INTO inventory (barcode, name, quantity, expiration_date, added_date, category, storage_location)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            barcode, name, 1, '1900-01-01', date.today().isoformat(), category, storage_location
        ))
        message = f'Artikel "{name}" hinzugefügt!'

    log_inventory_action(barcode, "Hinzufügen")
    
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'message': message}), 201

# Endpoint: Update item quantity
@app.route('/inventory/<barcode>', methods=['PUT'])
def update_item_quantity(barcode):
    data = request.json
    new_quantity = data.get('quantity')

    if new_quantity is None or not isinstance(new_quantity, int) or new_quantity < 0:
        return jsonify({'message': 'Ungültige Menge angegeben'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    existing_item = cursor.execute('SELECT * FROM inventory WHERE barcode = ?', (barcode,)).fetchone()

    if not existing_item:
        cursor.close()
        conn.close()
        return jsonify({'message': f'Kein Artikel mit Barcode {barcode} gefunden'}), 404

    if new_quantity == 0:
        cursor.execute('DELETE FROM inventory WHERE barcode = ?', (barcode,))
        log_inventory_action(barcode, "Löschen")
        message = f'Artikel mit Barcode {barcode} wurde gelöscht.'
    else:
        cursor.execute('UPDATE inventory SET quantity = ? WHERE barcode = ?', (new_quantity, barcode))
        log_inventory_action(barcode, "Mengenänderung")
        message = f'Artikel mit Barcode {barcode} wurde auf {new_quantity} gesetzt.'

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'message': message}), 200

# Endpoint: Artikel per Barcode um 1 verringern
@app.route('/inventory/remove', methods=['POST'])
def remove_item_by_barcode():
    data = request.json
    barcode = data.get('barcode')

    if not barcode:
        return jsonify({'error': 'Kein Barcode angegeben'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    existing_item = cursor.execute('SELECT quantity FROM inventory WHERE barcode = ?', (barcode,)).fetchone()

    if not existing_item:
        cursor.close()
        conn.close()
        return jsonify({'error': f'Kein Artikel mit Barcode {barcode} gefunden'}), 404

    quantity = existing_item['quantity']

    if quantity > 1:
        cursor.execute('UPDATE inventory SET quantity = quantity - 1 WHERE barcode = ?', (barcode,))
        message = f'Produkt mit Barcode {barcode} um 1 reduziert.'
    else:
        cursor.execute('DELETE FROM inventory WHERE barcode = ?', (barcode,))
        message = f'Produkt mit Barcode {barcode} wurde entfernt.'

    log_inventory_action(barcode, "Entfernen")

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'message': message}), 200



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
