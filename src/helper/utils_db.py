from dotenv import load_dotenv
import os
import psycopg2


# Load environment variables from the .env file
load_dotenv()

"""
Store settings for Kafka, database, and API keys here. 
This way, you can easily access configurations across different scripts without hardcoding them.
"""


# Connect to the PostgreSQL database
def connect_to_db():
    try:
        connection = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
        return connection
    except Exception as e:
        print("Error connecting to database:", e)
        raise

