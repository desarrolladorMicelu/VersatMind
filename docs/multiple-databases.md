# Bases de datos adicionales por tienda

## Modelo

Cada cliente conserva:

- **OFIMA**: SQL Server principal.
- **Base principal**: `tenant.external_db` (PostgreSQL).
- **Bases adicionales**: tabla `tenant_databases`, con `alias`, `label`, `config`, `is_active`.

Un cliente puede tener la base principal + N bases adicionales PostgreSQL.

## Configuración

En **Clientes → editar cliente**:

- Sección **Base de datos externa** para la principal (la que ya existía).
- Sección **Bases de datos adicionales**:
  - Alias estable (`micelu_pg`, `contabilidad`, etc.).
  - Nombre visible.
  - Host, puerto, base, usuario, contraseña, schema.
  - Tablas permitidas (separadas por coma).
  - Probar conexión.
  - Detectar esquema.
  - Activa/inactiva.

El alias no se puede cambiar después porque es la clave de permisos (`db:<alias>`).

## Consulta desde el chat

`ejecutar_consulta` ahora acepta:

- `base="principal"` → `tenant.external_db`.
- `base="<alias>"` → `tenant_databases`.

El prompt inyecta el esquema de cada base permitida y le indica al agente el alias correcto. Si una base no está permitida para el rol, su esquema no se envía y la consulta se bloquea.

## Permisos

- Fuente genérica: `db:<alias>`.
- Fuente por tabla: `db:<alias>:<tabla>`.
- En **Roles → Fuentes de datos** aparecen como:
  - `Base de datos · <nombre>`.
  - `<nombre> · <tabla>`.

Al crear una base se sincronizan sus `data_sources`; al eliminarla se eliminan sus fuentes y permisos. Admin y Gerencia reciben lectura automática; los demás roles se asignan manualmente.

## Seguridad

- Solo PostgreSQL por ahora.
- SELECT únicamente, una sola sentencia.
- Validación de tablas por alias y política de rol.
- Esquemas del sistema bloqueados.
- URLs/credenciales no se muestran al LLM.
- Las consultas quedan auditadas.

## Migración

`alembic/versions/0028_tenant_databases.py`.
