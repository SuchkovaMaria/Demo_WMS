from django.contrib import admin

from warehouse.models import Rack, Cell, StorageUnit


@admin.register(Rack)
class RackAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "number",
        "zone",
    )
    list_filter = ("zone",)
    search_fields = ("number",)


@admin.register(Cell)
class RackAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "number",
        "rack",
        "volume",
        "is_blocked_in",
        "is_blocked_out",
        "barcode",
    )
    list_filter = ("rack","is_blocked_in","is_blocked_out",)
    search_fields = ("barcode",)

@admin.register(StorageUnit)
class StorageUnitAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "barcode",
        "type",
        "parent",
        "current_cell",
    )

    search_fields = ("barcode",)