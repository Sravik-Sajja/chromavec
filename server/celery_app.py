import os
from celery import Celery
from celery.signals import worker_process_init

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

app = Celery('chromavec', broker=REDIS_URL, backend=REDIS_URL)
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'
app.conf.imports = ('tasks',)

@worker_process_init.connect
def reset_clients(**kwargs):
    from methods import database, snapshots
    database.reset_index()
    snapshots.init_db()