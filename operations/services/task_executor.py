from django.db import transaction
from django.utils import timezone

from core.models import Employee
from operations.models import Task, TaskLine, OperationLog
from warehouse.models import StorageUnit, Cell


def start_task(task_id, employee_id):
    """Сборщик берёт задание в работу."""
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return False, "Задание не найдено"

    if task.status != "new":
        return False, f"Задание нельзя взять в работу (статус: {task.status})"

    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return False, "Сотрудник не найден"
    # Проверка что сотрудник отборщик
    if task.task_type == "pick" and employee.group != "picker":
        return False, f"Только отборщики могут брать задания на отбор"

    task.status = "in_progress"
    task.assignee = employee
    task.save(update_fields=["status", "assignee"])
    return True, f"Задание #{task.id} взято в работу сотрудником {employee.name}"


def get_next_task_for_employee(employee_id):
    """
    Возвращает следующее задание для сотрудника:
    - сначала 'in_progress' (уже начатые),
    - потом 'new' (новые), отсортированные по FIFO.
    Задание должно быть привязано к наборной таре сотрудника.
    """
    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return None, "Сотрудник не найден"

    # Проверка, что у сотрудника есть активная тара
    tote = StorageUnit.objects.filter(assigned_to=employee, is_picking_tote=True).first()
    if not tote:
        return None, "У вас нет назначенной наборной тары. Возьмите тару."

    # 1. Поиск активного задания сотрудника
    task = Task.objects.filter(assignee=employee, status="in_progress").order_by("created_at").first()

    if task:
        return task, "Продолжаем текущее задание"

    # 2. Поиск нового задания, привязанное к этой таре
    task = Task.objects.filter(picking_tote=tote, status="new").order_by("created_at").first()

    if not task:
        return None, "Нет доступных заданий"

    return task, "Новое задание получено"


def confirm_pick(task_line_id, tote_barcode, employee_id):
    """
    Подтверждение отбор короба в наборную тару.

    :param task_line_id: ID строки задания (TaskLine)
    :param tote_barcode: ШК наборной тары
    :param employee_id: ID сотрудника
    """
    try:
        line = TaskLine.objects.select_related("task", "storage_unit").get(id=task_line_id)
    except TaskLine.DoesNotExist:
        return False, "Строка задания не найдена"

    task = line.task

    if line.is_completed:
        return False, "Этот короб уже подтверждён"

    if task.status not in ("new", "in_progress"):
        return False, f"Задание нельзя выполнить (статус: {task.status})"

    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return False, "Сотрудник не найден"

    # Поиск наборной тары
    try:
        tote = StorageUnit.objects.get(barcode=tote_barcode, type="tote", is_picking_tote=True)
    except StorageUnit.DoesNotExist:
        return False, "Наборная тара не найдена"

    if tote.assigned_to != employee:
        return (
            False,
            f"Тара принадлежит другому сотруднику: {tote.assigned_to.name if tote.assigned_to else 'не назначена'}",
        )

    source_unit = line.storage_unit
    quantity_to_pick = line.quantity

    # Проверка, что в коробе хранения достаточно товара
    if source_unit.quantity < quantity_to_pick:
        return (
            False,
            f"В коробе {source_unit.barcode} недостаточно товара (нужно {quantity_to_pick}, есть {source_unit.quantity})",
        )

    with transaction.atomic():
        # 1. Списываем из короба хранения
        source_unit.quantity -= quantity_to_pick
        source_unit.save(update_fields=["quantity"])

        # # 2. Поиск или создание StorageUnit внутри наборной тары для этого товара
        # inner_unit, created = StorageUnit.objects.get_or_create(
        #     parent=tote,
        #     product=source_unit.product,
        #     defaults={
        #         'type': 'box',  # внутри тары — условный "короб"
        #         'barcode': f"{tote.barcode}-{source_unit.product.code}",
        #         'quantity': 0,
        #         'current_cell': tote.current_cell,  # тара где-то лежит, но её содержимое — внутри неё
        #     }
        # )

        # Если внутренний объект создан, но у него barcode уже занят
        inner_unit = StorageUnit.objects.filter(parent=tote, product=source_unit.product).first()
        if not inner_unit:
            inner_unit = StorageUnit.objects.create(
                type="box",
                barcode=f"{tote.barcode}-{source_unit.product.code}",
                parent=tote,
                product=source_unit.product,
                quantity=0,
                current_cell=tote.current_cell,
            )

        inner_unit.quantity += quantity_to_pick
        inner_unit.save(update_fields=["quantity"])

        # 3. Помечение строки задания выполненной
        line.is_completed = True
        line.completed_at = timezone.now()
        line.save(update_fields=["is_completed", "completed_at"])

        # 4. Пишем в журнал
        OperationLog.objects.create(
            task=task,
            operation_type="pick",
            executor=employee,
            source_cell=source_unit.current_cell,
            target_cell=tote.current_cell,  # тара где-то стоит
            storage_unit=source_unit,
            quantity=quantity_to_pick,
        )

        # 5. Если все строки задания выполнены — завершаем задание
        if not task.lines.filter(is_completed=False).exists():
            task.status = "done"
            task.save(update_fields=["status"])

        return True, f"Товар {source_unit.product.name} x {quantity_to_pick} переложен в тару {tote.barcode}"


def finish_task(task_id):
    """Завершает задание и, если все задания по заявке выполнены, закрывает заявку."""
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return False, "Задание не найдено"

    if task.status == "done":
        return False, "Задание уже завершено"

    if task.lines.filter(is_completed=False).exists():
        return False, "Не все строки задания выполнены"

    with transaction.atomic():
        task.status = "done"
        task.save(update_fields=["status"])

        order = task.order_line.order if task.order_line else None
        if order:
            remaining = Task.objects.filter(order_line__order=order).exclude(status="done")
            if not remaining.exists():
                order.status = "shipped"
                order.save(update_fields=["status"])
                return True, f"Задание завершено, заявка {order.order_number} готова к отгрузке"

    return True, f"Задание #{task.id} завершено"
