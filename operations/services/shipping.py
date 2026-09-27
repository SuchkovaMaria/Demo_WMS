from django.db import transaction
from django.utils import timezone

from core.models import Employee
from operations.models import Task, OperationLog
from orders.models import Order
from warehouse.models import Cell


def ship_order(order_id, employee_id, gate_cell_id=None):
    """
    Отгрузка заявки: тара/товар перемещается из зоны отгрузки в ворота (gate).

    :param order_id: ID заявки
    :param employee_id: ID сотрудника-отгрузчика
    :param gate_cell_id: (опционально) ID ячейки в зоне ворот
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return False, "Заявка не найдена"

    if order.status != 'picked':
        return False, f"Заявку нельзя отгрузить (статус: {order.status})"

    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return False, "Сотрудник не найден"

    # проверка что это сотрудник отгрузки
    if employee.group != 'shipper':
        return False, f"Сотрудник {employee.name} не является отгрузчиком (группа: {employee.get_group_display()})"

    # 1. Находим все тары, привязанные к заданиям этой заявки
    tasks = Task.objects.filter(order_line__order=order, task_type='pick')
    totes = set()
    for task in tasks:
        if task.picking_tote:
            totes.add(task.picking_tote)

    if not totes:
        return False, "Не найдено ни одной тары для отгрузки"

    # 2. Определяем целевую ячейку (ворота)
    target_cell = None
    if gate_cell_id:
        try:
            target_cell = Cell.objects.get(id=gate_cell_id)
        except Cell.DoesNotExist:
            return False, "Ячейка ворот не найдена"
    else:
        # Ищем ячейку в зоне 'gate' (ворота)
        target_cell = Cell.objects.filter(
            rack__zone__zone_type='gate',
        ).first()
        if not target_cell:
            return False, "Нет ячейки в зоне ворот."

    with transaction.atomic():
        # 3. Перемещаем все тары в ворота
        for tote in totes:
            old_cell = tote.current_cell
            tote.current_cell = target_cell
            tote.save(update_fields=['current_cell'])

            OperationLog.objects.create(
                operation_type='ship',
                executor=employee,
                source_cell=old_cell,
                target_cell=target_cell,
                storage_unit=tote,
                quantity=tote.quantity,
            )

        # 4. Меняем статус заявки
        order.status = 'shipped'
        order.save(update_fields=['status'])

    return True, f"Заявка {order.order_number} отгружена. Тары: {', '.join(t.barcode for t in totes)}"