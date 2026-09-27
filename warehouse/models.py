from decimal import Decimal

from django.db import models

from core.models import Zone


class Rack(models.Model):
    """Модель стеллажа"""

    number = models.CharField(max_length=20, unique=True)
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='racks')

    class Meta:
        verbose_name = "Стеллаж"
        verbose_name_plural = "Стеллажи"
        ordering = [
            "number",
        ]

    def __str__(self):
        return f"Стеллаж {self.number}"


class Cell(models.Model):
    """Модель ячейки"""

    number = models.CharField(max_length=20)
    rack = models.ForeignKey(Rack, on_delete=models.CASCADE, related_name='cells')
    volume = models.DecimalField(max_digits=10, decimal_places=2, help_text="Объем в м3")
    is_blocked_in = models.BooleanField(default=False)
    is_blocked_out = models.BooleanField(default=False)
    barcode = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name = "Ячейка"
        verbose_name_plural = "Ячейки"
        ordering = [
            "number",
        ]
        unique_together = ('rack', 'number')  # Номер уникален в пределах стеллажа

    def __str__(self):
        return f"{self.rack.number}-{self.number}"


class StorageUnit(models.Model):
    """Объект"""

    TYPES = [('box', 'Короб'), ('pallet', 'Паллета'), ('tote', 'Наборная тара'),]

    type = models.CharField(max_length=10, choices=TYPES)
    barcode = models.CharField(max_length=50, unique=True)

    # Иерархия: если это короб внутри паллеты
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    # Ссылка на товар (заполняется только у коробов, у паллеты - null)

    product = models.ForeignKey('goods.Product', on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=3, default=0)  # кол-во в этой упаковке
    current_cell = models.ForeignKey(Cell, on_delete=models.SET_NULL, null=True, related_name='storage_units')
    is_picking_tote = models.BooleanField(default=False, help_text="Является ли этот объект наборной тарой")
    assigned_to = models.ForeignKey(
        'core.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_totes',
        help_text="Кладовщик, которому выдана эта тара"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    total_volume = models.DecimalField(
        max_digits=12, decimal_places=4, default=0,
        help_text="Суммарный объём содержимого (для паллет)"
    )
    is_closed = models.BooleanField(
        default=False,
        verbose_name="Закрыта",
        help_text="Для паллет: закрыта ли паллета (готова к размещению)."
    )
    is_opened_for_receiving = models.BooleanField(
        default=False,
        verbose_name="Открыта для приёмки",
        help_text="Для паллет: принимает ли сейчас короба."
    )
    MAX_VOLUME = Decimal('1.0')  # 1 м³ — порог заполнения паллеты

    @property
    def is_full(self):
        """Заполнена ли паллета до порога."""
        return self.total_volume >= self.MAX_VOLUME

    class Meta:
        verbose_name = "Объект"
        verbose_name_plural = "Объекты"
        ordering = [
            "barcode",
        ]

    def __str__(self):
        return f"{self.barcode} ({self.type})"


