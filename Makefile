# define the name of the virtual environment directory
VENV := .venv
MIGRATION ?= 0001

# default target, when make executed without arguments
all: venv

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV)
	./$(VENV)/bin/python3.12 -m pip install --upgrade pip
	./$(VENV)/bin/pip3.12 install -r requirements.txt

# venv is a shortcut target
venv: $(VENV)/bin/activate

run: venv
	./$(VENV)/bin/python3.12 manage.py runserver 9100

make_migrations: venv
	./$(VENV)/bin/python3.12 manage.py makemigrations
	./$(VENV)/bin/python3.12 manage.py sqlmigrate documents 0001  # change this
	./$(VENV)/bin/python3.12 manage.py migrate

migrate: venv
	./$(VENV)/bin/python3.12 manage.py migrate --run-syncdb

createsuperuser: venv
	./$(VENV)/bin/python3.12 manage.py createsuperuser
# mrommel + 0IsL7F594nyxYqEL
