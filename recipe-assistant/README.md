# Recipe Assistant Add-on für Home Assistant

![Recipe Assistant](https://img.shields.io/badge/Recipe%20Assistant-v1.0-blue)

## 📌 Überblick
**Recipe Assistant** ist ein **Home Assistant Add-on**, das eine OpenAI-basierte **Rezept- und Chat-Funktion** bietet.  
Das Add-on enthält:
- 📝 **Kochvorschläge basierend auf deinem Inventar**
- 💬 **Chat-Assistent für individuelle Fragen**
- 🖼 **Generierung von Rezeptbildern (optional)**
- 🔗 **Direkte Integration in Home Assistant mit Webinterface**

---

## 🚀 Installation

### 1️⃣ **Home Assistant Add-on Store**
1. **Gehe zu `Einstellungen` → `Add-ons` → `Add-on Store`**
2. **Klicke auf die drei Punkte (`⋮`) oben rechts → `Repository hinzufügen`**
3. **Gib diese URL ein:**
   ```
   https://github.com/woerty/inv-addon
   ```
4. **Nach ein paar Sekunden sollte das Add-on erscheinen**
5. **Installiere und starte das Add-on**

### 2️⃣ **Sidebar aktivieren**
- **Aktiviere `Zeige in der Sidebar`**, um das Webinterface direkt zu öffnen.

---

## 🛠 Konfiguration
Dieses Add-on benötigt keine spezielle Konfiguration.  
Es läuft direkt nach der Installation.  
Falls du OpenAI nutzen möchtest, stelle sicher, dass du einen **API-Key** hast.

- **Speicherort der Datenbank:** `/data/inventory.db`
- **Port des Backends:** `5000`
- **Port des Frontends:** `8080`

Falls du Bilder generieren möchtest, kannst du diese Option im Frontend aktivieren oder deaktivieren.

---

## 📂 Daten & Backup

### 🔍 **Wo wird die Datenbank gespeichert?**
Deine **Rezept-Datenbank (`inventory.db`)** wird in einem **persistenten Home Assistant Verzeichnis** gespeichert:
```
/data/inventory.db
```

### 📤 **Datenbank exportieren**
Falls du deine Daten sichern möchtest:
```sh
sqlite3 /data/inventory.db -header -csv "SELECT * FROM inventory;" > /data/inventory_export.csv
```

### 📥 **Datenbank importieren**
Falls du eine Backup-Datenbank wiederherstellen möchtest:
```sh
sqlite3 /data/inventory.db < /data/backup.sql
```

---

## 🚀 Nutzung

1️⃣ **Rezeptvorschläge abrufen**
- Öffne das Add-on in Home Assistant
- Klicke auf "Rezeptvorschläge abrufen"
- Wähle ein Rezept aus der Liste

2️⃣ **Bilder für Rezepte generieren**
- Aktiviere oder deaktiviere den **"Bilder generieren"**-Schalter
- Falls aktiviert, wird ein passendes Rezeptbild erstellt

3️⃣ **Chat-Assistent nutzen**
- Stelle Fragen zur Rezept-Zubereitung oder Ernährung
- Der Assistent kann direkt auf deine Zutaten zugreifen

---

## 🔧 Fehlerbehebung

### ❌ **Add-on erscheint nicht im Store**
Falls das Add-on nicht im Home Assistant Store auftaucht:
1. **Gehe zu `Einstellungen` → `Add-ons` → `Add-on Store`**
2. **Klicke auf "Repository hinzufügen" und gib die URL ein**
   ```
   https://github.com/woerty/inv-addon
   ```
3. **Falls das nicht hilft, starte Home Assistant neu:**
   ```sh
   ha supervisor restart
   ```

### ❌ **Kein Zugriff auf die Datenbank**
Falls die Datenbank nicht erreichbar ist:
- **Prüfe, ob die Datei existiert:**
  ```sh
  ls -l /data/inventory.db
  ```
- **Falls nicht, erstelle eine neue leere Datenbank:**
  ```sh
  sqlite3 /data/inventory.db "CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, quantity INTEGER);"
  ```

---

## 🏆 Mitwirkende
- **[@woerty](https://github.com/woerty)** – Entwickler

Falls du Vorschläge hast oder mitarbeiten möchtest, erstelle einfach ein Issue oder einen Pull Request!

---

## 📜 Lizenz
Dieses Projekt ist unter der **MIT-Lizenz** lizenziert.

