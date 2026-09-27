from collections import defaultdict

from django.db import transaction

from operations.models import Task, TaskLine
from orders.models import Order, Reservation


def create_picking_tasks_for_order(order_id):
    """
    Создаёт задания на отбор (pick) для всех резерваций заявки.
    Группирует резервации по ячейке и объекту складирования,
    чтобы сборщик не бегал в одну ячейку несколько раз.
    Возвращает количество созданных заданий.
    """

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return 0, "Заявка не найдена"

    if order.status not in ('reserved', 'new'):
        return 0, f"Заявка не может быть отправлена в отбор (статус: {order.status})"

    reservations = (
        Reservation.objects
        .filter(order_line__order=order)
        .select_related('storage_unit', 'storage_unit__current_cell', 'order_line')
    )

    if not reservations.exists():
        return 0, "Нет резерваций для создания заданий"

    # Группируем по ячейке
    groups = defaultdict(lambda: {
        'total_qty': 0,
        'order_line': None,
        'cell': None,
        'lines': []  # список коробов в этой ячейке
    })

    for res in reservations:
        cell = res.storage_unit.current_cell
        if not cell:
            continue

        key = cell.id  # ключ — только ID ячейки
        groups[key]['total_qty'] += res.reserved_quantity
        groups[key]['order_line'] = res.order_line
        groups[key]['cell'] = cell
        groups[key]['lines'].append({
            'storage_unit': res.storage_unit,
            'quantity': res.reserved_quantity
        })

    # Создание задания
    created_count = 0
    with transaction.atomic():
        for key, data in groups.items():
            # Создаём задание
            task = Task.objects.create(
                task_type='pick',
                order_line=data['order_line'],
                source_cell=data['cell'],
                target_cell=None,
                quantity=data['total_qty'],
                status='new'
            )
            # Создание строк задания (по одной на каждый короб)
            for line_data in data['lines']:
                TaskLine.objects.create(
                    task=task,
                    storage_unit=line_data['storage_unit'],
                    quantity=line_data['quantity']
                )
            created_count += 1

        order.status = 'picking'
        order.save(update_fields=['status'])

    return created_count, f"Создано {created_count} заданий на отбор"
