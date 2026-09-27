from django.db import models

class Product(models.Model):
    """Модель товара"""

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    weight = models.DecimalField(max_digits=10, decimal_places=3, help_text="Вес")
    volume = models.DecimalField(max_digits=10, decimal_places=3, help_text="Объем")
    width = models.DecimalField(max_digits=10, decimal_places=2, help_text="Ширина")
    height = models.DecimalField(max_digits=10, decimal_places=2, help_text="Высота")
    length = models.DecimalField(max_digits=10, decimal_places=2, help_text="Длина")
    barcode = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = [
            "barcode",
        ]

    def __str__(self):
        return self.name

