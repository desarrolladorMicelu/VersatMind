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
