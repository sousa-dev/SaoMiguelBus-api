
import pandas as pd
import matplotlib.pyplot as plt

def group_get_routes(list):
    route_requests = {}
    for request in list:
        key = f"{request['origin']} -> {request['destination']}"
        if key in route_requests:
            route_requests[key].append(request)
        else:
            route_requests[key] = [request]
    return route_requests


def group_find(list):
    find_requests = {}
    for request in list:
        key = request['origin']
        if key in find_requests:
            find_requests[key].append(request)
        else:
            find_requests[key] = [request]
    return find_requests

def group_map(list):
    map_requests = {}
    for request in list:
        key = request['destination']
        if key in map_requests:
            map_requests[key].append(request)
        else:
            map_requests[key] = [request]
    return map_requests

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

def get_day_of_week_stats(list):
    percentage = False
    days = {
    "Monday": [],
    "Tuesday": [],
    "Wednesday": [],
    "Thursday": [],
    "Friday": [],
    "Saturday": [],
    "Sunday": []
}
    for alert in list:
        day = get_weekday(alert['timestamp'])
        days[day].append(alert)
    days = {key: f"{round((len(value) / len(list)) * 100, 2)}%" for key, value in days.items()} if percentage else days
    return days

def get_hourly_stats(list):
    percentage = False

    hours = {
        "00": 0,
        "01": 0,
        "02": 0,
        "03": 0,
        "04": 0,
        "05": 0,
        "06": 0,
        "07": 0,
        "08": 0,
        "09": 0,
        "10": 0,
        "11": 0,
        "12": 0,
        "13": 0,
        "14": 0,
        "15": 0,
        "16": 0,
        "17": 0,
        "18": 0,
        "19": 0,
        "20": 0,
        "21": 0,
        "22": 0,
        "23": 0
    }

    for alert in list:
        hour = alert['timestamp'].split("T")[1].split(":")[0]
        hours[hour] += 1
    hours = {key: f"{round((value / len(list)) * 100, 2)}%" for key, value in hours.items()} if percentage else hours
    
    x = []
    for k,v in hours.items():
        for _ in range(v):
            x.append(k)

    plt.title("Traffic Alerts per Hour")
    plt.hist(x, bins = 24)
    plt.xlabel("Hour")
    plt.ylabel("Percentage")
    plt.show()