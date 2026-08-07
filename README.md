# Calendar Agent

Agente de IA en Python que gestiona Google Calendar a través de Telegram. Los usuarios escriben en lenguaje natural y el agente interpreta la intención, ejecuta herramientas y responde.

## Arquitectura

```
ProyectoAgenteCalendar/
├── api/              # Rutas FastAPI (webhook, OAuth, health)
├── agent/            # Agente LangGraph + prompts
├── auth/             # OAuth2 con Google
├── gcalendar/         # Cliente Google Calendar API (renombrado para evitar conflicto con el módulo `calendar` de la stdlib)
├── config/           # Settings (pydantic-settings)
├── database/         # Modelos SQLAlchemy + repositorios
├── telegram/         # Bot Telegram + handler de webhooks
├── tools/            # Herramientas del agente (extensible)
├── scripts/          # Utilidades (setup webhook)
├── main.py           # Entry point FastAPI
├── Dockerfile
└── docker-compose.yml
```

## Stack

| Componente | Tecnología |
|---|---|
| API | FastAPI + Uvicorn |
| Agente | LangGraph + LangChain + Google Gemini |
| Calendario | Google Calendar API |
| Auth | OAuth2 (Google) |
| Base de datos | PostgreSQL + SQLAlchemy async |
| Bot | Telegram Bot API (Webhooks) |
| Contenedores | Docker + Docker Compose |

## Inicio rápido

### 1. Clonar y configurar

```bash
cp .env.example .env
# Editar .env con tus credenciales
```

### 2. Levantar con Docker

```bash
docker compose up --build
```

La API queda disponible en `http://localhost:8000`.

### 3. Configurar credenciales

#### Telegram Bot
1. Crear bot con [@BotFather](https://t.me/BotFather)
2. Copiar el token a `TELEGRAM_BOT_TOKEN`
3. Definir un secret aleatorio en `TELEGRAM_WEBHOOK_SECRET`

#### Google OAuth2
1. Ir a [Google Cloud Console](https://console.cloud.google.com/)
2. Crear proyecto y habilitar **Google Calendar API**
3. Crear credenciales OAuth 2.0 (tipo "Web application")
4. Agregar redirect URI: `https://tu-dominio.com/auth/google/callback`
5. Copiar Client ID y Secret a `.env`

#### Google Gemini
1. Obtener API key gratuita en [Google AI Studio](https://aistudio.google.com/apikey)
2. Copiar a `GEMINI_API_KEY`
3. Modelo recomendado en tier gratuito: `gemini-2.0-flash` o `gemini-1.5-flash`

### 4. Registrar webhook de Telegram

Con la app corriendo y accesible públicamente (HTTPS requerido por Telegram):

```bash
python scripts/setup_webhook.py
```

Para desarrollo local, usá [ngrok](https://ngrok.com/) o similar:

```bash
ngrok http 8000
# Actualizar BASE_URL en .env con la URL de ngrok
python scripts/setup_webhook.py
```

## Flujo de uso

1. Usuario envía `/start` al bot en Telegram
2. El bot responde con un link para conectar Google Calendar
3. Usuario autoriza OAuth2 en el navegador
4. Usuario escribe solicitudes en lenguaje natural:
   - *"Agenda una reunión con Juan mañana a las 15 hs."*
   - *"¿Cuándo estoy libre el viernes?"*
   - *"Reprograma la reunión con Pedro para el lunes."*
5. El agente interpreta, llama herramientas y responde

## Herramientas del agente

| Tool | Descripción |
|---|---|
| `create_meeting` | Crear reunión |
| `list_meetings` | Listar reuniones en un rango |
| `find_free_slots` | Buscar horarios libres |
| `reschedule_meeting` | Reprogramar reunión |
| `cancel_meeting` | Cancelar reunión |

## Agregar nuevas herramientas

1. Crear clase que herede de `BaseAgentTool` en `tools/`:

```python
from tools.base import BaseAgentTool, ToolContext
from pydantic import BaseModel, Field

class MyToolArgs(BaseModel):
    param: str = Field(description="...")

class MyNewTool(BaseAgentTool):
    name = "my_new_tool"
    description = "Descripción para el LLM"

    def get_args_schema(self):
        return MyToolArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        # lógica aquí
        return "Resultado"
```

2. Registrar en `tools/registry.py`:

```python
ALL_TOOLS = [
    # ... herramientas existentes
    MyNewTool,
]
```

El agente las detectará automáticamente.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/telegram/webhook` | Webhook de Telegram |
| GET | `/auth/google/login?telegram_id=X` | Iniciar OAuth |
| GET | `/auth/google/callback` | Callback OAuth |

## Desarrollo local (sin Docker)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# PostgreSQL corriendo localmente
# Actualizar DATABASE_URL en .env

uvicorn main:app --reload
```

## Nota sobre el módulo `gcalendar/`

El directorio se renombró a `gcalendar/` para evitar colisión de nombres con la librería estándar `calendar` de Python, la cual es requerida internamente por librerías como `googleapiclient` y `email.utils`.
