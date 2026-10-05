# Integraciones de correo y calendario (Outlook / Google)

Mind permite vincular cuentas de **Outlook (Microsoft 365)** y **Google (Gmail/Calendar)**
por cliente, para que el agente lea correos, consulte la agenda y genere borradores de
respuesta (no envía correos).

## 0. Generar la clave de cifrado

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copia el resultado en `INTEGRATIONS_ENCRYPTION_KEY`. Si se deja vacío, se deriva de
`ADMIN_SECRET_KEY` (funciona, pero si cambias `ADMIN_SECRET_KEY` habrá que re-vincular
las cuentas).

## 1. Variables de entorno

```env
INTEGRATIONS_BASE_URL=https://web-production-b405d.up.railway.app
INTEGRATIONS_ENCRYPTION_KEY=          # opcional (Fernet key). Si vacío se deriva de ADMIN_SECRET_KEY

MS_CLIENT_ID=...
MS_CLIENT_SECRET=...
MS_TENANT_ID=common                    # "common" o el tenant id de la organización

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

Redirect URI (debe coincidir EXACTO en ambos proveedores):

```
<INTEGRATIONS_BASE_URL>/api/admin/integrations/outlook/callback
<INTEGRATIONS_BASE_URL>/api/admin/integrations/google/callback
```

## 2. Azure (Outlook / Microsoft Graph)

1. Azure Portal → **App registrations** → *New registration*.
2. Tipo: **Web**. Redirect URI: `.../api/admin/integrations/outlook/callback`.
3. **Certificates & secrets** → *New client secret* → copiar el valor a `MS_CLIENT_SECRET`.
   El *Application (client) ID* va en `MS_CLIENT_ID`.
4. **API permissions** → Microsoft Graph → *Delegated*:
   - `offline_access`, `User.Read`, `Mail.Read`, `Mail.ReadWrite`, `Calendars.Read`.
   - Si la organización lo exige: **Grant admin consent**.
5. `MS_TENANT_ID`: `common` (cuentas de cualquier organización) o el tenant específico.

## 3. Google Cloud (Gmail / Calendar)

1. Crear proyecto → **APIs & Services** → habilitar **Gmail API** y **Google Calendar API**.
2. **OAuth consent screen**:
   - Tipo *External* (o *Internal* si es Workspace).
   - Scopes: `gmail.readonly`, `gmail.compose`, `calendar.readonly`,
     `openid`, `email`, `profile`.
3. **Credentials** → *Create credentials* → **OAuth client ID** → *Web application*.
   - Authorized redirect URI: `.../api/admin/integrations/google/callback`.
   - Copiar Client ID y Client Secret.
4. ⚠️ **Importante**: en modo *Testing*, los *refresh tokens* caducan a los 7 días.
   Para producción hay que **publicar la app** (Publishing status: In production).

## 4. Uso en el panel

1. Entrar como superadmin (o admin del cliente), seleccionar el cliente.
2. Ir a **Integraciones** → **Conectar** en Outlook o Google.
3. Aceptar el consentimiento. Al volver, la cuenta aparece vinculada.
4. Asignar a los roles los permisos **READ_MAIL** y **READ_CALENDAR** (sección Roles).

## 5. Herramientas del agente

- `correos_recientes`, `buscar_correos`, `leer_correo`, `guardar_borrador_respuesta`
- `eventos_calendario`, `proximos_eventos`

Las herramientas solo aparecen si el cliente tiene una cuenta vinculada.

## 6. Seguridad

- Los tokens se guardan **cifrados** (Fernet) y se renuevan automáticamente.
- El callback OAuth valida un `state` firmado y con expiración (15 min).
- Definir `INTEGRATIONS_ENCRYPTION_KEY` en producción; si se pierde, hay que re-vincular
  las cuentas.

## 7. Dónde pegar las variables (Railway)

1. Railway → tu servicio → pestaña **Variables** → **New Variable**.
2. Agrega cada clave/valor: `INTEGRATIONS_BASE_URL`, `INTEGRATIONS_ENCRYPTION_KEY`,
   `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `MS_TENANT_ID`, `GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`.
3. Railway redespliega solo. Al terminar, en el panel → **Integraciones** los proveedores
   deben mostrar **Conectar** (ya no "Falta configurar credenciales").

Ejemplo de dominio:
`INTEGRATIONS_BASE_URL=https://web-production-b405d.up.railway.app`

Los redirect URI registrados en Azure/Google deben coincidir **exactamente**:
- `https://web-production-b405d.up.railway.app/api/admin/integrations/outlook/callback`
- `https://web-production-b405d.up.railway.app/api/admin/integrations/google/callback`

Si más adelante usas un dominio propio, actualiza `INTEGRATIONS_BASE_URL` y vuelve a
registrar los redirect URI en ambos proveedores.
