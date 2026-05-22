COMPOSE := docker compose -f docker-compose.yml

# Servicios "one-shot" — terminan en Exited(0) por diseño tras hacer su trabajo.
# Se excluyen del listado por defecto para reducir ruido visual.
ONE_SHOT := cerebro-migrate qdrant-init cerebro-seed-demo bootstrap-demo-keys n8n-bootstrap

.PHONY: ps ps-all ps-oneshot up down restart logs health

# Listado limpio: solo servicios runtime (oculta init containers terminados)
ps:
	@$(COMPOSE) ps $(filter-out $(ONE_SHOT),$(shell $(COMPOSE) config --services))

# Listado completo (incluye one-shot Exited)
ps-all:
	@$(COMPOSE) ps -a

# Estado de los init containers
ps-oneshot:
	@$(COMPOSE) ps -a $(ONE_SHOT)

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart $(SERVICE)

logs:
	$(COMPOSE) logs -f --tail=100 $(SERVICE)

# Resumen rápido del health de servicios runtime
health:
	@$(COMPOSE) ps --format 'table {{.Name}}\t{{.Status}}' | grep -v 'Exited'
