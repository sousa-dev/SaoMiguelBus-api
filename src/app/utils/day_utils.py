from app.models import Holiday


def get_type_of_day(day):
    if Holiday.objects.filter(date=day).exists():
        return 'SUNDAY'

    weekday = day.weekday()
    if weekday == 5:
        return 'SATURDAY'
    elif weekday == 6:  # Sunday or Monday
        return 'SUNDAY'
    else:
        return 'WEEKDAY'
