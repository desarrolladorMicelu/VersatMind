import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, Pencil, Trash2, Power, X, Eye, EyeOff, Database, Bot, Users, KeyRound } from "lucide-react";
import api, { tenantsApi } from "../lib/api";
import type { Tenant, TenantPayload } from "../lib/api";
import { fmtDateShort } from "../lib/utils";
import PageHeader from "../components/PageHeader";
import ExternalDbConfig from "../components/ExternalDbConfig";
import ExternalSheetsConfig from "../components/ExternalSheetsConfig";

const EMPTY: TenantPayload = {
  name: "",
  slug: "",
  bot_token: "",
  webhook_url: "",
  admin_chat_id: 0,
  sqlserver_host: "",
  sqlserver_db: "",
  sqlserver_user: "",
  sqlserver_password: "",
  sqlserver_driver: "ODBC Driver 18 for SQL Server",
};

// ── Modal crear / editar ──────────────────────────────────────────────────────

function TenantModal({
  initial,
  onClose,
  onSave,
  saving,
}: {
  initial: TenantPayload & { id?: number };
  onClose: () => void;
  onSave: (data: TenantPayload & { id?: number }) => void;
  saving: boolean;
}) {
  const [form, setForm] = useState(initial);
  const [showPass, setShowPass] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const isEdit = !!initial.id;

  const set = (k: keyof TenantPayload, v: string | number) =>
    setForm((f) => ({ ...f, [k]: v }));

  const handleSlug = (v: string) =>
    set("slug", v.toLowerCase().replace(/[^a-z0-9-]/g, "-"));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl bg-[#0d0d0d] border border-[#2a2a2a] flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#1a1a1a] flex-shrink-0">
          <div>
            <p className="section-tag mb-1">// {isEdit ? "EDITAR" : "NUEVO"} CLIENTE</p>
            <h2 className="text-lg font-bold text-white tracking-tight">
              {isEdit ? form.name || "Sin nombre" : "Crear tenant"}
            </h2>
          </div>
          <button onClick={onClose} className="text-white hover:text-white transition-colors p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 px-6 py-5 space-y-5">

          {/* Info básica */}
          <div className="border border-[#1a1a1a]">
            <div className="px-4 py-2.5 border-b border-[#1a1a1a] bg-[#050505]">
              <span className="section-tag">// INFORMACIÓN BÁSICA</span>
            </div>
            <div className="p-4 grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="label">Nombre del cliente</label>
                <input
                  className="input"
                  placeholder="Empresa XYZ S.A.S."
                  value={form.name}
                  onChange={(e) => {
                    set("name", e.target.value);
                    if (!isEdit) handleSlug(e.target.value);
                  }}
                />
              </div>
              <div>
                <label className="label">Slug <span className="text-white">(identificador único)</span></label>
                <input
                  className="input font-mono"
                  placeholder="empresa-xyz"
                  value={form.slug}
                  onChange={(e) => handleSlug(e.target.value)}
                />
                <p className="font-mono text-[10px] text-white mt-1.5">Solo letras, números y guiones</p>
              </div>
              <div>
                <label className="label">Admin Chat ID <span className="text-white">(Telegram)</span></label>
                <input
                  className="input font-mono"
                  placeholder="123456789"
                  type="number"
                  value={form.admin_chat_id || ""}
                  onChange={(e) => set("admin_chat_id", parseInt(e.target.value) || 0)}
                />
                <p className="font-mono text-[10px] text-white mt-1.5">Chat ID del administrador del tenant</p>
              </div>
            </div>
          </div>

          {/* Telegram */}
          <div className="border border-[#1a1a1a]">
            <div className="px-4 py-2.5 border-b border-[#1a1a1a] bg-[#050505] flex items-center gap-2">
              <Bot className="w-3 h-3 text-[#00e5a0]" />
              <span className="section-tag">// TELEGRAM</span>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="label">
                  Token del bot
                  {isEdit && <span className="text-white ml-2">(dejar vacío para no cambiar)</span>}
                </label>
                <div className="relative">
                  <input
                    className="input pr-10 font-mono text-xs"
                    placeholder="1234567890:ABCDefgh..."
                    type={showToken ? "text" : "password"}
                    value={form.bot_token}
                    onChange={(e) => set("bot_token", e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowToken((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-white hover:text-white transition-colors"
                  >
                    {showToken ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </button>
                </div>
                <p className="font-mono text-[10px] text-white mt-1.5">
                  Obtenlo de @BotFather → /newbot
                </p>
              </div>
              <div>
                <label className="label">Webhook URL <span className="text-white">(URL pública del servidor)</span></label>
                <input
                  className="input font-mono text-xs"
                  placeholder="https://tu-servidor.railway.app"
                  value={form.webhook_url}
                  onChange={(e) => set("webhook_url", e.target.value)}
                />
                <p className="font-mono text-[10px] text-white mt-1.5">
                  El webhook se registra automáticamente en{" "}
                  <span className="text-white">{form.webhook_url || "https://…"}/webhook/&#60;token&#62;</span>
                </p>
              </div>
            </div>
          </div>

          {/* SQL Server */}
          <div className="border border-[#1a1a1a]">
            <div className="px-4 py-2.5 border-b border-[#1a1a1a] bg-[#050505] flex items-center gap-2">
              <Database className="w-3 h-3 text-[#00e5a0]" />
              <span className="section-tag">// SQL SERVER OFIMA</span>
            </div>
            <div className="p-4 grid grid-cols-2 gap-4">
              <div>
                <label className="label">Host / IP</label>
                <input
                  className="input font-mono text-xs"
                  placeholder="172.200.231.95"
                  value={form.sqlserver_host}
                  onChange={(e) => set("sqlserver_host", e.target.value)}
                />
              </div>
              <div>
                <label className="label">Base de datos</label>
                <input
                  className="input font-mono text-xs"
                  placeholder="MICELU"
                  value={form.sqlserver_db}
                  onChange={(e) => set("sqlserver_db", e.target.value)}
                />
              </div>
              <div>
                <label className="label">Usuario</label>
                <input
                  className="input font-mono text-xs"
                  placeholder="db_read"
                  value={form.sqlserver_user}
                  onChange={(e) => set("sqlserver_user", e.target.value)}
                />
              </div>
              <div>
                <label className="label">
                  Contraseña
                  {isEdit && <span className="text-white ml-2">(dejar vacío para no cambiar)</span>}
                </label>
                <div className="relative">
                  <input
                    className="input pr-10 font-mono text-xs"
                    placeholder="••••••••"
                    type={showPass ? "text" : "password"}
                    value={form.sqlserver_password}
                    onChange={(e) => set("sqlserver_password", e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-white hover:text-white transition-colors"
                  >
                    {showPass ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>
              <div className="col-span-2">
                <label className="label">Driver ODBC</label>
                <input
                  className="input font-mono text-xs"
                  value={form.sqlserver_driver}
                  onChange={(e) => set("sqlserver_driver", e.target.value)}
                />
              </div>
            </div>
          </div>

          {/* Base de datos externa */}
          <ExternalDbConfig
            value={form.external_db ?? null}
            onChange={(v) => setForm((f) => ({ ...f, external_db: v ?? undefined }))}
            tenantId={form.id}
          />

          {/* Google Sheets */}
          <ExternalSheetsConfig
            value={form.external_sheets ?? null}
            onChange={(v) => setForm((f) => ({ ...f, external_sheets: v ?? undefined }))}
            tenantId={form.id}
          />

        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-[#1a1a1a] flex-shrink-0">
          <button onClick={onClose} className="btn-ghost">CANCELAR</button>
          <button
            className="btn-primary"
            disabled={saving || !form.name || !form.slug || (!isEdit && !form.bot_token)}
            onClick={() => onSave(form)}
          >
            {saving ? "GUARDANDO..." : isEdit ? "GUARDAR CAMBIOS →" : "CREAR CLIENTE →"}
          </button>
        </div>

      </div>
    </div>
  );
}

// ── Gestión de admins del tenant ─────────────────────────────────────────────

function TenantAdmins({ tenantId, tenantName }: { tenantId: number; tenantName: string }) {
  const qc = useQueryClient();
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [creating, setCreating] = useState(false);

  const { data: admins = [], isLoading } = useQuery({
    queryKey: ["tenant-admins", tenantId],
    queryFn: () => api.get(`/tenants/${tenantId}/admins`).then((r) => r.data),
  });

  const create = useMutation({
    mutationFn: () => api.post(`/tenants/${tenantId}/admins`, { username: newUsername, password: newPassword }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tenant-admins", tenantId] });
      setNewUsername("");
      setNewPassword("");
      setCreating(false);
    },
  });

  const toggleAdmin = useMutation({
    mutationFn: ({ adminId, is_active }: { adminId: number; is_active: boolean }) =>
      api.patch(`/tenants/${tenantId}/admins/${adminId}`, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenant-admins", tenantId] }),
  });

  const removeAdmin = useMutation({
    mutationFn: (adminId: number) => api.delete(`/tenants/${tenantId}/admins/${adminId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenant-admins", tenantId] }),
  });

  return (
    <div className="border-t border-[#1a1a1a] bg-[#080808]">
      <div className="px-6 py-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <KeyRound className="w-3.5 h-3.5 text-[#00e5a0]" />
            <span className="section-tag">// ACCESOS AL PANEL — {tenantName}</span>
          </div>
          <button
            onClick={() => setCreating((v) => !v)}
            className="btn-primary flex items-center gap-1.5 text-[10px] py-1 px-3"
          >
            <Plus className="w-3 h-3" /> NUEVA CUENTA
          </button>
        </div>

        {/* Formulario nueva cuenta */}
        {creating && (
          <div className="mb-4 border border-[#00e5a0]/20 bg-[#050505] p-4 flex flex-wrap gap-3 items-end">
            <div>
              <label className="label">Usuario</label>
              <input
                className="input w-44"
                placeholder="admin_cliente"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
              />
            </div>
            <div>
              <label className="label">Contraseña</label>
              <div className="relative">
                <input
                  className="input w-44 pr-9 font-mono"
                  placeholder="••••••••"
                  type={showPass ? "text" : "password"}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
                <button
                  type="button"
                  onClick={() => setShowPass((v) => !v)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#444] hover:text-[#888]"
                >
                  {showPass ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                </button>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                className="btn-primary py-1 px-3 text-[10px]"
                disabled={!newUsername || !newPassword || create.isPending}
                onClick={() => create.mutate()}
              >
                {create.isPending ? "CREANDO..." : "CREAR →"}
              </button>
              <button className="btn-ghost py-1 px-3 text-[10px]" onClick={() => setCreating(false)}>
                CANCELAR
              </button>
            </div>
            {create.isError && (
              <p className="w-full font-mono text-[10px] text-red-400">
                {(create.error as any)?.response?.data?.detail ?? "Error al crear la cuenta"}
              </p>
            )}
          </div>
        )}

        {/* Lista de admins */}
        {isLoading ? (
          <div className="h-10 animate-pulse border border-[#111]" />
        ) : admins.length === 0 ? (
          <p className="font-mono text-[10px] text-[#333] py-3">Sin cuentas creadas — este cliente no puede entrar al panel.</p>
        ) : (
          <div className="border border-[#1a1a1a]">
            <div className="grid grid-cols-12 bg-[#050505] border-b border-[#111]">
              <div className="col-span-4 th">Usuario</div>
              <div className="col-span-3 th">Estado</div>
              <div className="col-span-3 th">Creado</div>
              <div className="col-span-2 th" />
            </div>
            {admins.map((a: any) => (
              <div key={a.id} className="grid grid-cols-12 border-b border-[#111] hover:bg-[#050505] transition-colors">
                <div className="col-span-4 td">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 border border-[#2a2a2a] flex items-center justify-center flex-shrink-0">
                      <span className="font-mono text-[9px] text-[#00e5a0]">{a.username[0]?.toUpperCase()}</span>
                    </div>
                    <span className="font-mono text-xs text-white">{a.username}</span>
                  </div>
                </div>
                <div className="col-span-3 td">
                  <span className={`badge ${a.is_active ? "badge-green" : "badge-slate"}`}>
                    {a.is_active ? "ACTIVO" : "INACTIVO"}
                  </span>
                </div>
                <div className="col-span-3 td font-mono text-[11px] text-[#444]">
                  {a.created_at ? new Date(a.created_at).toLocaleDateString("es-CO") : "—"}
                </div>
                <div className="col-span-2 td">
                  <div className="flex items-center gap-1 justify-end">
                    <button
                      onClick={() => toggleAdmin.mutate({ adminId: a.id, is_active: !a.is_active })}
                      className={`p-1.5 transition-colors ${a.is_active ? "text-[#333] hover:text-yellow-500" : "text-[#333] hover:text-[#00e5a0]"}`}
                      title={a.is_active ? "Desactivar" : "Activar"}
                    >
                      <Power className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => window.confirm(`¿Eliminar la cuenta "${a.username}"?`) && removeAdmin.mutate(a.id)}
                      className="p-1.5 text-[#333] hover:text-red-500 transition-colors"
                      title="Eliminar"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function Tenants() {
  const qc = useQueryClient();
  const [modal, setModal] = useState<(TenantPayload & { id?: number }) | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const { data: tenants = [], isLoading } = useQuery<Tenant[]>({
    queryKey: ["tenants"],
    queryFn: tenantsApi.list,
  });

  const create = useMutation({
    mutationFn: (p: TenantPayload) => tenantsApi.create(p),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tenants"] });
      setModal(null);
    },
  });

  const update = useMutation({
    mutationFn: ({ id, ...rest }: TenantPayload & { id: number }) =>
      tenantsApi.update(id, rest),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tenants"] });
      setModal(null);
    },
  });

  const toggle = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      tenantsApi.update(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  });

  const remove = useMutation({
    mutationFn: (id: number) => tenantsApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  });

  const handleSave = (data: TenantPayload & { id?: number }) => {
    if (data.id) {
      // En edición: omitir campos vacíos (contraseña y token) para no sobreescribir
      const payload: Partial<TenantPayload> = { ...data };
      if (!payload.bot_token) delete payload.bot_token;
      if (!payload.sqlserver_password) delete payload.sqlserver_password;
      update.mutate({ ...(payload as TenantPayload), id: data.id });
    } else {
      create.mutate(data);
    }
  };

  const openEdit = (t: Tenant) => {
    setModal({
      id: t.id,
      name: t.name,
      slug: t.slug,
      bot_token: "",            // nunca pre-rellenamos el token real
      webhook_url: t.webhook_url,
      admin_chat_id: t.admin_chat_id,
      sqlserver_host: t.sqlserver_host ?? "",
      sqlserver_db: t.sqlserver_db ?? "",
      sqlserver_user: t.sqlserver_user ?? "",
      sqlserver_password: "",   // nunca pre-rellenamos la contraseña
      sqlserver_driver: t.sqlserver_driver ?? "ODBC Driver 18 for SQL Server",
      external_db: t.external_db_configured && t.external_db
        ? {
            engine: t.external_db.engine ?? "postgresql",
            host: t.external_db.host ?? "",
            port: t.external_db.port ?? 5432,
            database: t.external_db.database ?? "",
            user: t.external_db.user ?? "",
            password: "", // nunca pre-rellenamos la contraseña
            schema_description: t.external_db.schema_description,
          }
        : undefined,
      external_sheets: t.external_sheets_configured && t.external_sheets
        ? {
            spreadsheet_url: t.external_sheets.spreadsheet_url ?? "",
            credentials: undefined, // nunca pre-rellenamos las credenciales
            schema_description: t.external_sheets.schema_description,
          }
        : undefined,
    });
  };

  const saving = create.isPending || update.isPending;

  const saveError =
    (create.isError &&
      (create.error as unknown as {
        response?: { data?: { detail?: string } };
      })?.response?.data?.detail) ||
    (update.isError &&
      (update.error as unknown as {
        response?: { data?: { detail?: string } };
      })?.response?.data?.detail) ||
    (remove.isError &&
      (remove.error as unknown as {
        response?: { data?: { detail?: string } };
      })?.response?.data?.detail) ||
    "";

  return (
    <div>
      <PageHeader
        tag="MULTI-TENANT"
        title="Clientes"
        description={`${tenants.length} cliente${tenants.length !== 1 ? "s" : ""} registrado${tenants.length !== 1 ? "s" : ""}`}
        action={
          <button className="btn-primary flex items-center gap-2" onClick={() => setModal({ ...EMPTY })}>
            <Plus className="w-3.5 h-3.5" />
            NUEVO CLIENTE
          </button>
        }
      />

      <div className="px-8 py-8">

        {/* Error de mutación */}
        {(create.isError || update.isError || remove.isError) && (
          <div className="mb-4 px-4 py-3 border border-red-900 bg-red-950/30 font-mono text-xs text-red-400">
            {saveError || "Error al guardar. Verifica los datos e intenta de nuevo."}
          </div>
        )}

        <div className="border border-[#1a1a1a]">

          {/* Cabecera tabla */}
          <div className="grid grid-cols-[repeat(14,minmax(0,1fr))] bg-[#050505] border-b border-[#1a1a1a]">
            <div className="col-span-3 th">Cliente</div>
            <div className="col-span-2 th">Bot</div>
            <div className="col-span-2 th">SQL Server</div>
            <div className="col-span-2 th">DB Externa</div>
            <div className="col-span-1 th">Sheets</div>
            <div className="col-span-1 th">Webhook</div>
            <div className="col-span-1 th">Estado</div>
            <div className="col-span-1 th">Creado</div>
            <div className="col-span-1 th" />
          </div>

          {/* Skeleton */}
          {isLoading &&
            Array(3).fill(0).map((_, i) => (
              <div key={i} className="h-14 border-b border-[#111] animate-pulse" />
            ))}

          {/* Filas */}
          {!isLoading && tenants.map((t) => (
            <div key={t.id}>
              <div className="grid grid-cols-[repeat(14,minmax(0,1fr))] border-b border-[#111] hover:bg-[#050505] transition-colors">
              {/* Cliente */}
              <div className="col-span-3 td">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 border border-[#2a2a2a] flex items-center justify-center flex-shrink-0">
                    <span className="font-mono text-[11px] text-[#00e5a0]">
                      {t.name[0]?.toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-white leading-tight">{t.name}</p>
                    <p className="font-mono text-[10px] text-white">{t.slug}</p>
                  </div>
                </div>
              </div>

              {/* Bot token hint */}
              <div className="col-span-2 td">
                <span className="font-mono text-[11px] text-white bg-[#0a0a0a] px-2 py-0.5 border border-[#1a1a1a]">
                  ...{t.bot_token_hint}
                </span>
              </div>

              {/* SQL Server */}
              <div className="col-span-2 td">
                {t.sqlserver_host ? (
                  <div>
                    <p className="font-mono text-[11px] text-white truncate" title={t.sqlserver_host}>{t.sqlserver_host}</p>
                    <p className="font-mono text-[10px] text-white truncate" title={t.sqlserver_db}>{t.sqlserver_db}</p>
                  </div>
                ) : (
                  <span className="font-mono text-[11px] text-white">— sin configurar</span>
                )}
              </div>

              {/* DB Externa */}
              <div className="col-span-2 td">
                {t.external_db_configured ? (
                  <div>
                    <p className="font-mono text-[11px] text-white">
                      {t.external_db_engine ?? "postgresql"}
                    </p>
                    <p className="font-mono text-[10px] text-[#00e5a0]">✓ configurada</p>
                  </div>
                ) : (
                  <span className="font-mono text-[11px] text-white">— no configurada</span>
                )}
              </div>

              {/* Sheets */}
              <div className="col-span-1 td">
                {t.external_sheets_configured ? (
                  <div>
                    <p className="font-mono text-[10px] text-white truncate" title={t.external_sheets_spreadsheet}>
                      Sheets
                    </p>
                    <p className="font-mono text-[10px] text-[#00e5a0]">✓ configurada</p>
                  </div>
                ) : (
                  <span className="font-mono text-[11px] text-white">— no config</span>
                )}
              </div>

              {/* Webhook */}
              <div className="col-span-1 td">
                <span
                  className="font-mono text-[10px] text-white truncate block max-w-full"
                  title={t.webhook_url}
                >
                  {t.webhook_url.replace(/^https?:\/\//, "")}
                </span>
              </div>

              {/* Estado */}
              <div className="col-span-1 td">
                <span className={`badge ${t.is_active ? "badge-green" : "badge-slate"}`}>
                  {t.is_active ? "ON" : "OFF"}
                </span>
              </div>

              {/* Fecha */}
              <div className="col-span-1 td font-mono text-[11px] text-white">
                {fmtDateShort(t.created_at)}
              </div>

              {/* Acciones */}
              <div className="col-span-1 td">
                <div className="flex items-center gap-1 justify-end">
                  <button
                    onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
                    className={`p-1.5 transition-colors ${expandedId === t.id ? "text-[#00e5a0]" : "text-[#333] hover:text-[#00e5a0]"}`}
                    title="Gestionar accesos al panel"
                  >
                    <Users className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => openEdit(t)}
                    className="p-1.5 text-white hover:text-[#00e5a0] transition-colors"
                    title="Editar"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => toggle.mutate({ id: t.id, is_active: !t.is_active })}
                    className={`p-1.5 transition-colors ${
                      t.is_active
                        ? "text-white hover:text-yellow-500"
                        : "text-white hover:text-[#00e5a0]"
                    }`}
                    title={t.is_active ? "Desactivar" : "Activar"}
                  >
                    <Power className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() =>
                      window.confirm(`¿Eliminar el cliente "${t.name}"? Esta acción es irreversible.`) &&
                      remove.mutate(t.id)
                    }
                    className="p-1.5 text-white hover:text-red-500 transition-colors"
                    title="Eliminar"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
            {/* Panel de admins expandible */}
            {expandedId === t.id && (
              <TenantAdmins tenantId={t.id} tenantName={t.name} />
            )}
          </div>
          ))}

          {!isLoading && tenants.length === 0 && (
            <div className="px-5 py-16 text-center">
              <p className="font-mono text-xs text-white">SIN CLIENTES REGISTRADOS</p>
              <p className="font-mono text-[10px] text-white mt-2">
                Crea el primero con el botón "NUEVO CLIENTE"
              </p>
            </div>
          )}

        </div>

      </div>

      {/* Modal */}
      {modal && (
        <TenantModal
          initial={modal}
          onClose={() => setModal(null)}
          onSave={handleSave}
          saving={saving}
        />
      )}
    </div>
  );
}
