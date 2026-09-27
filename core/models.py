from django.db import models

from users.models import User


class Zone(models.Model):
    """Модель зоны склада"""

    ZONE_TYPES = [('receiving', 'Приемка'), ('storage', 'Хранение'), ('picking', 'Отбор'), ('shipping', 'Отгрузка'), ('gate', 'Ворота отгрузки')]

    name = models.CharField(max_length=100, unique=True)
    zone_type = models.CharField(max_length=20, choices=ZONE_TYPES)

    class Meta:
        verbose_name = "Зона"
        verbose_name_plural = "Зоны"
        ordering = [
            "zone_type",
        ]

    def __str__(self):
        return self.name


class Employee(models.Model):
    """Модель сотрудника"""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    name = models.CharField(max_length=150)  # ФИО
    group = models.CharField(max_length=50, choices=[('picker', 'Отбор'), ('receiver', 'Приемка'), ('shipper', 'Отгрузка')])
    barcode = models.CharField(max_length=50, unique=True)  # ШК сотрудника

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"
        ordering = [
            "name",
        ]

    def __str__(self):
        return self.name
