import argparse
import os
import psycopg2
from loguru import logger
from app.middleware.auth import hash_password

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/adv_rag")
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "seed", "migrations")


#demo users that get created when you run this script — useful for local testing
DEMO_USERS = [
    ("agent@demo.local", "agent123", False),
    ("admin@demo.local", "admin123", True),
]

#this fn finds all .sql files in the migrations folder and runs them in alphabetical order.
#this sets up the database schema (tables, indexes, etc).
def run_migrations(conn: psycopg2.extensions.connection) -> None:
    cur = conn.cursor()

    #sort the files so migrations always run in the right order (001, 002, 003...)
    files = sorted(
        [f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")]
    )

    for filename in files:
        path = os.path.join(MIGRATIONS_DIR, filename)

        with open(path) as f:
            sql = f.read()

        logger.info("Running migration: {}", filename)

        cur.execute(sql)

    conn.commit()
    cur.close()


#this fn inserts the demo users into the users table.
#it uses ON CONFLICT DO UPDATE so running this twice wont crash — it just updates.
def seed_users(conn: psycopg2.extensions.connection) -> None:
    cur = conn.cursor()

    for username, password, is_admin in DEMO_USERS:
        #hash the password before storing it in the db
        password_hash = hash_password(password)

        cur.execute(
            """
            INSERT INTO users (username, password_hash, is_admin)
            VALUES (%s, %s, %s)
            ON CONFLICT (username) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                is_admin = EXCLUDED.is_admin
            """,
            (username, password_hash, is_admin),
        )
        logger.info("Seeded user: {} (admin: {})", username, is_admin)

    conn.commit()
    cur.close()


#main entry point — connects to the db, runs all migrations, then seeds the demo users
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed DB (Lesson 0 - no doc ingestion)"
    )

    parser.parse_args()

    logger.info("Connecting to database...")

    conn = psycopg2.connect(DATABASE_URL)

    logger.info("Running migrations...")
    run_migrations(conn)

    logger.info("Seeding demo users...")
    seed_users(conn)

    conn.close()

    logger.info("DB seeding done.")
    logger.info(
        "Note: document ingestion is added in Lesson 1 (lesson-1-naive-rag)."
    )

if __name__ == "__main__":
    main()