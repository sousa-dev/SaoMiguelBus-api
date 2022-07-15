from django.db import models
from jsonfield import JSONField


# Create your models here.

class Stop(models.Model):
    name = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    def __str__(self):
        return self.name

class Route(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    route = models.CharField(max_length=100)
    stops = models.ManyToManyField(Stop)
    type_of_day = models.CharField(max_length=100)
    information = JSONField()
    def __str__(self):
        return self.name