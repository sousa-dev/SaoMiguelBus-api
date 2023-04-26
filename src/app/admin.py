from django.contrib import admin
from app.models import Stop, Route, Stat, Variables

admin.site.register(Stop)
admin.site.register(Route)
admin.site.register(Stat)
admin.site.register(Variables)