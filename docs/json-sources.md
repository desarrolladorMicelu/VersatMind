# Fuentes JSON / R2

## Qué hace

Permite asociar dos archivos JSON por tienda, con el mismo esquema siempre:

- `precios`: competencia, posición 1, presencia/precio de Micelu y brecha.
- `historial`: cambios de precio/posición de Micelu.

No se inyecta el archivo completo en el prompt. El agente consulta con
herramientas filtradas y el backend devuelve como máximo 50 filas compactas.

## Configuración

En **Clientes → editar cliente → Fuentes JSON / R2**:

- URL del JSON de precios.
- URL del JSON de historial.
- Activa por archivo.
- **Probar**: descarga, valida esquema y muestra el número de registros.

Las URLs se guardan en `tenants.json_sources`; no se exponen al usuario ni al
LLM. El conector exige HTTPS y limita el archivo a 10 MB.

## Herramientas

- `consultar_precios_exito`: código, código OFIMA, nombre, vendedor, solo con
  Micelu, rango de precio y límite.
- `resumen_precios_exito`: totales, presencia de Micelu y brechas agregadas.
- `consultar_historial_exito`: código, producto, tipo de cambio, rango de
  fechas y límite.
- `resumen_historial_exito`: totales por tipo, productos y rango de fechas.

Cada resultado incluye `total`, `mostrados` e `items`. Las tools se filtran
antes de enviarse al LLM: si el rol no tiene la fuente, no aparecen.

## Permisos

- Permiso funcional: `READ_JSON_DATA`.
- Fuentes: `json:precios` y `json:historial` en `data_sources`.
- En **Roles → Fuentes de datos** se activa/desactiva cada archivo por rol.
- Si un rol no tiene la fuente, `dispatch` también bloquea el intento y lo
  audita como `permission_denied`.

Por defecto la migración asigna lectura a admin, Gerencia, Comercial y
Contabilidad. Logística no la recibe por defecto.

## Control de tokens

- Cache en memoria de 5 minutos por tenant/fuente.
- Máximo 20 filas por defecto y 50 como límite duro.
- Resúmenes agregados para preguntas generales.
- El prompt solo recibe la descripción de la herramienta, nunca el JSON.
- Los campos de URL de producto no se devuelven al modelo.

## Seguridad R2

La URL pública de R2 permite lectura a cualquiera que la conozca. Si los datos
son sensibles, usa un bucket privado con URL firmada o un proxy del backend.
La app guarda la URL en servidor y no la muestra en el chat.

## Esquema

Los JSON deben ser arreglos de objetos.

Precios: `nombre`, `codigo`, `codigo_ofim`, `posicion_1`, `micelu`, etc.
Historial: `producto`, `codigo`, `fecha`, `tipo_cambio`, posiciones y precios
anteriores/nuevos.

La validación se ejecuta al probar y al consultar. Si el esquema no coincide,
la fuente responde con un error claro y no se envía nada al modelo.
