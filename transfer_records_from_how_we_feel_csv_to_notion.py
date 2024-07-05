import pandas as pd
import math
import notion_client
from dotenv import load_dotenv
import os
from anthropic import Anthropic
from datetime import datetime, timezone

load_dotenv()

# Load environment variables
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
CSV_FILE_PATH = os.getenv("CSV_FILE_PATH")

# Initialize clients
notion = notion_client.Client(auth=NOTION_API_KEY)
anthropic_client = Anthropic(api_key=ANTHROPIC_KEY)


def read_csv(file_path):
    return pd.read_csv(file_path)


def convert_dataframe_to_records(df):
    return df.to_dict(orient='records')


def fetch_notion_database_schema(notion_client, database_id):
    database = notion_client.databases.retrieve(database_id=database_id)
    return database['properties']


def round_sleep_hours(hours):
    return round(hours, 2)


def fahrenheit_to_celsius(fahrenheit):
    if isinstance(fahrenheit, float):
        return (fahrenheit - 32) * 5.0 / 9.0
    return None


def convert_to_iso8601(date_str):
    try:
        return datetime.strptime(date_str, "%Y %a %b %d %I:%M %p").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def generate_name(anthropic_client, record):
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


def fetch_all_notion_records(notion_client, database_id):
    results = []
    next_cursor = None

    while True:
        response = notion_client.databases.query(
            **{
                "database_id": database_id,
                "page_size": 100,
                "start_cursor": next_cursor,
            }
        )
        results.extend(response['results'])
        next_cursor = response.get('next_cursor')
        if not next_cursor:
            break

    return results


def extract_unique_dates_from_notion_records(notion_records):
    notion_dates = set()
    for record in notion_records:
        date_property = record['properties'].get('Date and time', {})
        date = date_property.get('date', {}).get('start')
        if date:
            standardized_date = datetime.fromisoformat(date).replace(tzinfo=timezone.utc).isoformat()
            notion_dates.add(standardized_date)
    return notion_dates


def add_record_to_notion(notion_client, database_id, record):
    notion_record = {
        "Title": {"title": [{"text": {"content": record['Name']}}]}
    }
    if record['Date']:
        notion_record["Date and time"] = {"date": {"start": record['Date']}}
    if isinstance(record['Places'], str):
        notion_record["Places"] = {
            "multi_select": [{"name": place} for place in record['Places'].split(';') if place.strip()]
        }
    if isinstance(record['People'], str):
        notion_record["People"] = {
            "multi_select": [{"name": person} for person in record['People'].split(';') if person.strip()]
        }
    if isinstance(record['Events'], str):
        notion_record["Events"] = {
            "multi_select": [{"name": event} for event in record['Events'].split(';') if event.strip()]
        }
    if isinstance(record['Notes'], str):
        notion_record["Notes"] = {"rich_text": [{"text": {"content": record['Notes']}}]}
    if isinstance(record['Mood'], str):
        notion_record["Emotions"] = {
            "multi_select": [{"name": mood} for mood in record['Mood'].split(';') if mood.strip()]
        }
    if record['Sleep'] is not None:
        notion_record["Sleep hours"] = {"number": record['Sleep']}
    if record['Meditation'] is not None:
        notion_record["Meditation"] = {"number": record['Meditation']}
    if record['Exercise'] is not None:
        notion_record["Exercise"] = {"number": record['Exercise']}
    if record['Steps'] is not None:
        notion_record["Steps"] = {"number": record['Steps']}
    if record['Temperature'] is not None:
        notion_record["Temperature"] = {"number": record['Temperature']}
    if isinstance(record['Weather'], str):
        notion_record["Weather"] = {"select": {"name": record['Weather']}}

    notion_client.pages.create(
        parent={"database_id": database_id},
        properties=notion_record
    )


def main():
    df = read_csv(CSV_FILE_PATH)
    records = convert_dataframe_to_records(df)
    notion_schema = fetch_notion_database_schema(notion, NOTION_DATABASE_ID)
    notion_records = fetch_all_notion_records(notion, NOTION_DATABASE_ID)
    notion_dates = extract_unique_dates_from_notion_records(notion_records)

    for i, record in enumerate(records):
        if i >= 1000:
            break

        date = convert_to_iso8601(record['Date'])
        if date in notion_dates:
            print(f"Date {date} is already in Notion database, skipping...")
            continue

        mood = record['Mood']
        places = record.get('Tags (Places)', None)
        people = record.get('Tags (People)', None)
        events = record.get('Tags (Events)', None)
        exercise = float(record['Exercise']) if pd.notna(record['Exercise']) else None
        sleep = round_sleep_hours(float(record['Sleep'])) if not math.isnan(float(record['Sleep'])) else None
        steps = round(float(record['Steps']), 2) if not math.isnan(float(record['Steps'])) else None
        meditation = float(record['Meditation']) if not math.isnan(float(record['Meditation'])) else None
        weather = record['Weather'] if pd.notna(record['Weather']) else None
        notes = record['Notes'] if pd.notna(record['Notes']) else None
        temperature = round(fahrenheit_to_celsius(float(record['Temperature (F)'])),
                            2) if 'Temperature (F)' in record and not math.isnan(float(record['Temperature (F)'])) else None

        name = generate_name(anthropic_client, record)

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

        add_record_to_notion(notion, NOTION_DATABASE_ID, record_for_notion)


if __name__ == "__main__":
    main()
