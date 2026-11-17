from django.apps import AppConfig


class OnlineClassesConfig(AppConfig):
    name = 'online_classes'
    verbose_name = 'کلاس‌ها و آزمون‌های آنلاین'

    def ready(self):
        from . import signals

        signals.connect()
