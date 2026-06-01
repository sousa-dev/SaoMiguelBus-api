"""Raw legacy tables preserved for full production imports."""

from __future__ import annotations

from django.db import models


class LegacyData(models.Model):
    id = models.AutoField(primary_key=True)
    data = models.JSONField()
    origin = models.CharField(max_length=100, null=True, blank=True)
    destination = models.CharField(max_length=100, null=True, blank=True)
    language_code = models.CharField(max_length=100, null=True, blank=True)
    time = models.CharField(max_length=100, null=True, blank=True)
    platform = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'app_data'


class LegacyTrip(models.Model):
    id = models.AutoField(primary_key=True)
    route = models.CharField(max_length=100)
    stops = models.JSONField()
    cleaned_stops = models.JSONField()
    type_of_day = models.CharField(max_length=100)
    information = models.JSONField()
    disabled = models.BooleanField(default=False)
    added = models.DateTimeField()
    likes = models.IntegerField(default=0)
    dislikes = models.IntegerField(default=0)

    class Meta:
        db_table = 'app_trip'


class LegacyTripStop(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    cleaned_name = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'app_tripstop'


class LegacyAIFeedback(models.Model):
    id = models.AutoField(primary_key=True)
    language = models.CharField(max_length=10, null=True, blank=True)
    first_time = models.BooleanField(null=True, blank=True)
    residence_status = models.CharField(max_length=50, null=True, blank=True)
    guide_preference = models.CharField(max_length=50, null=True, blank=True)
    payment_willingness = models.CharField(max_length=50, null=True, blank=True)
    timestamp = models.DateTimeField()

    class Meta:
        db_table = 'app_aifeedback'


class LegacyEmailOpen(models.Model):
    id = models.AutoField(primary_key=True)
    email_template_id = models.IntegerField()
    contact_id = models.IntegerField()
    clicks = models.IntegerField(default=0)

    class Meta:
        db_table = 'app_emailopen'
