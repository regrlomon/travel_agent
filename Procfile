web:    uvicorn api.main:app --host 0.0.0.0 --port 8000
worker: celery -A worker.celery_app worker --loglevel=info --pool=solo
