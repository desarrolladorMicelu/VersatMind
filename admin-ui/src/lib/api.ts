import axios from "axios";

const api = axios.create({
  baseURL: "/api/admin",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.response.use(
  (r) => r,
  (err) => Promise.reject(err)
);

export default api;

// ── Tipos ─────────────────────────────────────────────────────────────────────

export interface ExternalDbPayload {
  engine: string;
  host: string;
  port: number;
  database: string;
  user: string;
  password: string;
  schema_description?: string;
}

export interface ExternalDbInfo {
  engine: string;
  host: string;
  port: number;
  database: string;
  user: string;
  schema_description?: string;
}

export interface ExternalSheetsPayload {
  spreadsheet_url: string;
  credentials?: Record<string, unknown>;
  schema_description?: string;
}

export interface ExternalSheetsInfo {
  spreadsheet_url: string;
  spreadsheet_id: string;
  schema_description?: string;
}

export interface Tenant {
  id: number;
  name: string;
  slug: string;
  is_active: boolean;
  bot_token_hint: string;
  webhook_url: string;
  admin_chat_id: number;
  sqlserver_host: string;
  sqlserver_db: string;
  sqlserver_user: string;
  sqlserver_driver: string;
  external_db_configured: boolean;
  external_db_engine: string | null;
  external_db: ExternalDbInfo | null;
  external_sheets_configured: boolean;
  external_sheets_spreadsheet: string;
  external_sheets: ExternalSheetsInfo | null;
  external_alegra_configured: boolean;
  external_alegra: AlegraInfo | null;
  created_at: string | null;
}

export interface TenantPayload {
  name: string;
  slug: string;
  bot_token: string;
  webhook_url: string;
  admin_chat_id: number;
  sqlserver_host: string;
  sqlserver_db: string;
  sqlserver_user: string;
  sqlserver_password: string;
  sqlserver_driver: string;
  external_db?: ExternalDbPayload;
  external_sheets?: ExternalSheetsPayload;
  external_alegra?: AlegraPayload;
}

// ── Tenants API ───────────────────────────────────────────────────────────────

export const tenantsApi = {
  list: () => api.get<Tenant[]>("/tenants").then((r) => r.data),
  create: (payload: TenantPayload) => api.post("/tenants", payload).then((r) => r.data),
  update: (id: number, payload: Partial<TenantPayload> & { is_active?: boolean }) =>
    api.put(`/tenants/${id}`, payload).then((r) => r.data),
  remove: (id: number) => api.delete(`/tenants/${id}`).then((r) => r.data),
};

// ── Base de datos externa ─────────────────────────────────────────────────────

export const externalDbApi = {
  testConnection: (tenantId: number, payload: ExternalDbPayload) =>
    api.post(`/tenants/${tenantId}/test-external-db`, payload).then((r) => r.data),
  discoverSchema: (tenantId: number, payload: ExternalDbPayload) =>
    api.post(`/tenants/${tenantId}/discover-schema`, payload).then((r) => r.data),
};

// ── Google Sheets externa ──────────────────────────────────────────────────

export const externalSheetsApi = {
  testConnection: (tenantId: number, payload: ExternalSheetsPayload) =>
    api.post(`/tenants/${tenantId}/test-sheets`, payload).then((r) => r.data),
  discoverSheets: (tenantId: number, payload: ExternalSheetsPayload) =>
    api.post(`/tenants/${tenantId}/discover-sheets`, payload).then((r) => r.data),
};

// ── Alegra (MCP) ─────────────────────────────────────────────────────────

export interface AlegraPayload {
  email: string;
  token: string;
  groups?: string[];
  schema_description?: string;
}

export interface AlegraInfo {
  email: string;
  schema_description?: string;
}

export const alegraApi = {
  testConnection: (tenantId: number, payload: AlegraPayload) =>
    api.post(`/tenants/${tenantId}/alegra/test`, payload).then((r) => r.data),
  discoverTools: (tenantId: number, payload: AlegraPayload) =>
    api.post(`/tenants/${tenantId}/alegra/discover`, payload).then((r) => r.data),
};

// ── Consumo de tokens ─────────────────────────────────────────────────────────

export interface UsageSettings {
  tenant_id?: number;
  threshold_usd: number;
  period: "month" | "total";
  auto_pause: boolean;
  notify_telegram: boolean;
  notify_email: boolean;
  admin_email: string | null;
}

export interface UsageUserRow {
  chat_id: number;
  user_id: number | null;
  username: string | null;
  role_name: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  is_active: boolean;
  is_paused: boolean;
  paused_reason: string | null;
  has_alert: boolean;
  over_threshold: boolean;
  last_activity: string | null;
}

export interface UsageUsersResponse extends UsageSettings {
  currency: string;
  totals: {
    total_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_cost_usd: number;
    users_count: number;
    over_threshold_count: number;
    paused_count: number;
  };
  usuarios: UsageUserRow[];
}

export interface UsageGlobalRow {
  tenant_id: number;
  name: string;
  slug: string;
  is_active: boolean;
  total_tokens: number;
  total_cost_usd: number;
  users_count: number;
  over_threshold_count: number;
  paused_count: number;
  threshold_usd: number;
}

export interface UsageGlobalResponse {
  currency: string;
  totals: {
    total_cost_usd: number;
    total_tokens: number;
    tenants_count: number;
    over_threshold_count: number;
  };
  tenants: UsageGlobalRow[];
}

export interface UsageHistoryRow {
  id: number;
  tenant_id: number;
  tenant_name: string;
  chat_id: number | null;
  user_id: number | null;
  username: string | null;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  source: string;
  created_at: string | null;
}

export interface UsageHistoryResponse {
  total: number;
  limit: number;
  offset: number;
  rows: UsageHistoryRow[];
}

export interface UsageAlertRow {
  id: number;
  tenant_id: number;
  tenant_name: string;
  chat_id: number;
  user_id: number | null;
  username: string | null;
  threshold_usd: number;
  total_cost_usd: number;
  total_tokens: number;
  period_key: string;
  status: string;
  notified: boolean;
  created_at: string | null;
  acknowledged_at: string | null;
}

// ── Prompts programados ───────────────────────────────────────────────────────

export type Frequency = "daily" | "weekly" | "custom";

export interface ScheduledPrompt {
  id: number;
  tenant_id: number;
  name: string;
  description: string;
  prompt: string;
  chat_id: number;
  chat_label: string;
  frequency: Frequency;
  cron_expression: string;
  timezone: string;
  is_active: boolean;
  last_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  created_at: string | null;
  next_run_at?: string | null;
}

export interface ScheduledPromptPayload {
  name: string;
  description?: string;
  prompt: string;
  chat_id: number;
  chat_label?: string;
  frequency: Frequency;
  hour: number;
  minute: number;
  weekday: number;
  cron_expression?: string | null;
  timezone?: string;
  is_active: boolean;
}

export interface PromptVariable {
  key: string;
  desc: string;
}

export const promptsApi = {
  list: (tenantId: number) =>
    api.get<ScheduledPrompt[]>("/prompts", { params: { tenant_id: tenantId } }).then((r) => r.data),
  create: (tenantId: number, payload: ScheduledPromptPayload) =>
    api.post<ScheduledPrompt>("/prompts", payload, { params: { tenant_id: tenantId } }).then((r) => r.data),
  update: (tenantId: number, id: number, payload: Partial<ScheduledPromptPayload>) =>
    api.put<ScheduledPrompt>(`/prompts/${id}`, payload, { params: { tenant_id: tenantId } }).then((r) => r.data),
  toggle: (tenantId: number, id: number) =>
    api.patch(`/prompts/${id}/toggle`, null, { params: { tenant_id: tenantId } }).then((r) => r.data),
  remove: (tenantId: number, id: number) =>
    api.delete(`/prompts/${id}`, { params: { tenant_id: tenantId } }).then((r) => r.data),
  runNow: (tenantId: number, id: number) =>
    api
      .post<{ ok: boolean; text?: string; error?: string; rendered_prompt?: string }>(
        `/prompts/${id}/run`,
        null,
        { params: { tenant_id: tenantId } }
      )
      .then((r) => r.data),
  preview: (tenantId: number, prompt: string) =>
    api.post<{ rendered: string }>("/prompts/preview", { prompt }, { params: { tenant_id: tenantId } }).then((r) => r.data),
  variables: () => api.get<PromptVariable[]>("/prompts/variables").then((r) => r.data),
};

// ── Base de conocimiento ──────────────────────────────────────────────────────

export interface KnowledgeEntry {
  id: number;
  tenant_id: number;
  title: string;
  content: string;
  source: string;
  tags: string;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface KnowledgePayload {
  title: string;
  content: string;
  source?: string;
  tags?: string;
}

export const knowledgeApi = {
  list: (tenantId: number) =>
    api.get<KnowledgeEntry[]>("/conocimiento", { params: { tenant_id: tenantId } }).then((r) => r.data),
  create: (tenantId: number, payload: KnowledgePayload) =>
    api.post<KnowledgeEntry>("/conocimiento", payload, { params: { tenant_id: tenantId } }).then((r) => r.data),
  update: (tenantId: number, id: number, payload: Partial<KnowledgePayload> & { is_active?: boolean }) =>
    api.put<KnowledgeEntry>(`/conocimiento/${id}`, payload, { params: { tenant_id: tenantId } }).then((r) => r.data),
  toggle: (tenantId: number, id: number) =>
    api.patch(`/conocimiento/${id}/toggle`, null, { params: { tenant_id: tenantId } }).then((r) => r.data),
  remove: (tenantId: number, id: number) =>
    api.delete(`/conocimiento/${id}`, { params: { tenant_id: tenantId } }).then((r) => r.data),
};

export const consumoApi = {
  global: (params?: { date_from?: string; date_to?: string }) =>
    api.get<UsageGlobalResponse>("/consumo/global", { params }).then((r) => r.data),
  usuarios: (tenantId: number, params?: { date_from?: string; date_to?: string }) =>
    api
      .get<UsageUsersResponse>("/consumo/usuarios", { params: { tenant_id: tenantId, ...params } })
      .then((r) => r.data),
  config: (tenantId: number) =>
    api.get<UsageSettings>("/consumo/config", { params: { tenant_id: tenantId } }).then((r) => r.data),
  updateConfig: (tenantId: number, payload: UsageSettings) =>
    api.put("/consumo/config", payload, { params: { tenant_id: tenantId } }).then((r) => r.data),
  historial: (params: {
    tenant_id?: number;
    chat_id?: number;
    date_from?: string;
    date_to?: string;
    source?: string;
    limit?: number;
    offset?: number;
  }) => api.get<UsageHistoryResponse>("/consumo/historial", { params }).then((r) => r.data),
  alertas: (params?: { tenant_id?: number; status_filter?: string }) =>
    api.get<UsageAlertRow[]>("/consumo/alertas", { params }).then((r) => r.data),
  reconocerAlerta: (alertId: number) =>
    api.patch(`/consumo/alertas/${alertId}/reconocer`).then((r) => r.data),
  pausar: (tenantId: number, chatId: number, reason?: string) =>
    api
      .post(`/consumo/usuarios/${chatId}/pausar`, { reason }, { params: { tenant_id: tenantId } })
      .then((r) => r.data),
  reanudar: (tenantId: number, chatId: number) =>
    api.post(`/consumo/usuarios/${chatId}/reanudar`, null, { params: { tenant_id: tenantId } }).then((r) => r.data),
};
