from django.apps import AppConfig


class CountdownConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "works.countdown"
    # 置き場所を works/ に移したあとも、マイグレーションと DB の呼び名は変えない。
    label = "countdown"
    verbose_name = "カウントアップ＆ダウン"
