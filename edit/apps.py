from django.apps import AppConfig


class EditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "edit"

    def ready(self):
        # ログイン失敗の監視を有効にする
        from . import signals  # noqa: F401
