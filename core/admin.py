from django.contrib import admin

from core.models import Zone, Employee


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "zone_type",
    )
    list_filter = ("zone_type",)
    search_fields = ("name",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "group", "barcode")
    list_filter = ("group",)
    search_fields = ("barcode", "name")
