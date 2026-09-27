from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    verbose_name = "Core"

    def ready(self):
        from apps.core import signals  # noqa: F401  (connects the receivers)
