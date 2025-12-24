.PHONY: install migrate migrations runserver superuser update install-pre-commit lint develop django-app migration-roll-back production stop-production stop-develop django-shell frontend-build frontend-install frontend-lint docker-clean logs

# Backend Commands
install:
	poetry install --no-root

install-pre-commit:
	poetry run pre-commit uninstall && poetry run pre-commit install

lint:
	poetry run pre-commit run --all-files

lint-backend:
	poetry run black .
	poetry run isort .
	poetry run flake8
	poetry run mypy .

migrate:
	poetry run python -m core.manage migrate

migrations:
	poetry run python -m core.manage makemigrations

runserver:
	poetry run python -m core.manage runserver

runserver-web:
	poetry run daphne -p 8000 -b 0.0.0.0 core.project.asgi:application

superuser:
	poetry run python -m core.manage createsuperuser

develop:
	docker compose -f docker-compose.dev.yml up -d db

clean-develop:
	docker compose -f docker-compose.dev.yml down -v
	docker compose -f docker-compose.dev.yml up -d --force-recreate db

update: install migrate install-pre-commit

django-app:
	@read -p "Enter the name of the app: " appname; \
	poetry run python -m core.manage startapp "$$appname"

migration-roll-back:
	@read -p "Enter the name of the app: " appname; \
	read -p "Enter the migration version: " version; \
	poetry run python -m core.manage migrate "$$appname" "$$version"

# Frontend Commands
frontend-install:
	cd frontend && npm install

frontend-build:
	cd frontend && npm run build

frontend-lint:
	cd frontend && npx eslint . --ext .js,.vue
	cd frontend && npx prettier --check .

frontend-lint-fix:
	cd frontend && npx eslint . --ext .js,.vue --fix
	cd frontend && npx prettier --write .

# Docker Commands
production:
	docker compose up -d --build

stop-production:
	docker compose down

stop-develop:
	docker compose -f docker-compose.dev.yml down

docker-clean:
	docker system prune -f
	docker volume prune -f

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-frontend:
	docker compose logs -f frontend

logs-db:
	docker compose logs -f db

# Full Deployment
deploy: stop-production docker-clean frontend-build production migrate

# Development
django-shell:
	poetry run python -m core.manage shell

# Testing
test:
	poetry run pytest

test-backend:
	poetry run pytest

test-frontend:
	cd frontend && npm test

# Database
db-backup:
	docker compose exec db pg_dump -U fra fra > backup_$(shell date +%Y%m%d_%H%M%S).sql

db-shell:
	docker compose exec db psql -U fra -d fra

# Full linting command
lint-all: lint-backend frontend-lint

# Pre-commit preparation
pre-commit-setup: install-pre-commit frontend-install
