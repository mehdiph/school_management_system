from django.apps import AppConfig


class WebsiteConfig(AppConfig):
    name = 'website'
    verbose_name = 'وب‌سایت'

    def ready(self):
        from . import signals

        signals.connect()
