from django.db import models

from core.models import Zone
from goods.models import Product
from warehouse.models import StorageUnit


class Order(models.Model):
    """Модель заказа"""

    TYPES = [('in', 'Входящая'), ('out', 'Исходящая')]

    STATUSES = [('new', 'Ожидает'), ('reserved', 'Зарезервирована'), ('picking', 'В отборе'), ('shipped', 'Отгружена'), ('picked', 'Собран'), ('shipping', 'В отгрузке'), ('receiving', 'Приёмка'), ('received', 'Принята'), ('putaway', 'Размещение'), ('stored', 'Размещена')]

    order_type = models.CharField(max_length=3, choices=TYPES)
    counterparty = models.CharField(max_length=200, help_text="Контрагент")
    order_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=STATUSES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = [
            "status",
        ]

    def __str__(self):
        return self.order_number


class OrderLine(models.Model):
    """ Модель строки заказа"""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    requested_quantity = models.DecimalField(max_digits=15, decimal_places=3, help_text="Количество товара в заказе")
    reserved_quantity = models.DecimalField(max_digits=15, decimal_places=3, default=0, help_text="Зарезервированно")
    received_quantity = models.DecimalField(
        max_digits=15, decimal_places=3, default=0,
        verbose_name="Принято",
        help_text="Сколько фактически принято (может отличаться от заказанного)."
    )

    class Meta:
        verbose_name = "Строка заказа"
        verbose_name_plural = "Строки заказа"
        ordering = [
            "order",
        ]

    def __str__(self):
        return self.product.name


class Reservation(models.Model):
    """Модель резерва"""

    order_line = models.ForeignKey(OrderLine, on_delete=models.CASCADE, related_name='reservations')
    storage_unit = models.ForeignKey(StorageUnit, on_delete=models.PROTECT)
    reserved_quantity = models.DecimalField(max_digits=15, decimal_places=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Резерв"
        verbose_name_plural = "Резервы"
        ordering = [
            "order_line",
        ]

    def __str__(self):
        return self.order_line.product.name


class Wave(models.Model):
    """Модель волны отбора"""

    STATUSES = [('draft', 'Наложена'), ('active', 'В работе'), ('completed', 'Завершена')]

    name = models.CharField(max_length=100)
    zone = models.ForeignKey(Zone, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUSES, default='draft')
    params = models.JSONField(default=dict, blank=True)  # параметры фильтрации
    orders = models.ManyToManyField(Order, related_name='waves')

    class Meta:
        verbose_name = "Волна"
        verbose_name_plural = "Волны"
        ordering = [
            "status",
        ]

    def __str__(self):
        return self.name

