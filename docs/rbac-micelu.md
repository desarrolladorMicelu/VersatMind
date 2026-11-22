# RBAC por fuente de datos — implementación

## Qué se agregó

- `data_sources`: fuentes autorizables por tenant (`ofima_table`, `external_db_table`, `sheets`, `excel`, `alegra`, `mail`, `calendar`, `knowledge`).
- `role_source_permissions`: permiso `read`/`none` de un rol sobre una fuente.
- `user_roles`: múltiples roles por usuario; se backfillea desde `users.role_id`.
- Permiso funcional nuevo: `READ_CUSTOMER_PII` para datos personales de clientes.
- Migración `0023_rbac_sources.py` con backfill, fuentes por tenant y roles por defecto.

## Reglas de aplicación

1. Un rol sin filas en `role_source_permissions` conserva el comportamiento legado (permiso funcional suficiente).
2. Un rol con filas queda restringido: solo ve las fuentes con `read`; `none` siempre gana.
3. Las tools se filtran **antes** de enviarse al LLM; no solo se bloquean al ejecutar.
4. `dispatch` revalida permiso funcional + fuente/tabla antes de ejecutar.
5. `ejecutar_consulta` extrae tablas con `sqlglot` y bloquea tablas/esquemas no permitidos y catálogos del sistema.
6. `consultar_indicadores` oculta costo, margen y CxP sin `READ_FINANCE`.
7. `consultar_ventas` y `consultar_ventas_detalle` ocultan costo/utilidad sin `READ_FINANCE`.
8. `generar_informe` valida el tipo de informe contra `READ_SALES` / `READ_FINANCE` / `READ_KPI`; el esquema que ve el LLM solo incluye los tipos permitidos.
9. `consultar_indicadores` cambia su descripción y omite costo/margen/CxP sin `READ_FINANCE`.
10. El prompt del agente solo incluye esquemas, tablas permitidas y conocimiento autorizado.
11. Las denegaciones se registran como `permission_denied` y los cambios de rol como `role_change`.
12. Las tareas programadas ejecutan con el rol actual del usuario destino; si está inactivo/pausado, se omiten.
13. El chat web ya no fuerza permisos completos: superadmin conserva acceso total y tenant_admin usa el rol `admin` del tenant si existe.

## Roles por defecto

| Rol | Funciones | Fuentes |
|---|---|---|
| admin | Todas | Todas las configuradas |
| Gerencia | Todas | Todas las configuradas |
| Comercial | Ventas, KPIs, informes | Ventas, clientes, inventario, maestros, conocimiento |
| Contabilidad | Ventas, KPIs, finanzas, informes, DB externa, PII | Cartera, caja, contabilidad, clientes, Alegra, conocimiento |
| Logística | Ventas, KPIs, informes | Inventario, bodegas, productos, ventas de bodega, conocimiento |

Los roles preexistentes (`board_member`, etc.) **no** se modifican ni se restringen automáticamente. Para MICELU, asigna explícitamente cada usuario a Gerencia/Comercial/Contabilidad/Logística.

## UI

En **Roles** cada rol tiene:
- Funciones permitidas.
- **Fuentes de datos**: “Acceso completo” o una lista de fuentes/tablas permitidas.

En **Usuarios** se asigna el rol. El cambio actualiza `users.role_id` y `user_roles`.

## Pruebas

- `tests/unit/test_data_policy.py`: política, tools expuestas, informes financieros, SQL por tabla, CTE, costo/margen ocultos, CxP oculto.
- Migración aplicada: `0023 (head)`.
- Suite unitaria: 175 pasan; quedan 8 fallos preexistentes de configuración/Alegra ajenos a RBAC.

## Límites conocidos

- `READ_CUSTOMER_PII` se agregó a roles existentes con `READ_SALES` para no romper comportamiento; un admin puede quitarlo.
- La granularidad es por tabla. Si una vista/tabla mezcla columnas sensibles, se recomienda una vista curada por rol.
- Los prompts programados son configurados por administradores y siguen ejecutándose como tarea de servicio; los destinatarios los define el admin.
