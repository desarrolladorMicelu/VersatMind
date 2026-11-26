# Informes y tableros en el chat web

## Reutilización de VT-51

- Se conserva `mind/reports/generator.py` como punto único de generación.
- El chat web agrega `mind/reports/dashboard.py`, que reutiliza la
  normalización de secciones y el logo/config del generador, y produce un
  tablero HTML autocontenido.
- Las tools existentes (`generar_informe` y `generar_informe_contable`)
  detectan el canal `web` y persisten el HTML; en Telegram mantienen el
  PDF/Excel de VT-51.

## Flujo web

1. El usuario pide un informe o tablero en el chat.
2. La IA consulta datos con las tools permitidas por RBAC.
3. Llama a `generar_informe_contable` con secciones o `generar_informe` con
   un tipo (`ventas`, `finanzas`, `indicadores`).
4. El backend genera un HTML con KPIs, gráficos SVG y tablas, más JavaScript propio para interactividad.
5. El HTML se guarda en `reports`, asociado a conversación, usuario y tenant.
6. El SSE emite un evento `report`; el chat muestra una tarjeta con iframe.
7. Al recargar, `/conversations/{id}/messages` devuelve los reportes de cada
   mensaje.

## Endpoints

- `GET /api/admin/reports/{id}/html?tenant_id=...` — vista previa.
- `GET /api/admin/reports/{id}/download?tenant_id=...` — descarga HTML.
- `GET /api/admin/reports/{id}/pdf?tenant_id=...` — PDF si WeasyPrint está
  disponible.

Todos validan JWT de admin, tenant y propietario del informe.

## Seguridad

- El iframe usa `sandbox="allow-scripts allow-downloads"` sin `allow-same-origin`.
- El HTML se sirve con CSP `sandbox allow-scripts allow-downloads;
  script-src 'unsafe-inline'; connect-src 'none'`, sin recursos externos.
- El JavaScript es de plantilla fija; los datos se insertan escapados y no se
  ejecuta HTML del usuario.
- Incluye filtros por gráfico/leyenda, KPIs recalculados, búsqueda, orden de
  columnas, cambio de tipo de gráfico y exportación CSV.
- Los perfiles de permisos se siguen aplicando antes de consultar datos.

## PDF opcional

El botón PDF solo aparece si `weasyprint` está instalado. Si no, el informe
sigue disponible como HTML descargable.

## Pruebas

- `tests/unit/test_data_policy.py` cubre RBAC y tools.
- Flujo manual verificado: creación de reporte, persistencia, endpoints HTML,
  descarga, aislamiento por tenant y carga en historial del chat.
