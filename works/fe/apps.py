from django.apps import AppConfig


class FeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'works.fe'
    # 置き場所を works/ に移したあとも、マイグレーションと DB の呼び名は変えない。
    label = 'fe'
    verbose_name = 'FE 基本情報技術者試験 対策'
