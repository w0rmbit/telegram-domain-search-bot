import psycopg2
from config import DATABASE_URL

def connect():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id SERIAL PRIMARY KEY,
                    file_id TEXT,
                    file_name TEXT,
                    file_size INTEGER,
                    upload_date TIMESTAMP DEFAULT NOW()
                );
            """)
            conn.commit()

def save_file(file_id, file_name, file_size):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO files (file_id, file_name, file_size)
                VALUES (%s, %s, %s);
            """, (file_id, file_name, file_size))
            conn.commit()

def get_all_files():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT file_id, file_name FROM files;")
            return cur.fetchall()
