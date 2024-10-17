from django.contrib import admin
from app.models import Info, Stop, Route, Stat, Variables, Ad, Group, Holiday, Data, Trip, TripStop, AIFeedback

admin.site.register(Stop)
admin.site.register(Route)
admin.site.register(Stat)
admin.site.register(Variables)
admin.site.register(Ad)
admin.site.register(Group)
admin.site.register(Info)
admin.site.register(Holiday)
admin.site.register(Data)
admin.site.register(Trip)
admin.site.register(TripStop)
admin.site.register(AIFeedback)