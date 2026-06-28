from celery import Celery

app = Celery('chromavec', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'