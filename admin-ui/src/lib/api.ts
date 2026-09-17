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
}

// ── Tenants API ───────────────────────────────────────────────────────────────

export const tenantsApi = {
  list: () => api.get<Tenant[]>("/tenants").then((r) => r.data),
  create: (payload: TenantPayload) => api.post("/tenants", payload).then((r) => r.data),
  update: (id: number, payload: Partial<TenantPayload> & { is_active?: boolean }) =>
    api.put(`/tenants/${id}`, payload).then((r) => r.data),
  remove: (id: number) => api.delete(`/tenants/${id}`).then((r) => r.data),
};
