from decimal import Decimal

from django.db import transaction

from core.models import Employee
from goods.models import Product
from operations.models import OperationLog
from orders.models import Order, OrderLine
from warehouse.models import StorageUnit, Cell


def scan_product_for_receiving(order_id, product_barcode, boxes_count, per_box_qty, employee_id):
    """
    Функция приемки
    Оператор отсканировал ШК товара и указал количество коробов и кратность.

    Функция:
    - Находит строку заявки с этим товаром
    - Создаёт паллету (PALLET-IN-NNN)
    - Создаёт короба (BOX-NNN-M) и распределяет их по паллетам
    - Контролирует объём паллеты (MAX_VOLUME = 1 м³)
    - Если паллета переполняется — закрывает её и создаёт новую
    - Возвращает список созданных паллет и инструкции оператору

    :param order_id: ID входящей заявки
    :param product_barcode: ШК товара
    :param boxes_count: сколько коробов пришло (int)
    :param per_box_qty: сколько единиц в одном коробе (Decimal или int)
    :param employee_id: ID приёмщика
    """

    # 1. Проверка заявки
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return False, "Заявка не найдена", []

    if order.order_type != "in":
        return False, "Это не входящая заявка", []

    if order.status != "receiving":
        return False, f"Заявка не в процессе приёмки (статус: {order.get_status_display()})", []

    # 2. Проверка сотрудника
    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return False, "Сотрудник не найден", []

    if employee.group != "receiver":
        return False, f"Сотрудник {employee.name} не является приёмщиком", []

    # 3. Находим товар по ШК
    try:
        product = Product.objects.get(barcode=product_barcode)
    except Product.DoesNotExist:
        return False, f"Товар с ШК {product_barcode} не найден", []

    # 4. Находим строку заявки с этим товаром
    line = OrderLine.objects.filter(order=order, product=product).first()
    if not line:
        return False, f"Товара «{product.name}» нет в заявке {order.order_number}", []

    # 5. Проверяем, что товар ещё не принят полностью
    remaining = line.requested_quantity - line.received_quantity
    if remaining <= 0:
        return False, f"Товар «{product.name}» уже принят полностью", []

    # 6. Проверяем, что не принимаем больше, чем надо
    total_incoming = Decimal(boxes_count) * Decimal(per_box_qty)
    if total_incoming > remaining:
        return False, (f"Слишком много: по заявке осталось принять {remaining}, " f"а вы вводите {total_incoming}"), []

    # 7. Объём одного короба
    volume_per_box = product.volume * Decimal(per_box_qty)
    if volume_per_box > StorageUnit.MAX_VOLUME:
        return (
            False,
            (f"Короб объёмом {volume_per_box} м³ превышает объём паллеты " f"({StorageUnit.MAX_VOLUME} м³)"),
            [],
        )

    # 8. Создаём паллеты и короба в транзакции
    created_pallets = []

    with transaction.atomic():
        remaining_boxes = boxes_count
        current_pallet = None

        while remaining_boxes > 0:
            # Проверяем, нужна ли новая паллета:
            #   - если её нет, или
            #   - если текущая паллета + следующий короб переполнится
            if current_pallet is None or current_pallet.total_volume + volume_per_box > StorageUnit.MAX_VOLUME:
                # Закрываем старую паллету (если была)
                if current_pallet is not None:
                    current_pallet.is_closed = True
                    current_pallet.is_opened_for_receiving = False
                    current_pallet.save(update_fields=["is_closed", "is_opened_for_receiving"])
                    created_pallets.append(current_pallet)

                # Создаём новую паллету
                pallet_number = StorageUnit.objects.filter(barcode__startswith="OC-").count() + 1
                pallet_barcode = f"OC-{pallet_number:03d}"

                current_pallet = StorageUnit.objects.create(
                    type="pallet",
                    barcode=pallet_barcode,
                    product=None,  # паллета смешанная — не привязана к одному товару
                    quantity=0,
                    current_cell=None,  # пока не в ячейке — «в руках» оператора
                    total_volume=Decimal("0"),
                    is_opened_for_receiving=True,
                )

            # Создаём короб и кладём на паллету
            box_number = StorageUnit.objects.filter(barcode__startswith=f"KR-{current_pallet.barcode}-").count() + 1
            box_barcode = f"KR-{current_pallet.barcode}-{box_number:03d}"

            box = StorageUnit.objects.create(
                type="box",
                barcode=box_barcode,
                parent=current_pallet,
                product=product,
                quantity=Decimal(per_box_qty),
                current_cell=None,
                total_volume=volume_per_box,
            )

            # Обновляем объём паллеты
            current_pallet.total_volume += volume_per_box
            current_pallet.save(update_fields=["total_volume"])

            remaining_boxes -= 1

        # 9. Обновляем received_quantity в строке заявки
        line.received_quantity += Decimal(boxes_count) * Decimal(per_box_qty)
        line.save(update_fields=["received_quantity"])

    # 10. Собираем сообщение для оператора
    total_pallets = len(created_pallets) + (1 if current_pallet else 0)
    message_lines = [
        f"Принято {boxes_count} коробов по {per_box_qty} ед. товара «{product.name}».",
        f"Создано паллет: {total_pallets}.",
    ]

    if created_pallets:
        closed = ", ".join(p.barcode for p in created_pallets)
        message_lines.append(f"Закрытые паллеты: {closed}.")
        message_lines.append("Отсканируйте ШК ячейки приёмки для каждой закрытой паллеты.")

    if current_pallet:
        message_lines.append(
            f"Текущая открытая паллета: {current_pallet.barcode} " f"(объём {current_pallet.total_volume} м³)."
        )

    return True, " ".join(message_lines), created_pallets + [current_pallet] if current_pallet else created_pallets


def start_receiving(order_id, employee_id):
    """
    Начало приёмки заявки.
    Проверяет роль (только receiver), меняет статус заявки на 'receiving'.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return False, "Заявка не найдена"

    if order.order_type != "in":
        return False, "Это не входящая заявка"

    if order.status != "new":
        return False, f"Заявку нельзя принять (статус: {order.get_status_display()})"

    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return False, "Сотрудник не найден"

    if employee.group != "receiver":
        return False, (
            f"Сотрудник {employee.name} не является приёмщиком " f"(группа: {employee.get_group_display()})"
        )

    order.status = "receiving"
    order.save(update_fields=["status"])

    return True, (f"Приёмка заявки {order.order_number} начата. " f"Отсканируйте ШК товара.")


def confirm_pallet_close(pallet_barcode, receiving_cell_barcode, employee_id):
    """
    Оператор закрывает паллету и кладёт её в ячейку зоны приёмки.
    """
    # 1. Находим паллету
    try:
        pallet = StorageUnit.objects.get(barcode=pallet_barcode, type="pallet")
    except StorageUnit.DoesNotExist:
        return False, f"Паллета {pallet_barcode} не найдена"

    if pallet.is_closed:
        return False, f"Паллета {pallet.barcode} уже закрыта"

    # 2. Сотрудник
    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return False, "Сотрудник не найден"

    if employee.group != "receiver":
        return False, f"Сотрудник {employee.name} не является приёмщиком"

    # 3. Ячейка приёмки
    try:
        cell = Cell.objects.get(barcode=receiving_cell_barcode)
    except Cell.DoesNotExist:
        return False, f"Ячейка {receiving_cell_barcode} не найдена"

    # 4. Проверяем, что ячейка в зоне приёмки
    if cell.rack.zone.zone_type != "receiving":
        return False, (f"Ячейка {cell.barcode} не в зоне приёмки " f"(зона: {cell.rack.zone.name})")

    # 5. Блокировки
    if cell.is_blocked_in:
        return False, f"Ячейка {cell.barcode} заблокирована на вход"

    # 6. Перемещаем паллету
    with transaction.atomic():
        old_cell = pallet.current_cell

        pallet.current_cell = cell
        pallet.is_closed = True
        pallet.is_opened_for_receiving = False
        pallet.save(update_fields=["current_cell", "is_closed", "is_opened_for_receiving"])

        OperationLog.objects.create(
            operation_type="receive",
            executor=employee,
            source_cell=old_cell,
            target_cell=cell,
            storage_unit=pallet,
            quantity=pallet.total_volume,
            notes=f"Паллета {pallet.barcode} закрыта и помещена в ячейку {cell.barcode}",
        )

    return True, f"Паллета {pallet.barcode} закрыта и перемещена в ячейку {cell.barcode}"


def finish_receiving(order_id, employee_id):
    """
    Завершение приёмки заявки. Если есть недостача — фиксируем в журнале.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return False, "Заявка не найдена"

    if order.status != "receiving":
        return False, f"Заявка не в приёмке (статус: {order.get_status_display()})"

    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return False, "Сотрудник не найден"

    if employee.group != "receiver":
        return False, f"Сотрудник {employee.name} не является приёмщиком"

    # 1. Закрываем все оставшиеся открытые паллеты
    open_pallets = StorageUnit.objects.filter(
        type="pallet",
        is_opened_for_receiving=True,
    )

    with transaction.atomic():
        for pallet in open_pallets:
            pallet.is_closed = True
            pallet.is_opened_for_receiving = False
            pallet.save(update_fields=["is_closed", "is_opened_for_receiving"])

        # 2. Считаем недостачу по каждой строке
        discrepancies = []
        for line in order.lines.all():
            shortfall = line.requested_quantity - line.received_quantity
            if shortfall > 0:
                discrepancies.append((line, shortfall))
                OperationLog.objects.create(
                    operation_type="receive",
                    executor=employee,
                    storage_unit=StorageUnit.objects.filter(
                        type="pallet",
                        children__product=line.product,
                    ).first(),
                    quantity=line.received_quantity,
                    notes=(
                        f"Недостача по товару «{line.product.name}» ({line.product.code}): "
                        f"заказано {line.requested_quantity}, "
                        f"принято {line.received_quantity}, "
                        f"не хватило {shortfall}"
                    ),
                )

        # 3. Меняем статус заявки
        order.status = "received"
        order.save(update_fields=["status"])

    # 4. Формируем сообщение
    if discrepancies:
        parts = [f"«{line.product.name}» — не хватило {shortfall}" for line, shortfall in discrepancies]
        return True, (f"Приёмка заявки {order.order_number} завершена с недостачей: " + "; ".join(parts))

    return True, f"Приёмка заявки {order.order_number} завершена успешно"
