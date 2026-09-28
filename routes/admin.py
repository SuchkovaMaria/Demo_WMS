from django.contrib import admin

from routes.models import PickingRoute


@admin.register(PickingRoute)
class PickingRouteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "strategy",
        "zone",
        "is_active",
    )

    search_fields = (
        "name",
        "strategy",
    )
