def get_type_of_day(day, holiday):
    if holiday:
        return 'SUNDAY'

    weekday = day.weekday()
    if weekday == 5:
        return 'SATURDAY'
    elif weekday == 6:  # Sunday or Monday
        return 'SUNDAY'
    else:
        return 'WEEKDAY'
