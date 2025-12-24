#!/usr/bin/env bash
set -e

echo "Waiting for database..."

# Wait for database using Python, explicitly executed in the Poetry virtual environment
poetry run python3 << END
import sys
import time
import psycopg2
from psycopg2 import OperationalError
import os

max_retries = 30
retry = 0
sleep_time = 2

while retry < max_retries:
    try:
        conn = psycopg2.connect(
            dbname=os.environ['POSTGRES_DB'],
            user=os.environ['POSTGRES_USER'],
            password=os.environ['POSTGRES_PASSWORD'],
            host=os.environ['POSTGRES_HOST'],
            port=os.environ['POSTGRES_PORT']
        )
        conn.close()
        print("Database is ready!")
        sys.exit(0)
    except OperationalError:
        retry += 1
        print(f"Database unavailable, waiting... ({retry}/{max_retries})")
        time.sleep(sleep_time)

# If the loop finishes without exiting 0, it means it failed to connect.
print("Could not connect to database after maximum retries!")
sys.exit(1)
END

RUN_MANAGE_PY='poetry run python -m core.manage'

echo 'Collecting static files...'
$RUN_MANAGE_PY collectstatic --no-input

echo 'Running migrations...'
$RUN_MANAGE_PY migrate --no-input

echo 'Starting gunicorn...'
exec poetry run gunicorn core.project.wsgi:application --bind 0.0.0.0:8000
