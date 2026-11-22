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

## Verificación

- `npm run build` (incluye `tsc -b`) OK.
- ESLint sin errores nuevos en los archivos tocados.
