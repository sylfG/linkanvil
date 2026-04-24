# 🚀 Tutorial Interactivo: Instalación y Configuración

Bienvenidos a la guía práctica para inicializar LinkAnvil, tu backend soberano de conocimiento estructurado. Este tutorial paso a paso está diseñado para instalar la plataforma en local o tu cloud personal, entender el flujo de datos y enviar tu primer enlace de conocimiento para asegurar que todo funciona.

---

## FASE 1: Preparación del Entorno

1. **Obtener y validar las herramientas base**:
   * Asegúrate de contar con Git, una terminal Bash/Zsh o PowerShell.
   * Confirma que cuentas con [Docker y Docker Compose V2](https://docs.docker.com/compose/) instalado ejecutando:

     ```bash
     docker compose version
     ```

   * Si no devuelve un error y la versión es superior a la 2.22, estás listo.

2. **Clonar y Analizar la Raíz**:
   * Accede al directorio `linkanvil` (`cd linkanvil`)
   * Verás varias carpetas como `/infra`, donde residen las configuraciones de cada uno de los contenedores Docker locales (Traefik, Redis, Grafana, PostgreSQL, LiteLLM, Qdrant).

---

## FASE 2: Tokens de Inteligencia Artificial y `.env`

El corazón de extracción y vectorización de URLs funciona gracias a nuestro enrutador **LiteLLM**. Necesitaremos proporcionar credenciales seguras.

1. Copia nuestra plantilla a tu fichero local secreto (recuerda que este fichero NUNCA debe subirse a un repositorio público):

   ```bash
   cp .env.example .env
   ```

2. Edita `.env` con un editor como Nano, Vim o VS Code:
   * **Variables de API (*CRÍTICAS*)**: Proporciona la llave de OpenRouter. En `infra/litellm/config.yaml` se pueden configurar otras, pero la plantilla general exige:

     ```env
     OPENROUTER_API_KEY=sk-or-xxxxxx...
     ```

   * **Contraseña del Gateway Local**: Necesitas una llave tuya propia que protegerá cualquier llamada interna. Por defecto es `sk-cerebro-master-key`, pero es muy recomendable cambiarla por seguridad (y usar la nueva en todas las peticiones).

     ```env
     LITELLM_MASTER_KEY=sk-tullave-privada-y-segura
     ```

   * **Contraseñas del resto del Stack**: Modifica a placer las contraseñas predefinidas en el fichero de las bases de datos (RabbitMQ, Postgre, Redis, Grafana...).

     ```env
     POSTGRES_PASSWORD=cerebro_db_pass
     RABBITMQ_PASS=cerebro_pass
     # ...
     ```

---

## FASE 3: Despliegue e Inicialización (Bootstrapping)

Ahora que las llaves están configuradas, instruiremos a Docker Compose que descargue las imágenes, cree las redes (red interna invisible que solo pueden hablar los contenedores entre sí) y aplique los init scripts (como la recreación de tablas relacionales en `init.sql`).

```bash
docker compose up -d
```

> **NOTA:** Tardará varios minutos dependiendo de tu ancho de banda ya que se han de descargar orquestadores, la BD Vectorial (Qdrant) y la cola de mensajería (RabbitMQ). Puedes chequear los logs de todos ellos a la vez lanzando `docker compose logs -f`.

---

## FASE 4: Verificación Integral del Ecosistema

LinkAnvil posee un script inteligente oficial escrito en Python que simula ser un flujo de datos y prueba la disponibilidad, la inserción relacional, las políticas RLS y las colas de fallos.

1. Confirma que tienes Python en el sistema.
2. Ejecuta el test integral:

   ```bash
   python infra/test_health.py
   ```

3. Cada validación (Conexión LLM, Creación de Colección Vectorial de Qdrant, Exchange AMQP) debe reportar un **OK** color verde. Si notas que la base de datos reporta un error de puerto o conexión "rechazada", a veces se debe a que PostgreSQL todavía tardará unos segundos extra en inicializar la Base de datos en vacío la primera vez. Vuelve a ejecutar el check.

---

## FASE 5: Prueba Manual y Dashboards UI

¡Si estás aquí, la instalación ha concluido con éxito! La mejor forma de visualizar que los logs de telemetría y Traefik funcionan es navegando por los paneles expuestos:

| Dashboard y URL Directa | Puerto  | Credenciales Configurable en tu `.env` |
|:--- |:--- |:--- |
| **Orquestador (n8n)** | [http://localhost:5678](http://localhost:5678) | `N8N_USER` & `N8N_PASSWORD` |
| **Colas (RabbitMQ)** | [http://localhost:15672](http://localhost:15672) | `RABBITMQ_USER` & `RABBITMQ_PASS` |
| **Métricas (Grafana)** | [http://localhost:3000](http://localhost:3000) | `GRAFANA_USER` & `GRAFANA_PASSWORD` |
| **Trazas Visuales (Jaeger)**| [http://localhost:16686](http://localhost:16686) | Libre |
| **BD Vectorial (Qdrant)** | [http://localhost:6333/dashboard](http://localhost:6333/dashboard) | Libre |

***Tip Pro***: Como Traefik está como Gateway proxy, puedes editar las redirecciones oportunas en tu fichero anfitrión local (`/etc/hosts` o de Windows) para acceder a subdominios como *`n8n.localhost`*, resultando en un acceso limpio y centralizado.

### Tu primera ingesta

Puedes probar que RabbitMQ encola URLs correctas si ejecutas desde el terminal principal `n8n` para arrancar un web-hook, o enviando un payload REST post directamente simulando la lectura.

```bash
docker exec -it cerebro-rabbitmq rabbitmqadmin publish exchange=amq.default routing_key="q.url.ingesta" payload='{"url":"https://vitepress.dev/"}'
```

*¡Felicidades! LinkAnvil ya forma parte de tu ecosistema.* Avanza con las integraciones manuales de Telegram o los scrapers modulares de Python en tu [Siguiente Sección de la Documentación](./0_0_resumen.md).
