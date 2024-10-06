from app.models import Holiday


def get_type_of_day(day):
    holidays = Holiday.objects.filter(date=day)
    if holidays.exists():
        return 'SUNDAY'

    if day.weekday() == 5:
        return 'SATURDAY'
    elif day.weekday() == 6:
        return 'SUNDAY'
    else:
        return 'WEEKDAY'
