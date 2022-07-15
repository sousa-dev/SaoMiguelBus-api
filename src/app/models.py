from django.db import models
from jsonfield import JSONField
import json
from sqlalchemy import null


# Create your models here.

class Stop(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    def __str__(self):
        return self.name

class Route(models.Model):
    id = models.AutoField(primary_key=True)
    route = models.CharField(max_length=100)
    stops = JSONField()
    type_of_day = models.CharField(max_length=100)
    information = JSONField()
    def __str__(self):
        start = self.stops.split(',')[0].split(':')[0].replace('{','').replace('\'','')
        start_time = self.stops.split(',')[0].split(':')[1].replace('{','').replace('\'','')
        end = self.stops.split(',')[-1].split(':')[0].replace('}','').replace('\'','')
        return f"{self.route} | {start} -> {end} | {start_time}"