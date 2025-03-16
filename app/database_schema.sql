-- SQLite Datenbankschema für Inventarsystem
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barcode TEXT UNIQUE NOT NULL,
    quantity INTEGER NOT NULL,
    expiration_date DATE,
    added_date DATE NOT NULL,
    category TEXT NOT NULL
);
