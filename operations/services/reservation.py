from django.db import transaction
from django.db.models import Sum, Q, F

from orders.models import Order, OrderLine, Reservation
from warehouse.models import StorageUnit


def reserve_order(order_id):
    """
    Функция резерва товаров под заказ.
    Возвращает кортеж (успех_флага, сообщения).
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return False, "Заявка не найдена"

    # Проверка полученного статуса
    if order.status != "new":
        return False, f"Заявка уже в обработке (статус: {order.status})"

    # Получение всех строк заявки и их блокировка для обновления
    with transaction.atomic():
        # Блокируем строки заявки, чтобы избежать двойного резервирования
        lines = OrderLine.objects.filter(order=order).select_for_update()  # - блокирует выбранные строки в БД

        all_reserved = True

        for line in lines:
            # requested_quantity — сколько заказано всего
            # reserved_quantity — сколько уже зарезервировано ранее
            need = line.requested_quantity - line.reserved_quantity
            if need <= 0:
                continue

            # Запрос к таблице StorageUnit, ищем только те, где лежит нужный товар в не заблокированных на выход ячейках
            available_unit_ids = (
                StorageUnit.objects.filter(
                    product=line.product,
                    current_cell__is_blocked_out=False,
                )
                .annotate(reserved_sum=Sum("reservation__reserved_quantity"))
                .filter(Q(reserved_sum__isnull=True) | Q(reserved_sum__lt=F("quantity")))
                .values_list("id", flat=True)  # ← Берём только ID
                .order_by("barcode")
            )

            available_units = StorageUnit.objects.filter(
                id__in=list(available_unit_ids)  # фильтруем по списку ID
            ).select_for_update()  # Блокировка

            for unit in available_units:
                if need <= 0:
                    break

                # Вычисляем свободное незарезервированое количество товара
                reserved_on_unit = (
                    Reservation.objects.filter(storage_unit=unit).aggregate(total=Sum("reserved_quantity"))["total"]
                    or 0
                )

                available = unit.quantity - reserved_on_unit

                if available <= 0:
                    continue

                # Резерв минимального из того, что нужно и что доступно
                to_reserve = min(need, available)

                Reservation.objects.create(order_line=line, storage_unit=unit, reserved_quantity=to_reserve)

                line.reserved_quantity = F("reserved_quantity") + to_reserve

                # Сохранение изменения в БД, обновляя только одно поле (для производительности)
                line.save(update_fields=["reserved_quantity"])

                need -= to_reserve

            if need > 0:
                all_reserved = False  # Заявка не может быть выполнена полностью

        # Если удалось зарезервировать всё — смена статуса на 'reserved'
        if all_reserved:
            order.status = "reserved"
            order.save(update_fields=["status"])
            return True, "Заявка полностью зарезервирована"
        else:
            return True, "Заявка зарезервирована частично (недостаточно товара)"
