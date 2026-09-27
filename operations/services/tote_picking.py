
from django.db import transaction
from django.utils import timezone

from core.models import Employee
from operations.models import Task, OperationLog, TaskLine
from warehouse.models import StorageUnit, Cell


def assign_tote(employee_id, tote_barcode):
    """
    Кладовщик берёт наборную тару - пустую тару.
    Система проверяет, что тара:
      - существует,
      - имеет тип 'tote',
      - не назначена другому сотруднику,
      - не занята другим заданием.
    """

    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return False, "Сотрудник не найден"
    #Проверка что сотрудник отборщик
    if employee.group != 'picker':
        return False, f"Только отборщики могут брать наборную тару (у {employee.name} группа: {employee.get_group_display()})"

    try:
        tote = StorageUnit.objects.get(barcode=tote_barcode, type='tote')
    except StorageUnit.DoesNotExist:
        return False, "Наборная тара не найдена"

    # Проверка: не назначена ли она кому-то ещё
    if tote.assigned_to and tote.assigned_to != employee:
        return False, f"Тара уже выдана сотруднику {tote.assigned_to.name}"

    # Проверка: не используется ли она в активном задании
    active_task = Task.objects.filter(
        picking_tote=tote,
        status__in=['new', 'in_progress']
    ).first()
    if active_task:
        return False, f"Тара уже используется в задании #{active_task.id}"

    with transaction.atomic():
        tote.assigned_to = employee
        tote.is_picking_tote = True
        tote.save(update_fields=['assigned_to', 'is_picking_tote'])

    return True, f"Тара {tote.barcode} выдана сотруднику {employee.name}"


def get_next_task_for_employee(employee_id):
    """
    Возвращает следующее задание для сотрудника:
    - сначала 'in_progress' (уже начатые),
    - потом 'new' (новые), отсортированные по FIFO.
    """
    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return None, "Сотрудник не найден"

    tote = StorageUnit.objects.filter(
        assigned_to=employee,
        is_picking_tote=True
    ).first()
    if not tote:
        return None, "У вас нет назначенной наборной тары. Возьмите тару."

    # 1. Активное задание сотрудника
    task = Task.objects.filter(
        assignee=employee,
        status='in_progress'
    ).order_by('created_at').first()

    if task:
        return task, "Продолжаем текущее задание"

    # 2. Новое задание, привязанное к таре
    task = Task.objects.filter(
        picking_tote=tote,
        status='new'
    ).order_by('created_at').first()

    if not task:
        return None, "Нет доступных заданий"

    return task, "Новое задание получено"


def confirm_pick(task_line_id, tote_barcode, employee_id):
    """
    Подтверждение отбора короба в наборную тару.
    Списывает товар из короба хранения и добавляет его в тару.
    """
    try:
        line = TaskLine.objects.select_related('task', 'storage_unit').get(id=task_line_id)
    except TaskLine.DoesNotExist:
        return False, "Строка задания не найдена"

    task = line.task

    if line.is_completed:
        return False, "Этот короб уже подтверждён"

    if task.status not in ('new', 'in_progress'):
        return False, f"Задание нельзя выполнить (статус: {task.status})"

    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return False, "Сотрудник не найден"
    # Проверка что сотрудник отборщик
    if employee.group != 'picker':
        return False, f"Только отборщики могут подтверждать отбор"

    try:
        tote = StorageUnit.objects.get(barcode=tote_barcode, type='tote', is_picking_tote=True)
    except StorageUnit.DoesNotExist:
        return False, "Наборная тара не найдена"

    if tote.assigned_to != employee:
        return False, f"Тара принадлежит другому сотруднику: {tote.assigned_to.name if tote.assigned_to else 'не назначена'}"

    source_unit = line.storage_unit
    quantity_to_pick = line.quantity

    if source_unit.quantity < quantity_to_pick:
        return False, f"В коробе {source_unit.barcode} недостаточно товара (нужно {quantity_to_pick}, есть {source_unit.quantity})"

    with transaction.atomic():
        # 1. Списываем из короба хранения
        source_unit.quantity -= quantity_to_pick
        source_unit.save(update_fields=['quantity'])

        # 2. Ищем или создаём объект внутри тары
        inner_unit = StorageUnit.objects.filter(parent=tote, product=source_unit.product).first()
        if not inner_unit:
            inner_unit = StorageUnit.objects.create(
                type='box',
                barcode=f"{tote.barcode}-{source_unit.product.code}",
                parent=tote,
                product=source_unit.product,
                quantity=0,
                current_cell=tote.current_cell,
            )

        inner_unit.quantity += quantity_to_pick
        inner_unit.save(update_fields=['quantity'])

        # 3. Помечаем строку выполненной
        line.is_completed = True
        line.completed_at = timezone.now()
        line.save(update_fields=['is_completed', 'completed_at'])

        # 4. Журнал
        OperationLog.objects.create(
            task=task,
            operation_type='pick',
            executor=employee,
            source_cell=source_unit.current_cell,
            target_cell=tote.current_cell,
            storage_unit=source_unit,
            quantity=quantity_to_pick,
        )

        # 5. Если все строки задания выполнены — завершаем задание
        if not task.lines.filter(is_completed=False).exists():
            task.status = 'done'
            task.save(update_fields=['status'])

            # 5.1 Проверяем, все ли задания по заявке выполнены
            order = task.order_line.order if task.order_line else None
            if order:
                remaining = Task.objects.filter(
                    order_line__order=order
                ).exclude(status='done')
                if not remaining.exists():
                    # Заявка СОБРАНА, но ещё не отгружена
                    order.status = 'picked'
                    order.save(update_fields=['status'])

    return True, f"Товар {source_unit.product.name} x {quantity_to_pick} переложен в тару {tote.barcode}"


def close_tote(tote_barcode, employee_id, target_cell_id=None):
    """
    Кладовщик сбрасывает заполненную наборную тару в целевую зону (отгрузка).

    :param tote_barcode: ШК наборной тары
    :param employee_id: ID сотрудника
    :param target_cell_id: (опционально) ID ячейки, куда положить тару.
                           Если не задан — ищем свободную ячейку в зоне 'shipping'.
    """
    # 1. Поиск тары
    try:
        tote = StorageUnit.objects.get(barcode=tote_barcode, type='tote')
    except StorageUnit.DoesNotExist:
        return False, "Тара не найдена"

    # 2. Находим сотрудника
    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return False, "Сотрудник не найден"
    #Проверка что сотрудник отборщик
    if employee.group != 'picker':
        return False, f"Только отборщики могут сдавать тару"

    # 3. Проверка, что нет активных заданий
    active_tasks = Task.objects.filter(
        picking_tote=tote,
        status__in=['new', 'in_progress']
    )
    if active_tasks.exists():
        return False, f"У тары остались незавершённые задания ({active_tasks.count()})"

    # 4. Определение целевой ячейки
    target_cell = None
    if target_cell_id:
        # Пользователь указал конкретную ячейку
        try:
            target_cell = Cell.objects.get(id=target_cell_id)
        except Cell.DoesNotExist:
            return False, "Указанная ячейка не найдена"
    else:
        # Ищем свободную ячейку в зоне отгрузки
        target_cell = Cell.objects.filter(
            rack__zone__zone_type='shipping',
            is_blocked_in=False,
            storage_units__isnull=True  # в ячейке ничего не лежит
        ).first()

        if not target_cell:
            return False, "Нет свободных ячеек в зоне отгрузки"

    # 5. Запоминаем исходную ячейку для журнала
    old_cell = tote.current_cell

    # 6. Открываем транзакцию
    with transaction.atomic():
        # 6.1 Перемещаем тару в целевую ячейку
        tote.current_cell = target_cell
        # 6.2 Освобождаем тару от сотрудника и снимаем флаг
        tote.assigned_to = None
        tote.is_picking_tote = False
        tote.save(update_fields=['current_cell', 'assigned_to', 'is_picking_tote'])

        # 6.3 Пишем в журнал операций, что тара перемещена
        OperationLog.objects.create(
            operation_type='move',
            executor=employee,
            source_cell=old_cell,
            target_cell=target_cell,
            storage_unit=tote,
            quantity=tote.quantity  # общее кол-во в таре
        )

    return True, f"Тара {tote.barcode} перемещена в ячейку {target_cell}"