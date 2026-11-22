# Unificación tipográfica — Panel de administración

## Inventario (antes)

| Dónde | Familia / tamaño |
|---|---|
| `admin-ui/src/index.css` | Google Fonts **Space Grotesk** (interfaz) + **Space Mono** (labels, botones, badges, tablas, nav) |
| `admin-ui/tailwind.config.js` | `font-sans: Space Grotesk`, `font-mono: Space Mono` |
| `admin-ui/src/chat.css` | **Calibri / Carlito / Segoe UI** como familia base |
| `admin-ui/src/chat.css` (código) | Cascadia Code / Consolas |
| `admin-ui/src/**/*.tsx` | 254 usos de `font-mono`; 109 tamaños arbitrarios de 9–11 px; tracking de hasta `0.2em` |
| `admin-ui/src/App.css` | CSS del template de Vite, sin uso |

## Decisión

- **Una sola familia para la interfaz: Inter** (con fallback a `Segoe UI` / sistema).
- **Monoespaciada solo para código y datos técnicos**: stack del sistema (`ui-monospace`, Consolas, etc.), sin descargar otra fuente.
- Escala centralizada en `admin-ui/src/styles/tokens.css`:

| Token | Valor | Uso |
|---|---|---|
| `--text-2xs` | 12 px | metadatos y labels densos |
| `--text-xs` | 13 px | ayudas, badges, navegación |
| `--text-sm` | 15 px | cuerpo por defecto |
| `--text-base` | 16 px | cuerpo destacado |
| `--text-lg` | 18 px | H3 |
| `--text-xl` | 22 px | H2 |
| `--text-2xl` | 28 px | H1 de página |
| `--text-3xl` | 36 px | display |

También viven ahí los pesos, interlineados, tracking y la paleta base. Tailwind consume los mismos tokens (`fontSize`, `fontFamily`) y los componentes usan clases de escala (`text-xs`, `text-sm`, `text-2xl`…) en lugar de tamaños sueltos.

## Cambios visuales

- Se eliminó `Space Grotesk` y `Space Mono`; solo queda un `@import` de Inter.
- Se eliminaron todos los `font-mono` inline (254) y los tamaños arbitrarios de 9–11 px.
- Se redujo el tracking extremo de labels y badges.
- Fondo negro azulado con superficies por capas, bordes suaves, radios consistentes y acento esmeralda menos saturado.
- Login rediseñado con panel de marca + formulario.
- Sidebar, header de página, métricas y tablas con jerarquía y espaciado revisados.
- Tablas críticas con scroll horizontal en móvil; header móvil con espacio para el menú.

## Capturas

- `before-login-desktop.png` / `after-login-desktop.png`
- `before-login-mobile.png` / `after-login-mobile.png`
- `after-dashboard-desktop.png` / `after-dashboard-mobile.png`
- `after-superadmins-desktop.png` / `after-superadmins-mobile.png`
- `after-tenants-desktop.png`

## Chat minimalista (segunda fase)

El chat pasó a ser una pantalla completa (`/admin/chat`) fuera del layout de administración:

- Barra lateral de 288 px, colapsable a 76 px (solo iconos) y off-canvas en móvil.
- Navegación: **Nuevo chat**, **Historial**, **Proyectos** (espacio reservado, marcado “Pronto”), **Configuración** y **Panel de administración**.
- Regreso siempre visible al panel: botón **← Panel** en el encabezado, ítem **Panel de administración** en la barra lateral y botón **Ir al panel** en Configuración.
- Acciones secundarias (nuevo chat, eliminar conversación, configuración) movidas al menú contextual `···` del encabezado.
- Estado vacío simple con 4 sugerencias de preguntas y un composer fijo.
- Configuración con cuenta, cliente activo (selector para superadmin), acceso al panel y cierre de sesión.
- Sin degradados, glows ni animaciones decorativas. Solo transiciones sutiles de hover y el cursor de streaming.
- Paleta y espaciado desde tokens: `--color-*`, `--space-*`, `--radius-*` en `styles/tokens.css`.

### Legibilidad y navegación del panel

- Escala base subida: cuerpo de 16 px, metadatos de 13–14 px, títulos de página de 32 px, tablas de 15 px.
- Sidebar del panel agrupada en **Principal**, **Operación**, **Administración** y **Sistema** para reducir la carga visual.
- El acceso a Chat se marca con una flecha para indicar que abre la vista enfocada de conversación.
- Tablas críticas mantienen scroll horizontal en móvil.

Capturas adicionales:

- `before-chat-desktop.png` / `after-chat-desktop.png`
- `before-chat-mobile.png` / `after-chat-mobile.png`
- `after-chat-collapsed.png`
- `after-chat-config.png`
- `after-chat-projects.png`
- `after-chat-mobile-menu.png`

## Verificación

- `npm run build` (incluye `tsc -b`) OK.
- ESLint sin errores nuevos en los archivos tocados.
- Capturas tomadas con Chrome headless y emulación móvil real (390 × 844).
