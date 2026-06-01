from collections import defaultdict
from datetime import datetime
import json
import requests
import pandas as pd

# Sample data
data = requests.get('http://127.0.0.1:8000/api/v2/route?all=True').json()
# Normalize stops
for entry in data:
    entry['stops'] = json.loads(entry['stops'].replace("'", '"'))

df = pd.DataFrame(data)

# Extract origin and destination
df['origin'] = df['stops'].apply(lambda x: list(x.keys())[0])
df['destination'] = df['stops'].apply(lambda x: list(x.keys())[-1])

# Helper function to sort stops by time
def sort_stops_by_time(stops_dict):
    stops_with_time = [(stop, datetime.strptime(time, '%Hh%M')) for stop, time in stops_dict.items()]
    sorted_stops = sorted(stops_with_time, key=lambda x: x[1])
    sorted_stops_dict = {stop: time.strftime('%Hh%M') for stop, time in sorted_stops}
    return sorted_stops_dict

# Group by route, origin, and destination
grouped = df.groupby(['route', 'origin', 'destination'])

# Function to assign timetable IDs
def assign_timetable_ids(group):
    timetable_dict = defaultdict(list)
    timetable_id = 1
    for idx, row in group.iterrows():
        sorted_stops = sort_stops_by_time(row['stops'])
        timetable_key = tuple(sorted_stops.items())
        if timetable_key not in timetable_dict:
            timetable_dict[timetable_key] = timetable_id
            timetable_id += 1
        row['timetable_id'] = timetable_dict[timetable_key]
        merged_data.append(row)

merged_data = []
for (route, origin, destination), group in grouped:
    assign_timetable_ids(group)


merged_df = pd.DataFrame(merged_data)

for entry in merged_data:
    print(entry['route'])
    print(entry['stops'])
