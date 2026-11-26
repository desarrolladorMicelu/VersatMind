# Usuarios de portal y multi-tienda

## Modelo

- `portal_users`: cuenta global con `username`, contraseña, estado y contraseña temporal cifrada.
- `memberships`: pertenencia a una tienda con un rol para esa tienda. Un usuario puede tener 1..N tiendas, cada una con su propio rol.
- `users.portal_user_id`: vínculo del chat de Telegram con su cuenta de portal. Un usuario de Telegram no existe sin cuenta de portal.
- `tenant_admins` se mantiene separado para el panel de administración (decisión de menor riesgo).

## Backfill de Telegram

Al arrancar, `backfill_portal_users()`:

- Crea `PortalUser` para cada usuario de Telegram que aún no tenga cuenta.
- Genera una contraseña temporal automática y la guarda cifrada.
- Crea una `Membership` por cada tienda/rol donde el chat esté autorizado.
- Vincula `users.portal_user_id`.

El administrador puede revelar o regenerar la contraseña temporal desde **Usuarios → Contraseña temporal**.

## Login y sesión

- Login admin: superadmin / tenant_admin como antes.
- Login portal: `portal_users.username` + contraseña; JWT con `role=portal_user` y `portal_user_id`.
- `GET /api/admin/me` devuelve las tiendas y roles del usuario portal.
- Un usuario portal solo puede entrar al chat. Las rutas de administración siguen bloqueadas para `portal_user`.

## Chat multi-tienda

- El usuario portal cambia de tienda desde **Configuración** en el chat.
- Cada conversación pertenece a `(usuario portal, tienda)`.
- El backend resuelve el rol desde la `Membership` de la tienda activa.
- Las tools, fuentes y tablas se filtran con el mismo RBAC ya existente.
- Un usuario no puede acceder a una tienda donde no tiene membership.

## Administración

En **Usuarios**:

- Superadmin ve todos los usuarios y todas sus tiendas.
- Tenant admin ve únicamente los usuarios/roles de su tienda.
- Crear usuario: usuario, nombre, contraseña o temporal, tiendas y roles.
- Un tenant admin solo puede asignar su propia tienda.
- Superadmin puede vincular/desvincular un chat de Telegram.
- Tenant admin puede activar/desactivar la pertenencia a su tienda.
- Las credenciales de usuarios multi-tienda solo las gestiona el superadmin; un tenant admin no puede generar/ver su contraseña.

## Seguridad

- Las contraseñas temporales se guardan cifradas con una clave derivada de `ADMIN_SECRET_KEY`.
- Al iniciar sesión se elimina el valor temporal cifrado.
- Una cuenta de Telegram siempre queda ligada a una cuenta de portal.
- Un chat de Telegram no puede quedar ligado a dos cuentas de portal distintas.
- Portal users no pueden acceder a endpoints `require_admin`.

## Migración

- `alembic/versions/0025_portal_users.py`.
- Backfill de datos en el arranque de la aplicación.

## Pruebas realizadas

- Backfill de usuario Telegram existente con membership y contraseña temporal.
- Login portal, `/me`, listado/creación de conversaciones y rechazo de tiendas ajenas.
- Bloqueo de endpoints administrativos para portal users.
- Creación/edición de usuarios de portal, membresías y contraseña temporal desde API.
- Acceso a informes HTML con identidad portal y aislamiento por propietario.
