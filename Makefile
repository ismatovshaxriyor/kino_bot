# KinoBot — docker compose qisqa buyruqlari.
# Misol:  make up | make logs | make init-db | make deploy
#
# Eslatma: recipe satrlari TAB bilan boshlanadi (Makefile talabi).

COMPOSE = docker compose
APP = $(COMPOSE) --profile app

.PHONY: help build up up-infra down stop start restart logs ps init-db migrate upgrade backup shell deploy

help:
	@echo "make build     - image'ni yig'ish"
	@echo "make up        - hammasini ishga tushirish (redis+db+bot+worker)"
	@echo "make up-infra  - faqat redis + db (lokal dev uchun)"
	@echo "make down      - hammasini to'xtatish (volume'lar saqlanadi)"
	@echo "make restart   - bot + worker'ni qayta ishga tushirish"
	@echo "make logs      - bot + worker loglari (jonli)"
	@echo "make ps        - konteynerlar holati"
	@echo "make init-db   - YANGI bo'sh bazada jadvallarni yaratish (faqat 1-marta)"
	@echo "make migrate m=desc - model o'zgarishidan keyin migratsiya yaratish"
	@echo "make upgrade   - migratsiyalarni qo'llash"
	@echo "make backup    - host'ga qo'lda SQL backup (backups/ papkaga)"
	@echo "make shell     - bot konteynerida bash"
	@echo "make deploy    - git pull + qayta yig'ish + qayta ishga tushirish"

build:
	$(APP) build

up:
	$(APP) up -d --build

up-infra:
	$(COMPOSE) up -d redis db

down:
	$(APP) down

stop:
	$(APP) stop

start:
	$(APP) start

restart:
	$(APP) restart bot worker

logs:
	$(APP) logs -f --tail=100 bot worker

ps:
	$(APP) ps

init-db:
	$(COMPOSE) run --rm bot aerich init-db

migrate:
	$(COMPOSE) run --rm bot aerich migrate --name "$(m)"

upgrade:
	$(COMPOSE) run --rm bot aerich upgrade

backup:
	@mkdir -p backups
	$(COMPOSE) exec -T db sh -c 'pg_dump -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" --no-owner --no-privileges' \
		| gzip > "backups/kino_$(shell date +%Y%m%d_%H%M%S).sql.gz"
	@echo "✅ Backup saqlandi: backups/ papkasini tekshiring"

shell:
	$(COMPOSE) exec bot bash

deploy:
	git pull --ff-only
	$(APP) up -d --build
	$(APP) ps
