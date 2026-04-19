# ⚙️ Instalación y Configuración

Esta guía te detallará los pasos para configurar, descargar, e iniciar el stack de los servicios en un entorno local mediante Docker Compose.

## 1. Prerrequisitos

* [Docker Desktop](https://www.docker.com/products/docker-desktop/) ≥ 4.25 (con Docker Compose v2)
* **Recursos recomendados**: 8 a 12 GB de RAM dedicados a Docker (dado que se levantan varios servicios Java, bases de datos vectoriales y mensajería).
* **Puertos Disponibles**:
  * HTTP/Gateway: `80`, `8080` (Traefik)
  * Dashboards UI: `3000` (Grafana), `5678` (n8n), `6333` (Qdrant), `9090` (Prometheus), `15672` (RabbitMQ), `16686` (Jaeger)
  * Servicios Internos: `4000` (LiteLLM), `5432` (PostgreSQL), `5672` (RabbitMQ AMQP), `6379` (Redis), `4317-4318` (OTel)

## 2. APIs y Variables de Entorno

El sistema necesita poder contactar con varios LLMs en caso de que un proveedor falle, esto está cubierto con **LiteLLM**. Existen otros servicios que requieren configuraciones de administración local.
Todo esto se maneja desde el archivo principal de entorno de variables oculto desde su plantilla.

```bash
# Paso 1: Crea el archivo de entorno basado en la plantilla:
cp .env.example .env
```

### Configuración de Secretos

Es **absolutamente necesario** definir o revisar las variables clave en tu fichero `.env`:

#### A. APIs de Inteligencia Artificial

Estas APIs se proveen al gateway LiteLLM. Puedes configurar tantas como necesites en `infra/litellm/config.yaml`, pero mínimamente sugerimos:

```env
# Llaves de Proveedores Externos
OPENAI_API_KEY=sk-proj-xxxxxx...
ANTHROPIC_API_KEY=sk-ant-xxxxxx...

# Llave Interna Masteria
# Cualquier petición que enviemos a nuestro gateway deberá usar está llave.
LITELLM_MASTER_KEY=sk-cerebro-master-key
```

#### B. Credenciales Locales e Infraestructura

*Recomendadas para desarrollo local de la BD y dashboards (pueden venir con un valor predeterminado seguro en desarrollo).*

```env
# Bases de datos y Brokers
POSTGRES_USER=cerebro
POSTGRES_PASSWORD=cerebro_db_pass
POSTGRES_DB=cerebro_brain

REDIS_PASSWORD=cerebro_redis_pass

RABBITMQ_USER=cerebro
RABBITMQ_PASS=cerebro_pass
RABBITMQ_VHOST=/

# Administración de Interfaces de Usuario
N8N_USER=admin
N8N_PASSWORD=cerebro_n8n_pass

GRAFANA_USER=admin
GRAFANA_PASSWORD=cerebro_grafana_pass
```

## 3. Preparando e Inicializando la Infraestructura

Una vez dispongas de tu `.env` completado, podrás levantar todo el cluster.

### Levantando el clúster

Ejecuta el siguiente comando en la raíz del proyecto para descargar e iniciar la capa orquestada (los contenedores se descargan e instancian entre 2 y 4 minutos dependiendo de la conexión):

```bash
docker compose up -d
```

### Comprobado Logs y Status

```bash
# Ver los contenedores desplegados
docker compose ps

# Si quieres ver qué está haciendo el workflow u otro gateway
docker compose logs -f n8n
docker compose logs -f litellm
```

## 4. Ejecución del Health Check 🩺

Se dispone de un script centralizado hecho en Python (`test_health.py`) diseñado para la verificación e introspección de todos los conectores. Nos dirá si todos los contenedores arrancaron de forma correcta.

```bash
# Requiere Python 3.9+
python infra/test_health.py
```

El log validará:

* Disponibilidad y códigos HTTP (200 OK correspondientes).
* Migración y esquemas de BD aplicados en PostgreSQL en el init (`init.sql`).
* Existencia de exchanges y encolamientos listos en Rabbit (`definitions.json`).
* Si todo está en verde tu **Segundo Cerebro** es operacional!

## 5. Accediendo al Frontend de tus Servicios

Si la inicialización y el script completaron con éxito, tendrás a nivel local las siguientes rutas e interfaces a interactuar:

| Servicio / Dashboard | Endpoint Interno | Credenciales Requeridas |
|---|---|---|
| **API Gateway - Traefik** | `http://localhost:8080/dashboard/` | Ninguna |
| **Broker MQ - RabbitMQ** | `http://localhost:15672` | `RABBITMQ_USER` / `RABBITMQ_PASS` |
| **Vector DB - Qdrant** | `http://localhost:6333/dashboard` | Ninguna |
| **Observability - Jaeger**| `http://localhost:16686` | Ninguna |
| **Observability - Grafana**| `http://localhost:3000` | `GRAFANA_USER` / `GRAFANA_PASSWORD` |
| **Workflows - n8n** | `http://localhost:5678` | `N8N_USER` / `N8N_PASSWORD` |

*Opcional*: Si añades las redirecciones oportunas a tu `/etc/hosts` nativo para resolver las direcciones en modo clúster (Ej: `127.0.0.1  traefik.localhost n8n.localhost rabbitmq.localhost`), utilizarás la funcionalidad DNS del gateway Traefik y todo será más fácil bajo estos subdominios.
