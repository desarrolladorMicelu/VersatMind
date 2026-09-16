# Mind by Versat

Agente de IA conversacional para miembros de juntas directivas. Se comunica por Telegram, consulta datos empresariales, genera informes PDF/Excel y gestiona tareas programadas.

## Requisitos

- Python 3.12+
- Docker y Docker Compose
- Token de Telegram Bot (obtener via [@BotFather](https://t.me/BotFather))
- API Key de OpenAI
- URL pública con HTTPS (Railway, ngrok, etc.)

## Configuración rápida

### 1. Clonar y configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus valores reales
```

### 2. Variables de entorno requeridas

| Variable | Descripción |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token del bot (de @BotFather) |
| `TELEGRAM_WEBHOOK_URL` | URL pública del servicio (ej: `https://tu-app.railway.app`) |
| `OPENAI_API_KEY` | API key de OpenAI |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` |
| `DATABASE_URL_SYNC` | `postgresql://user:pass@host:5432/db` |

### 3. Ejecutar localmente con Docker

```bash
docker-compose up
```

### 4. Inicializar base de datos y crear usuario admin

```bash
# Con Docker Compose corriendo:
DATABASE_URL_SYNC=postgresql://mind:mind_dev_password@localhost:5432/mind_db \
ADMIN_CHAT_ID=TU_CHAT_ID \
ADMIN_USER_ID=TU_USER_ID \
python scripts/seed_initial_data.py
```

> **Tip**: Para obtener tu `chat_id`, envía `/start` al bot [@userinfobot](https://t.me/userinfobot) en Telegram.

## Despliegue en Railway

1. Conecta este repositorio a Railway
2. Agrega el servicio PostgreSQL de Railway
3. Configura las variables de entorno en Railway
4. Railway detecta automáticamente el `Dockerfile` y el `railway.toml`
5. El health check está en `/health`

## Estructura del proyecto

```
mind/
├── main.py              # FastAPI app (webhook + health check)
├── config.py            # Variables de entorno (pydantic-settings)
├── agent/
│   ├── orchestrator.py  # Loop LLM con tool-calling
│   ├── context.py       # Historial de conversación
│   └── tools/           # Herramientas: datos, informes, scheduler
├── auth/                # Autorización (whitelist + roles)
├── audit/               # Registro de auditoría
├── data/                # Conectores de datos (solo lectura)
├── reports/             # Generador PDF/Excel
├── scheduler/           # APScheduler con PostgreSQL
└── telegram/            # Bot handler y webhook
alembic/                 # Migraciones de base de datos
scripts/                 # Utilidades de administración
tests/                   # Tests unitarios y de integración
```

## Ejemplos de uso

Una vez que el bot está corriendo, envíale mensajes en Telegram:

- `"¿Cómo estuvieron las ventas este mes?"`
- `"Genera el informe financiero del último trimestre en PDF"`
- `"¿Cuáles indicadores están por debajo del objetivo?"`
- `"Recuérdame enviarme el informe todos los lunes a las 8 AM"`
- `"Lista mis tareas programadas"`
- `"Elimina la tarea abc-123"`

## Licencia

Privado — Versat
