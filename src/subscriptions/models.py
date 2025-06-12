from django.db import models
from django.core.validators import EmailValidator

class Subscription(models.Model):
    """Simple subscription model for manual management"""
    id = models.AutoField(primary_key=True)
    email = models.EmailField(validators=[EmailValidator()], unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'subscriptions'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.email} - {'Active' if self.is_active else 'Inactive'}"
