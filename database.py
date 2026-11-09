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
                unit TEXT NOT NULL DEFAULT 'kg',
                is_deleted INTEGER NOT NULL DEFAULT 0
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

        # Table to track if seeding was already done once
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Add is_deleted column if it doesn't exist (migration for existing db)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(products)").fetchall()]
        if "is_deleted" not in cols:
            conn.execute("ALTER TABLE products ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0")

        # Seed sample products ONLY ONCE
        seeded = conn.execute("SELECT value FROM meta WHERE key = 'seeded'").fetchone()
        if not seeded:
            sample_products = [
                ("Rice", 60.0, 50.0, "kg"),
                ("Pappu", 120.0, 30.0, "kg"),
                ("Sugar", 45.0, 40.0, "kg"),
                ("Ravva", 40.0, 25.0, "kg"),
                ("Oil", 140.0, 20.0, "litre"),
                ("Atta", 55.0, 35.0, "kg")
            ]
            conn.executemany(
                "INSERT INTO products (name, price, stock, unit, is_deleted) VALUES (?, ?, ?, ?, 0)",
                sample_products
            )
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('seeded', 'true')")

        conn.commit()
        conn.close()
    except Exception as e:
        print("[DB INIT ERROR]", e)
