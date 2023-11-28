from datetime import timezone
from django.contrib.postgres.fields import DateTimeRangeField
from django.db import models

from members.models import User

class MembershipManager(models.Manager):
    def current(self):
        return self.get_queryset().filter(valid__contains=timezone.now())

class Membership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    valid = DateTimeRangeField()

    objects = MembershipManager()

    def is_current(self):
        return self.valid.lower <= timezone.now() < self.valid.upper

    def __str__(self):
        return "{} member from {} to {}".format(
            self.user, self.valid.lower, self.valid.upper
        )
