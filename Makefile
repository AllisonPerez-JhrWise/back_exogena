# ════════════════════════════════════════════════════════════════════════
#  Atajos del proyecto. Escribe `make` (o `make help`) para ver la lista.
#  Funciona desde PowerShell o Git Bash (ver docs/GUIA_LOCAL.md).
# ════════════════════════════════════════════════════════════════════════

.DEFAULT_GOAL := help

YELLOW := \033[1;33m
GREEN  := \033[1;32m
RED    := \033[1;31m
BOLD   := \033[1m
RESET  := \033[0m

# Rutas del entorno virtual de Python: cambian entre Windows y Linux/macOS
ifeq ($(OS),Windows_NT)
  VENV_BIN := .venv/Scripts
  PYTHON   := py
  # Los atajos usan comandos de Linux (sh, sed, cp…). Git para Windows los trae en
  # <Git>/usr/bin: se agregan al PATH para que make funcione también desde PowerShell.
  GIT_USR_BIN := $(subst /mingw64/libexec/git-core,/usr/bin,$(shell git --exec-path))
  export PATH := $(GIT_USR_BIN);$(PATH)
  SHELL := sh.exe
else
  VENV_BIN := .venv/bin
  PYTHON   := python3
endif

COMPOSE_TEST := docker compose -f docker-compose.test.yml

# OJO: los mensajes que imprimen los comandos (printf) van sin tildes ni simbolos:
# en Windows, make le pasa cada comando a sh con la codificacion antigua y se dañan.

.PHONY: help up down restart status logs shell psql reset migrate migration db-check \
        seed aws-status aws-sql aws-migrate aws-seed-catalog db-sync-cloud test venv test-unit lint format clean check-docker

help: ## Muestra los comandos disponibles
	@printf "\n$(BOLD)Comandos disponibles$(RESET)  (uso: make <comando>)\n"
	@awk 'BEGIN {FS = ":.*?## "} \
	  /^##@ / {sub(/^##@ /, ""); printf "\n$(YELLOW)%s$(RESET)\n", $$0; next} \
	  /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-12s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf "\n"

##@ Día a día

up: check-docker .env ## Enciende TODO: app + base de datos + migraciones
	docker compose up -d --build --wait
	docker compose exec app alembic upgrade head
	@printf "\n$(GREEN)OK - Todo encendido y listo$(RESET)\n"
	@printf "  API:           http://localhost:8000\n"
	@printf "  Documentacion: http://localhost:8000/docs\n"
	@printf "  Ver logs:      make logs      Apagar: make down\n\n"

down: ## Apaga todo (los datos de la base local se conservan)
	docker compose down

restart: ## Reinicia la app (si un cambio de código no se reflejó)
	docker compose restart app

status: ## Muestra qué está encendido
	docker compose ps

logs: ## Muestra los logs de la app en vivo (Ctrl+C para salir)
	docker compose logs -f app

shell: ## Abre una terminal dentro del contenedor de la app
	docker compose exec app bash

psql: ## Abre la consola SQL de la base de datos local
	docker compose exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

reset: check-docker ## ⚠ Borra la base de datos LOCAL y enciende todo de cero
	@printf "$(RED)Esto borra todos los datos de la base de datos local.$(RESET) Continuar? [s/N] "; \
	  read ans; ans=$$(printf '%s' "$$ans" | tr -cd 'a-zA-Z'); \
	  if [ "$$ans" = "s" ] || [ "$$ans" = "S" ]; then \
	    docker compose down -v && "$(MAKE)" --no-print-directory up; \
	  else \
	    echo "Cancelado. No se borro nada."; \
	  fi

##@ Base de datos

migrate: ## Aplica las migraciones pendientes
	docker compose exec app alembic upgrade head

migration: ## Crea una migración nueva. Uso: make migration m="agregar terceros"
	@if [ -z "$(m)" ]; then printf "$(YELLOW)Uso: make migration m=\"descripcion\"$(RESET)\n"; exit 1; fi
	docker compose exec app alembic revision --autogenerate -m "$(m)"
	@printf "$(YELLOW)Revisa el archivo creado en alembic/versions/ y luego ejecuta: make migrate$(RESET)\n"

db-check: ## Verifica que los modelos y las migraciones coincidan
	docker compose exec app alembic check

seed: ## Base LOCAL lista para probar: firma, administrador, catalogo y token para /docs
	docker compose exec app python -m scripts.seed_local

##@ AWS (usa .env.aws)

# Misma imagen de la app, pero con la conexión de .env.aws. MSYS_NO_PATHCONV evita que
# Git Bash en Windows convierta /app en una ruta de Windows.
# AUTH_BYPASS=false: el .env local (montado con el código) lo tiene encendido para pruebas
AWS_RUN := MSYS_NO_PATHCONV=1 docker run --rm --env-file .env.aws -e PYTHONPATH=/app \
  -e AUTH_BYPASS=false -v "$(CURDIR):/app" -w /app back-exogena
AWS_ALEMBIC := $(AWS_RUN) alembic
DB_INIT := docker/db-init

aws-status: check-docker .env.aws ## Solo lectura: qué migración tiene la base de AWS
	$(AWS_ALEMBIC) current

aws-sql: check-docker .env.aws ## Solo lectura: muestra el SQL que se ejecutaría en AWS
	$(AWS_ALEMBIC) upgrade head --sql

aws-migrate: check-docker .env.aws ## ⚠ Aplica las migraciones en la base de AWS (pide confirmación)
	@printf "$(RED)Esto modifica la base de datos de AWS.$(RESET) Continuar? [s/N] "; \
	  read ans; ans=$$(printf '%s' "$$ans" | tr -cd 'a-zA-Z'); \
	  if [ "$$ans" = "s" ] || [ "$$ans" = "S" ]; then \
	    $(AWS_ALEMBIC) upgrade head; \
	  else \
	    echo "Cancelado. No se aplico nada."; \
	  fi

aws-seed-catalog: check-docker .env.aws ## ⚠ Carga el catalogo inicial en AWS. Uso: make aws-seed-catalog tenant=<uuid>
	@if [ -z "$(tenant)" ]; then printf "$(YELLOW)Uso: make aws-seed-catalog tenant=<uuid de la firma>$(RESET)\n"; exit 1; fi
	@printf "$(RED)Esto escribe en la base de datos de AWS (tenant $(tenant)).$(RESET) Continuar? [s/N] "; \
	  read ans; ans=$$(printf '%s' "$$ans" | tr -cd 'a-zA-Z'); \
	  if [ "$$ans" = "s" ] || [ "$$ans" = "S" ]; then \
	    $(AWS_RUN) python -m scripts.seed_catalog --tenant-id $(tenant); \
	  else \
	    echo "Cancelado. No se cargo nada."; \
	  fi

db-sync-cloud: check-docker .env.aws ## Solo lectura: copia de AWS la estructura de public y los catalogos
	@url=$$(grep '^DATABASE_URL=' .env.aws | cut -d= -f2- | sed 's/+asyncpg//'); \
	  MSYS_NO_PATHCONV=1 docker run --rm -e PGSSLMODE=require -e "URL=$$url" postgres:18 \
	    sh -c 'pg_dump "$$URL" --schema-only --schema=public --exclude-table=public.alembic_version_exogena' \
	    > $(DB_INIT)/.plataforma.tmp
	@{ printf '%s\n' \
	    "-- Estructura del schema public de la plataforma, copiada de la RDS (wiseerp)." \
	    "-- NO se edita a mano: la maneja el servicio de plataforma con su propio Alembic." \
	    "-- Para actualizarla: make db-sync-cloud (requiere .env.aws)" ""; \
	  sed -e '/^.restrict [A-Za-z0-9]*$$/d' -e '/^.unrestrict [A-Za-z0-9]*$$/d' \
	    -e '/^CREATE SCHEMA public;$$/d' $(DB_INIT)/.plataforma.tmp; \
	  } > $(DB_INIT)/10_plataforma.sql && rm $(DB_INIT)/.plataforma.tmp
	$(AWS_RUN) python scripts/cloud_catalogs.py > $(DB_INIT)/.catalogos.tmp
	@mv $(DB_INIT)/.catalogos.tmp $(DB_INIT)/20_catalogos.sql
	@printf "$(GREEN)OK - Copiado. Revisa los cambios con git diff $(DB_INIT) y aplica con: make reset$(RESET)\n"

##@ Pruebas y calidad

test: check-docker ## Corre TODAS las pruebas en Docker, con una base desechable
	$(COMPOSE_TEST) run --rm --build app_test; \
	  status=$$?; $(COMPOSE_TEST) down -v; exit $$status

venv: ## Crea el entorno de Python local (.venv) para el editor, ruff y pytest
	$(PYTHON) -m venv .venv
	$(VENV_BIN)/python -m pip install --upgrade pip
	$(VENV_BIN)/pip install -r requirements/dev.txt -r requirements/test.txt
	$(VENV_BIN)/pre-commit install

test-unit: ## Pruebas unitarias con el .venv local (no necesita Docker)
	$(VENV_BIN)/pytest -m "not integration"

lint: ## Revisa el estilo del código con ruff
	$(VENV_BIN)/ruff check .
	$(VENV_BIN)/ruff format --check .

format: ## Formatea y corrige el estilo automáticamente
	$(VENV_BIN)/ruff check --fix .
	$(VENV_BIN)/ruff format .

clean: ## Borra archivos temporales (cachés de Python)
	find . -type d \( -name "__pycache__" -o -name ".pytest_cache" -o -name ".ruff_cache" \) -prune -exec rm -rf {} +

# ── Pasos internos (no aparecen en la ayuda) ─────────────────────────────

# Falla con un mensaje claro si Docker Desktop no está encendido
check-docker:
	@docker info >/dev/null 2>&1 || { \
	  printf "$(RED)ERROR - Docker no esta encendido.$(RESET) Abre Docker Desktop y espera a que diga 'Engine running'.\n"; \
	  exit 1; }

# Crea el .env la primera vez, con un JWT_SECRET aleatorio (solo si no existe)
.env:
	@cp .env_example .env
	@secret=$$(od -An -tx1 -N32 /dev/urandom | tr -d ' \n') && \
	  sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$$secret/" .env
	@printf "$(GREEN)OK - Se creo .env con un JWT_SECRET nuevo$(RESET) (no se sube a git)\n"

# Los comandos aws-* necesitan .env.aws con la conexión a RDS (no se sube a git)
.env.aws:
	@printf "$(RED)ERROR - Falta el archivo .env.aws.$(RESET) Crealo con DATABASE_URL (postgresql+asyncpg://...),\n"
	@printf "DB_SSL_MODE=require, ENVIRONMENT=production, COOKIE_SECURE=true y JWT_SECRET.\n"
	@exit 1
