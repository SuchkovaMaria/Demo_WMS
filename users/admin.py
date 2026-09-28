from django.contrib import admin

from users.models import User


@admin.register(User)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "email",
        "phone",
        "token",
    )
    list_filter = ("email",)
    search_fields = ("phone", "email")
