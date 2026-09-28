from django.db import models

from core.models import Zone


class PickingRoute(models.Model):
    """Модель маршрута обхода зоны при наборе"""

    STRATEGIES = [
        ("s_shape", "S-образный"),
        ("zigzag", "Зигзаг"),
        ("by_aisle", "По проходам"),
        ("closest", "Ближайший"),
    ]

    name = models.CharField(max_length=100)
    strategy = models.CharField(max_length=20, choices=STRATEGIES)
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="routes")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Маршрут"
        verbose_name_plural = "Маршруты обхода"
        ordering = [
            "strategy",
        ]

    def __str__(self):
        return self.name
