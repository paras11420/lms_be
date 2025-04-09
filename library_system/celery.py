from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "library_system.settings")

app = Celery("library_system")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(lambda: ['library_system'])

@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")

@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    from library_system.tasks import send_overdue_notifications
    sender.add_periodic_task(
        crontab(hour=8, minute=0),
        send_overdue_notifications.s(),
        name="Send overdue book reminders every day at 8 AM",
    )