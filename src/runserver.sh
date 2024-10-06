python manage.py collectstatic --no-input
python manage.py migrate
gunicorn SaoMiguelBus.wsgi --bind=0.0.0.0:80
