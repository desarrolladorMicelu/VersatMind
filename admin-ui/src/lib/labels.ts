/**
 * Etiquetas visibles para personas no técnicas.
 * Centraliza la traducción de valores técnicos que llegan del backend.
 */

const EVENT_LABELS: Record<string, string> = {
  interaction: "Conversación",
  tool_failure: "Error de consulta",
  unauthorized: "Acceso no autorizado",
  permission_denied: "Acceso denegado",
  role_change: "Cambio de permisos",
  scheduler: "Tarea automática",
  meeting: "Reunión",
  login: "Inicio de sesión",
};

const STATUS_LABELS: Record<string, string> = {
  success: "Correcto",
  ok: "Correcto",
  error: "Con error",
  failed: "Con error",
  failure: "Con error",
  pending: "Pendiente",
  approved: "Aprobado",
  rejected: "Rechazado",
  active: "Activo",
  inactive: "Inactivo",
  paused: "Pausado",
  running: "En proceso",
  processing: "Procesando",
  done: "Completado",
  completed: "Completado",
  ready: "Listo",
  recording: "Grabando",
  sent: "Enviado",
  acknowledged: "Revisada",
  resolved: "Resuelta",
  denied: "Denegado",
  connected: "Conectada",
  disconnected: "Desconectada",
  revoked: "Revocada",
};

const SOURCE_LABELS: Record<string, string> = {
  scheduler: "Tarea programada",
  telegram: "Telegram",
  web: "Web",
  api: "API",
  chat: "Asistente web",
  admin: "Panel",
  panel: "Panel",
};

const TOOL_LABELS: Record<string, string> = {
  consultar_ventas: "Consulta de ventas",
  consultar_ventas_detalle: "Detalle de ventas",
  consultar_indicadores: "Consulta de indicadores",
  consultar_finanzas: "Consulta de finanzas",
  consultar_productos: "Consulta de productos",
  consultar_cxp: "Consulta de cuentas por pagar",
  generar_informe: "Generación de informe",
  crear_tarea_programada: "Creación de tarea programada",
  listar_tareas: "Listado de tareas",
  modificar_tarea: "Edición de tarea",
  eliminar_tarea: "Eliminación de tarea",
  ejecutar_consulta: "Consulta a base de datos",
  consultar_sheet: "Consulta a Google Sheets",
  consultar_excel: "Consulta a Excel",
  consultar_alegra: "Consulta a Alegra",
  generar_informe_contable: "Informe contable",
};

const ROLE_LABELS: Record<string, string> = {
  user: "Usuario",
  assistant: "Asistente",
  tool: "Consulta interna",
  admin: "Administrador",
  superadmin: "Superadministrador",
  tenant_admin: "Administrador del cliente",
  board_member: "Miembro de junta",
  finance: "Finanzas",
  commercial: "Comercial",
  Gerencia: "Gerencia",
  Comercial: "Comercial",
  Contabilidad: "Contabilidad",
  "Logística": "Logística",
  Logistica: "Logística",
};

const ENGINE_LABELS: Record<string, string> = {
  postgresql: "PostgreSQL",
  postgres: "PostgreSQL",
  mysql: "MySQL",
  sqlserver: "SQL Server",
  mariadb: "MariaDB",
};

export function eventLabel(value?: string | null): string {
  if (!value) return "Sin tipo";
  return EVENT_LABELS[value] ?? "Otro evento";
}

export function statusLabel(value?: string | null): string {
  if (!value) return "Sin estado";
  return STATUS_LABELS[value] ?? "Sin estado";
}

export function sourceLabel(value?: string | null): string {
  if (!value) return "—";
  return SOURCE_LABELS[value] ?? "Otro origen";
}

export function toolLabel(value?: string | null): string {
  if (!value) return "—";
  return TOOL_LABELS[value] ?? "Consulta del asistente";
}

export function roleLabel(value?: string | null): string {
  if (!value) return "Usuario";
  return ROLE_LABELS[value] ?? "Usuario";
}

export function engineLabel(value?: string | null): string {
  if (!value) return "Base de datos";
  return ENGINE_LABELS[value.toLowerCase()] ?? "Base de datos";
}

export function activeLabel(value: boolean, feminine = false): string {
  if (feminine) return value ? "Activa" : "Inactiva";
  return value ? "Activo" : "Inactivo";
}

const DOW_NAMES: Record<string, string> = {
  "0": "Domingo", "1": "Lunes", "2": "Martes", "3": "Miércoles",
  "4": "Jueves", "5": "Viernes", "6": "Sábado", "7": "Domingo",
};

function weekdayLabel(value: string): string | null {
  if (DOW_NAMES[value]) return DOW_NAMES[value];
  if (value === "1-5") return "Lunes a viernes";
  if (value === "6,0" || value === "0,6") return "Fines de semana";
  const days = value.split(",").map((d) => DOW_NAMES[d]).filter(Boolean);
  return days.length ? days.join(", ") : null;
}

/** Traduce las expresiones cron más comunes a una frase legible. */
export function cronLabel(expression?: string | null): string {
  if (!expression) return "Personalizada";
  const parts = expression.trim().split(/\s+/);
  if (parts.length !== 5) return "Personalizada";
  const [minute, hour, dom, month, dow] = parts;
  const time = /^\d+$/.test(minute) && /^\d+$/.test(hour)
    ? `${String(Number(hour)).padStart(2, "0")}:${String(Number(minute)).padStart(2, "0")}`
    : "";

  if (dow !== "*" && dom === "*") {
    const days = weekdayLabel(dow);
    if (days) return `${days}${time ? `, ${time}` : ""}`;
  }
  if (dom !== "*" && dow === "*" && /^\d+$/.test(dom) && month === "*") {
    return `Día ${dom} de cada mes${time ? `, ${time}` : ""}`;
  }
  if (dom === "*" && month === "*" && dow === "*") {
    return time ? `Todos los días, ${time}` : "Cada hora";
  }
  return "Personalizada";
}

export function isOkStatus(value?: string | null): boolean {
  return value === "success" || value === "ok" || value === "completed" || value === "done";
}

export function isErrorStatus(value?: string | null): boolean {
  return value === "error" || value === "failed" || value === "failure";
}
