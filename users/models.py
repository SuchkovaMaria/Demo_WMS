from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Модель Пользователь"""

    username = None
    email = models.EmailField(unique=True, blank=True, null=True, verbose_name="Email")
    phone = models.CharField(
        max_length=11, verbose_name="Телефон", blank=True, null=True, help_text="Укажите номер телефона"
    )

    token = models.CharField(max_length=100, verbose_name="Token", blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "Управляющий"
        verbose_name_plural = "Управляющие"

    def __str__(self):
        return self.email