from django.db import models

from core.models import Employee
from orders.models import Wave, OrderLine
from warehouse.models import Cell, StorageUnit


class Task(models.Model):
    """Модель операции"""

    TYPES = [('putaway', 'Размещение'), ('pick', 'Отбор'), ('move', 'Перемещение')]
    STATUSES = [('new', 'Новое'), ('in_progress', 'Выполняется'), ('done', 'Выполнено')]

    task_type = models.CharField(max_length=20, choices=TYPES)
    order_line = models.ForeignKey('orders.OrderLine', on_delete=models.SET_NULL, null=True, blank=True)
    source_cell = models.ForeignKey('warehouse.Cell', on_delete=models.PROTECT, related_name='tasks_from', null=True,
                                    blank=True)
    target_cell = models.ForeignKey('warehouse.Cell', on_delete=models.PROTECT, related_name='tasks_to', null=True,
                                    blank=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=3, default=0)  # общее количество
    status = models.CharField(max_length=20, choices=STATUSES, default='new')
    assignee = models.ForeignKey('core.Employee', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    wave = models.ForeignKey('orders.Wave', on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    picking_tote = models.ForeignKey(
        'warehouse.StorageUnit',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='picking_tasks',
        help_text="Наборная тара, в которую собирается товар"
    )

    class Meta:
        verbose_name = "Операция"
        verbose_name_plural = "Операции"
        ordering = [
            "task_type",
        ]

    def __str__(self):
        return self.task_type


class TaskLine(models.Model):
    """Модель строка задания — конкретный короб, который нужно взять."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='lines')
    storage_unit = models.ForeignKey('warehouse.StorageUnit', on_delete=models.PROTECT, related_name='task_lines')
    quantity = models.DecimalField(max_digits=15, decimal_places=3)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Строка заданий"
        verbose_name_plural = "Строки заданий"
        ordering = [
            "storage_unit",
        ]

    def __str__(self):
        return self.storage_unit.barcode

class OperationLog(models.Model):
    """Модель отчета"""

    OPERATION_TYPES = [
        ('pick', 'Отбор'),
        ('move', 'Перемещение'),
        ('putaway', 'Размещение'),
        ('receive', 'Приёмка'),
        ('ship', 'Отгрузка'),
    ]
    operation_type = models.CharField(max_length=20, choices=OPERATION_TYPES)
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True)
    executor = models.ForeignKey(Employee, on_delete=models.PROTECT)
    source_cell = models.ForeignKey(Cell, on_delete=models.PROTECT, related_name='ops_from', null=True)
    target_cell = models.ForeignKey(Cell, on_delete=models.PROTECT, related_name='ops_to', null=True)
    storage_unit = models.ForeignKey(StorageUnit, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=15, decimal_places=3)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(
        blank=True, null=True,
        verbose_name="Примечание",
        help_text="Недостача, комментарий, пояснение — всё в текстовом виде."
    )

    class Meta:
        verbose_name = "Отчеты"
        verbose_name_plural = "Отчеты"
        ordering = [
            "operation_type",
        ]

    def __str__(self):
        return self.task
