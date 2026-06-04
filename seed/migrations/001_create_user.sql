CREATE TABLE IF NOT EXISTS users(
id                SERIAL PRIMARY KEY,
username          VARCHAR(255) UNIQUE NOT NULL,
password_hash     VARCHAR(255) NOT NULL,
is_admin          BOOLEAN NOT NULL DEFAULT FALSE,
created_at        TIMESTAMP NOT NULL DEFAULT now()
);