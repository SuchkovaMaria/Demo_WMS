from django.db import transaction
from django.utils import timezone

from core.models import Employee
from operations.models import Task, OperationLog, TaskLine
from orders.models import Order
from warehouse.models import StorageUnit, Cell


def create_putaway_tasks(order_id, employee_id):
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return 0, "Заявка не найдена"

    if order.order_type != "in":
        return 0, "Это не входящая заявка"

    if order.status != "received":
        return 0, f"Заявку нельзя разместить (статус: {order.get_status_display()})"

    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return 0, "Сотрудник не найден"

    if employee.group not in ("receiver", "picker"):
        return 0, f"Сотрудник {employee.name} не может размещать"

    # Находим закрытые паллеты в зоне приёмки
    pallets = StorageUnit.objects.filter(
        type="pallet",
        is_closed=True,
        current_cell__rack__zone__zone_type="receiving",
    )

    if not pallets.exists():
        return 0, "Нет паллет для размещения"

    created_count = 0
    with transaction.atomic():
        for pallet in pallets:
            # Проверяем, нет ли уже активного задания на эту паллету через TaskLine
            existing = Task.objects.filter(
                task_type="putaway",
                lines__storage_unit=pallet,
                status__in=["new", "in_progress"],
            ).exists()
            if existing:
                continue

            # Создаём задание и строку задания
            task = Task.objects.create(
                task_type="putaway",
                source_cell=pallet.current_cell,
                target_cell=None,
                quantity=pallet.total_volume,
                status="new",
            )
            TaskLine.objects.create(
                task=task,
                storage_unit=pallet,
                quantity=pallet.total_volume,
            )
            created_count += 1

        order.status = "putaway"
        order.save(update_fields=["status"])

    return created_count, f"Создано {created_count} заданий на размещение"


def confirm_putaway(task_id, target_cell_barcode, employee_id):
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return False, "Задание не найдено"

    if task.task_type != "putaway":
        return False, "Это не задание на размещение"

    if task.status not in ("new", "in_progress"):
        return False, f"Задание нельзя выполнить (статус: {task.get_status_display()})"

    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return False, "Сотрудник не найден"

    if employee.group not in ("receiver", "picker"):
        return False, f"Сотрудник {employee.name} не может размещать"

    try:
        target_cell = Cell.objects.get(barcode=target_cell_barcode)
    except Cell.DoesNotExist:
        return False, f"Ячейка {target_cell_barcode} не найдена"

    if target_cell.rack.zone.zone_type != "storage":
        return False, f"Ячейка {target_cell.barcode} не в зоне хранения"

    if target_cell.is_blocked_in:
        return False, f"Ячейка {target_cell.barcode} заблокирована на вход"

    if StorageUnit.objects.filter(current_cell=target_cell).exists():
        return False, f"Ячейка {target_cell.barcode} уже занята"

    # Перемещаем паллету из первой строки задания
    line = task.lines.first()
    if not line:
        return False, "У задания нет строк"

    pallet = line.storage_unit
    old_cell = pallet.current_cell

    with transaction.atomic():
        pallet.current_cell = target_cell
        pallet.save(update_fields=["current_cell"])

        task.status = "done"
        task.target_cell = target_cell
        task.assignee = employee
        task.save(update_fields=["status", "target_cell", "assignee"])

        line.is_completed = True
        line.completed_at = timezone.now()
        line.save(update_fields=["is_completed", "completed_at"])

        OperationLog.objects.create(
            operation_type="putaway",
            task=task,
            executor=employee,
            source_cell=old_cell,
            target_cell=target_cell,
            storage_unit=pallet,
            quantity=pallet.total_volume,
            notes=f"Паллета {pallet.barcode} размещена в ячейке {target_cell.barcode}",
        )

    return True, f"Паллета {pallet.barcode} размещена в ячейке {target_cell.barcode}"


def finish_putaway_order(order_id, employee_id):
    """
    Завершить размещение по заявке:
    - проверяет, что все задания выполнены,
    - меняет статус заявки на 'stored'.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return False, "Заявка не найдена"

    if order.status != "putaway":
        return False, f"Заявка не в размещении (статус: {order.get_status_display()})"

    # Активные задания по заявке — по source_cell из зоны приёмки.
    # Проще: ищем задания типа putaway, у которых source_cell в зоне receiving,
    # и которые ещё не done.
    active = Task.objects.filter(
        task_type="putaway",
    ).exclude(status="done")

    if active.exists():
        return False, f"Есть незавершённые задания на размещение: {active.count()}"

    with transaction.atomic():
        order.status = "stored"
        order.save(update_fields=["status"])

    return True, f"Заявка {order.order_number} полностью размещена (stored)"
