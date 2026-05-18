<div align="center">
  <img src="/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# Visión General del Proyecto: "LinkAnvil"

</div>

## Documentación Oficial del Proyecto: LinkAnvil

---

## Tabla de contenidos

1. [Visión General del Proyecto](#visión-general-del-proyecto)
2. [Estructura y Módulos del Sistema](#estructura-y-módulos-del-sistema)
3. [Flujo de Funcionamiento Práctico (El Viaje del Dato)](#flujo-de-funcionamiento-práctico-el-viaje-del-dato)
4. [Infraestructura y Mecanismos de Protección](#infraestructura-y-mecanismos-de-protección)

---

## Visión General del Proyecto

El proyecto **LinkAnvil** es una plataforma diseñada para organizar información digital dispersa y transformarla en conocimiento útil y estructurado. El sistema permite a los usuarios guardar enlaces, artículos o publicaciones para luego interactuar con ellos mediante un chat inteligente, generar contenido nuevo (como tutoriales o resúmenes) y realizar búsquedas avanzadas en tiempo real.

### Características Principales

* **Organización Automatizada:** Clasifica y resume el contenido guardado sin intervención del usuario.
* **Asistente Virtual Inteligente:** Permite "dialogar" con la base de conocimientos guardada para resolver dudas o redactar documentos.
* **Eficiencia en Costes:** Utiliza filtros inteligentes para evitar procesar la misma información varias veces, reduciendo el consumo de recursos.
* **Seguridad Avanzada:** Protege la privacidad de los datos de cada usuario y previene ataques informáticos comunes.

---

## Estructura y Módulos del Sistema

El sistema está dividido en cinco componentes independientes que trabajan en equipo de forma ordenada.

### A. Módulo de Ingesta y Captura (El Recolector)

Es la puerta de entrada de la información al sistema. Los usuarios pueden enviar enlaces a través de extensiones de navegador, un bot de Telegram o conexiones automáticas (*webhooks*).

1. **Filtro de Entrada:** Cuando un usuario envía un enlace, el sistema limpia la dirección web (eliminando códigos de rastreo innecesarios).
2. **Verificación de Duplicados:** El sistema comprueba al instante si el enlace ya existe en la base de datos general.
* Si el enlace ya se había registrado antes, se reutiliza la información existente para ahorrar energía y costes.
* Si es un enlace nuevo, se envía a una lista de espera (cola de mensajes) para ser procesado sin retrasar la navegación del usuario.


3. **Extracción Flexible de Contenido:** Un extractor automático analiza la página web para leer su texto. Si la página cuenta con protecciones antibots o bloqueos avanzados (como LinkedIn o X), el sistema activa de forma automática herramientas especiales que simulan una navegación humana para asegurar la lectura del contenido.

### B. Motor de Procesamiento (El Analista)

Este módulo se encarga de entender el texto extraído utilizando Inteligencia Artificial (IA).

* **Conexión Inteligente y de Respaldo:** El sistema no depende de un único proveedor de IA. Si el servicio principal (por ejemplo, OpenAI) falla, el sistema se conecta automáticamente a un servicio secundario sin que el usuario note la interrupción.
* **Formato de Datos Estricto:** Se obliga a la IA a entregar las respuestas en una estructura rígida y organizada que contiene:
* **Clasificación:** Categoría principal y etiquetas del tema.
* **Resumen:** Una síntesis breve y clara del texto.
* **Fecha de Caducidad Estimada:** Un cálculo de cuánto tiempo seguirá siendo útil o vigente esa información (por ejemplo, se usaría para detectar url de eventos que ya han pasado, promociones que ya no estan vigentes, etc.).



### C. Almacenamiento Multicapa (La Memoria)

Una vez procesada la información, se guarda de forma segura en tres niveles distintos:

* **Base de Datos Relacional:** Funciona como el libro de registro principal, asegurando que los metadatos y el estado de la información sean exactos y no se pierdan.
* **Base de Datos Vectorial:** Transforma las ideas en valores matemáticos para buscar conexiones. Si el sistema detecta que un enlace nuevo comparte un tema muy similar con otro guardado hace meses, crea un puente de conocimiento de forma automática, ayudando al usuario a descubrir relaciones ocultas entre sus datos.
* **Exportación para Uso Local:** El sistema permite descargar todo el conocimiento acumulado en archivos de texto estructurados. Estos archivos son totalmente compatibles con herramientas de notas locales (como Obsidian o Cursor) y permiten ver las conexiones de las ideas de forma visual, incluso sin conexión a Internet.
> **Nota de Seguridad:** Este proceso de descarga se genera directamente en la memoria volátil del servidor (RAM). No se guardan archivos temporales en el disco, evitando cualquier riesgo de fuga de datos entre usuarios.



### D. Agente de Mantenimiento (El Curador Nocturno)

Para evitar que el sistema se vuelva lento o costoso debido a la acumulación de información antigua, un proceso automático revisa el contenido periódicamente.

1. **Revisión Económica:** El sistema realiza una búsqueda rápida en la base de datos para identificar textos cuya fecha de caducidad estimada haya vencido. Este paso no consume recursos de IA.
2. **Evaluación Especializada:** Solo si el usuario lo solicita expresamente, la IA analizará a fondo el contenido para determinar si sigue siendo técnicamente relevante.
3. **Bandeja de Cuarentena:** La información obsoleta no se elimina de inmediato; se traslada a una carpeta de "Archivados" o "Caducados" para su revisión final.

### E. Interfaz y Chatbot (El Asistente Personal)

Es la pantalla y el canal de comunicación con el usuario. Está formado por un panel de control visual y un chat interactivo.

* **Panel de Control:** Permite ver estadísticas, consultar los enlaces guardados y revisar el historial de conversaciones.
* **Chat Fluido:** Las respuestas de la IA se muestran palabra por palabra en tiempo real (mientras se van generando). El historial de conversación se guarda de forma segura en el servidor, permitiendo continuar la charla desde cualquier dispositivo (móvil, tablet u ordenador) sin perder información.
* **Seguridad de Acceso:** El inicio de sesión utiliza cookies ultra-protegidas que los virus informáticos comunes no pueden leer del navegador, y cuenta con un límite de intentos para bloquear accesos no autorizados.

---

## Flujo de Funcionamiento Práctico (El Viaje del Dato)

A continuación se detalla cómo viaja la información a través del sistema en el día a día:

```
[Usuario envía enlace vía Telegram] 
               │
               ▼
   [Módulo A: Limpieza y Filtro] ── (Si ya existe) ──► [Reutilizar datos]
               │
          (Si es nuevo)
               │
               ▼
 [Módulo B: Análisis e Inteligencia Artificial]
               │
               ▼
 [Módulo C: Almacenamiento en Base de Datos y Enlaces de Ideas]
               │
               ▼
 [Módulo E: Consulta en el Chatbot / Creación de Tutoriales]
               │
               ▼
 [Módulo D: Limpieza Nocturna de Datos Obsoletos]

```

1. **Captura:** El usuario encuentra un enlace de interés en su móvil (por ejemplo, en X) y lo reenvía al bot de Telegram del proyecto.
2. **Confirmación:** El bot responde de inmediato que ha recibido el enlace de forma segura, permitiendo al usuario seguir con sus actividades.
3. **Procesamiento:** En segundo plano, el sistema extrae el texto, la IA lo resume y le asigna una fecha de vigencia estimada.
4. **Guardado:** La información se registra en las bases de datos y se conecta automáticamente con otros temas relacionados guardados en el pasado.
5. **Consulta:** Días después, el usuario abre la aplicación web y solicita: *"Redacta un tutorial basado en los enlaces que guardé el lunes"*. El sistema busca los documentos y genera el texto.
6. **Actualización:** Semanas más tarde, el usuario puede pedir modificaciones sobre ese mismo tutorial desde Telegram; el sistema recordará el contexto de la conversación anterior y aplicará los cambios.
7. **Depuración:** Pasado un tiempo, el asistente nocturno detecta los enlaces antiguos y los agrupa en la sección de cuarentena para que el usuario decida si desea conservarlos o eliminarlos.

---

## Infraestructura y Mecanismos de Protección

Para garantizar un funcionamiento estable y sin caídas, la plataforma cuenta con las siguientes reglas técnicas:

* **Gestión de Enlaces Rotos:** Si el sistema intenta leer un enlace que no existe o está caído, lo reintenta 3 veces. Si sigue fallando, lo envía a una lista de errores y notifica al usuario: *"El enlace que intentaste guardar ya no está disponible"*, evitando gastar recursos innecesarios.
* **Privacidad Total (Multi-Inquilino):** Los datos de cada usuario están estrictamente separados mediante etiquetas y llaves de seguridad únicas. Es técnicamente imposible que un usuario pueda ver o buscar en la información de otra persona.
* **Control de Consumo de Memoria:** Si un usuario no utiliza su sesión de chat durante 30 días, el sistema la traslada de la memoria rápida al almacenamiento a largo plazo para liberar espacio en el servidor. Si el usuario vuelve a escribir, la sesión se recarga en un instante.
* **Protección contra Abusos:** Si un usuario realiza miles de búsquedas o peticiones de forma exagerada y simultánea, el sistema limitará su velocidad de respuesta temporalmente. Esto evita que un solo usuario ralentice la plataforma para los demás.
* **Rastreo de Errores en Cascada:** Cada enlace guardado recibe un código de identificación único. Si ocurre un fallo en cualquier punto del recorrido, los ingenieros pueden localizar exactamente en qué paso se detuvo el proceso usando ese código.

