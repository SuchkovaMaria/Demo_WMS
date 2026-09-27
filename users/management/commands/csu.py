import os

from django.core.management import BaseCommand

from users.models import User


class Command(BaseCommand):
    """Создание супер-пользователя"""

    def handle(self, *args, **options):
        user = User.objects.create(email=os.getenv("EMAIL_ADMIN"))
        user.set_password(os.getenv("PASSWORD_ADMIN"))
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.save()
