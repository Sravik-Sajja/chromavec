from celery import Celery
from celery.signals import worker_process_init

app = Celery('chromavec', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'
app.conf.imports = ('tasks',)

@worker_process_init.connect
def reset_clients(**kwargs):
    from methods import database
    database.reset_index()