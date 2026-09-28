from django.contrib import admin

from operations.models import Task, TaskLine


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "task_type",
        "order_line",
        "source_cell",
        "target_cell",
        "quantity",
        "status",
        "assignee",
        "created_at",
        "wave",
    )

    search_fields = (
        "assignee",
        "status",
    )


@admin.register(TaskLine)
class TaskLineAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "task",
        "storage_unit",
        "quantity",
        "is_completed",
        "completed_at",
    )

    search_fields = (
        "task",
        "storage_unit",
    )
