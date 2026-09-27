from django.contrib import admin

from goods.models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "barcode",
        "name",
        "code",
        "weight",
        "volume",
        "width",
        "height",
        "length",
    )
    list_filter = ("name",)
    search_fields = ("barcode", "code", "name")
