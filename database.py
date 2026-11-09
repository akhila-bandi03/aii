import os
import sqlite3

if os.environ.get("VERCEL"):
    DATABASE = "/tmp/dukaansaathi.db"
else:
    DATABASE = "dukaansaathi.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    try:
        conn = get_db_connection()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                stock REAL NOT NULL DEFAULT 0,
                unit TEXT NOT NULL DEFAULT 'kg'
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                customer_name TEXT,
                quantity REAL NOT NULL,
                unit_price REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL,
                sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)

        # Add initial sample products if table is empty
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count == 0:
            sample_products = [
                ("Rice", 60.0, 50.0, "kg"),
                ("Pappu", 120.0, 30.0, "kg"),
                ("Sugar", 45.0, 40.0, "kg"),
                ("Ravva", 40.0, 25.0, "kg"),
                ("Oil", 140.0, 20.0, "litre"),
                ("Atta", 55.0, 35.0, "kg")
            ]
            conn.executemany(
                "INSERT INTO products (name, price, stock, unit) VALUES (?, ?, ?, ?)",
                sample_products
            )

        conn.commit()
        conn.close()
    except Exception as e:
        print("[DB INIT ERROR]", e)
