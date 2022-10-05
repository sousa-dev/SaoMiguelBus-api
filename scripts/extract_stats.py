import requests
import pandas as pd

def get_weekday(timestamp):
    year = timestamp.split("T")[0].split("-")[0]
    month = timestamp.split("T")[0].split("-")[1]
    day = timestamp.split("T")[0].split("-")[2]
    ts = pd.Timestamp(int(year.lstrip("0")), int(month.lstrip("0")), int(day.lstrip("0")))
    if ts.day_of_week == 0:
        return "Monday"
    elif ts.day_of_week == 1:
        return "Tuesday"
    elif ts.day_of_week == 2:
        return "Wednesday"
    elif ts.day_of_week == 3:
        return "Thursday"
    elif ts.day_of_week == 4:
        return "Friday"
    elif ts.day_of_week == 5:
        return "Saturday"
    elif ts.day_of_week == 6:
        return "Sunday"

if __name__ == "__main__":
    response = requests.get('https://saomiguelbus-api.herokuapp.com/api/v1/stats').json()

    stats = {}

    for stat in response:
        if stat['request'] in stats:
            stats[stat['request']].append(stat)
        else:
            stats[stat['request']] = [stat]

    #print(f"Android Load Requests: {len(stats['android_load'])}\nGet Route Requests: {len(stats['get_route'])}")
