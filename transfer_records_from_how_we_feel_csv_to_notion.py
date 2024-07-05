import pandas as pd
import math
import notion_client
from dotenv import load_dotenv
import os
from anthropic import Anthropic
from datetime import datetime

load_dotenv()

# Load environment variables
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
CSV_FILE_PATH = "../HowWeFeelEmotions5Jul2024.csv"

# Read CSV file
file_path = CSV_FILE_PATH
df = pd.read_csv(file_path)

# Display the dataframe structure
print("Dataframe Columns: ", df.columns)
print("First few rows of the dataframe:")
print(df.head())

# Convert dataframe to list of dictionaries
records = df.to_dict(orient='records')

print("First few records parsed from CSV:")
for record in records[:5]:
    print(record)

# Initialize Notion client
notion = notion_client.Client(auth=NOTION_API_KEY)
database_id = NOTION_DATABASE_ID

# Initialize Anthropic client
anthropic_client = Anthropic(api_key=ANTHROPIC_KEY)


# Function to fetch the database schema from Notion
def fetch_notion_database_schema(database_id):
    database = notion.databases.retrieve(database_id=database_id)
    return database['properties']


# Fetch database schema
notion_schema = fetch_notion_database_schema(database_id)

# Display the types of the columns
print("\nColumn types in the Notion database:")
for name, prop in notion_schema.items():
    print(f"{name}: {prop['type']}")


# Function to round sleep hours
def round_sleep_hours(hours):
    return round(hours, 2)


# Function to convert Fahrenheit to Celsius
def fahrenheit_to_celsius(fahrenheit):
    if isinstance(fahrenheit, float):
        return (fahrenheit - 32) * 5.0 / 9.0
    else:
        return ''


# Function to convert date to ISO 8601 format
def convert_to_iso8601(date_str):
    try:
        return datetime.strptime(date_str, "%Y %a %b %d %I:%M %p").isoformat()
    except ValueError:
        return None


# Function to generate a name using Anthropic API
def generate_name(record):
    prompt = f'''
Your goal is to create a short name for an entry in the Mood diary.
You'll be provided data about the mood diary entry and you need to output only the name of that diary entry.
Pay special attention to the Notes field.
Include no other info except for the title.
Only spaces and letters: Russian or English. No full stops. Treat it as a header.
Data: {record}
    '''
    response = anthropic_client.messages.create(
        max_tokens=1000,
        model='claude-3-haiku-20240307',
        messages=[
            {
                "role": "user",
                "content": f"{prompt}"
            }
        ]
    )
    return response.content[0].text.strip()


# Function to add a record to Notion
def add_record_to_notion(record, name):
    # Prepare the Notion record
    print(f"Record before transform: {record}")

    notion_record = {
        "Title": { "title": [{ "text": { "content": record['Name'] } }] }
    }
    # Add fields to the record if they are present in the CSV
    if record['Date']:
        notion_record["Date and time"] = { "date": { "start": record['Date'] } }
    if record['Places']:
        notion_record["Places"] = {
            "multi_select": [{ "name": place } for place in record['Places'].split(';') if place.strip()]
        }
    if record['People']:
        notion_record["People"] = {
            "multi_select": [{ "name": person } for person in record['People'].split(';') if person.strip()]
        }
    if record['Notes']:
        notion_record["Notes"] = { "rich_text": [{ "text": { "content": record['Notes'] } }] }
    if record['Mood']:
        notion_record["Emotions"] = {
            "multi_select": [{ "name": mood } for mood in record['Mood'].split(';') if mood.strip()]
        }
    if record['Sleep'] is not None:
        notion_record["Sleep hours"] = { "number": record['Sleep'] }
    if record['Meditation'] is not None:
        notion_record["Meditation"] = { "number": record['Meditation'] }
    if record['Events'] and record['Events'] is not None:
        notion_record["Events"] = {
            "multi_select": [{ "name": event } for event in record['Events'].split(';') if event.strip()]
        }
    if record['Exercise'] is not None:
        notion_record["Exercise"] = { "number": record['Exercise'] }
    if record['Steps'] is not None:
        notion_record["Steps"] = { "number": record['Steps'] }
    if record['Temperature'] is not None:
        notion_record["Temperature"] = { "number": record['Temperature'] }
    if record['Weather']:
        notion_record["Weather"] = { "select": { "name": record['Weather'] } }

    # Debug print statement
    print("Adding record to Notion:", notion_record)

    notion.pages.create(
        parent={ "database_id": database_id },
        properties=notion_record
    )


# Process and add records to Notion
for i, record in enumerate(records):
    if i >= 1000:
        break

    # Extract and transform data
    date = convert_to_iso8601(record['Date'])
    mood = record['Mood']
    places = record.get('Tags (Places)', '')  # Extract Places from CSV
    people = record.get('Tags (People)', '')  # Extract People from CSV
    events = record.get('Tags (Events)', '')  # Extract Events from CSV
    exercise = float(record['Exercise']) if pd.notna(record['Exercise']) else None
    sleep = round_sleep_hours(float(record['Sleep'])) if not math.isnan(float(record['Sleep'])) else None
    steps = round(float(record['Steps']),2) if not math.isnan(float(record['Steps'])) else None
    meditation = float(record['Meditation']) if not math.isnan(float(record['Meditation'])) else None
    weather = record['Weather'] if pd.notna(record['Weather']) else None
    notes = record['Notes'] if pd.notna(record['Notes']) else None
    temperature = round(fahrenheit_to_celsius(float(record['Temperature (F)'])),
                        2) if 'Temperature (F)' in record and not math.isnan(float(record['Temperature (F)'])) else None

    # Generate name using Anthropic API
    name = generate_name(record)

    # Prepare the record for Notion
    record_for_notion = {
        "Name": name,
        "Date": date,
        "Mood": mood,
        "Places": places,
        "People": people,
        "Events": events,
        "Exercise": exercise,
        "Sleep": sleep,
        "Steps": steps,
        "Meditation": meditation,
        "Weather": weather,
        "Notes": notes,
        "Temperature": temperature
    }

    add_record_to_notion(record_for_notion, name)
