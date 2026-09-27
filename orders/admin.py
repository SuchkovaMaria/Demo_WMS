from django.contrib import admin

from orders.models import Order, OrderLine, Reservation, Wave


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order_type",
        "counterparty",
        "order_number",
        "status",
        "created_at",
    )

    search_fields = ("order_number", "counterparty", "created_at")


@admin.register(OrderLine)
class OrderLineAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "product",
    )

    search_fields = ("order",)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order_line",
        "storage_unit",
        "created_at",
    )

    search_fields = ("storage_unit",)


@admin.register(Wave)
class WaveAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "zone",
        "status",
        "params",
    )
    search_fields = ("name",)
