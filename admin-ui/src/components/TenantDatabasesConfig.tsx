import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Pencil, Plus, Trash2, X, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { tenantDatabasesApi } from "../lib/api";
import type { TenantDatabaseInfo, TenantDatabasePayload } from "../lib/api";

const EMPTY: TenantDatabasePayload = {
  alias: "",
  label: "",
  engine: "postgresql",
  host: "",
  port: 5432,
  database: "",
  user: "",
  password: "",
  schema_name: "public",
  tables: [],
  schema_description: null,
  is_active: true,
};

function DatabaseModal({
  tenantId,
  initial,
  onClose,
  onSaved,
}: {
  tenantId: number;
  initial: TenantDatabaseInfo | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<TenantDatabasePayload>(() => initial ? {
    alias: initial.alias,
    label: initial.label,
    engine: initial.engine,
    host: initial.host,
    port: initial.port,
    database: initial.database,
    user: initial.user,
    password: "",
    schema_name: initial.schema_name,
    tables: initial.tables,
    schema_description: initial.schema_description,
    is_active: initial.is_active,
  } : { ...EMPTY });
  const [tablesText, setTablesText] = useState((initial?.tables ?? []).join(", "));
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const set = (k: keyof TenantDatabasePayload, v: string | number | boolean) =>
    setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setError("");
    setBusy(true);
    try {
      const payload = {
        ...form,
        tables: tablesText.split(",").map((t) => t.trim()).filter(Boolean),
      };
      if (initial) await tenantDatabasesApi.update(tenantId, initial.id, payload);
      else await tenantDatabasesApi.create(tenantId, payload);
      onSaved();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "No se pudo guardar la base de datos.");
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setStatus("testing");
    setError("");
    try {
      const r = await tenantDatabasesApi.test(tenantId, {
        ...form,
        tables: tablesText.split(",").map((t) => t.trim()).filter(Boolean),
      });
      if (r.ok) setStatus("ok");
      else { setStatus("error"); setError(r.error ?? "No se pudo conectar."); }
    } catch (e: any) {
      setStatus("error");
      setError(e?.response?.data?.detail ?? "No se pudo conectar.");
    }
  };

  const discover = async () => {
    setStatus("discovering");
    setError("");
    try {
      const r = await tenantDatabasesApi.discover(tenantId, {
        ...form,
        tables: tablesText.split(",").map((t) => t.trim()).filter(Boolean),
      });
      if (r.schema_description !== undefined) {
        setForm((f) => ({ ...f, schema_description: r.schema_description }));
        setStatus("ok");
      } else {
        setStatus("error");
        setError(r.error ?? "No se pudo detectar el esquema.");
      }
    } catch (e: any) {
      setStatus("error");
      setError(e?.response?.data?.detail ?? "No se pudo detectar el esquema.");
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl">
        <div className="flex items-start justify-between border-b border-[var(--color-border-subtle)] px-5 py-4">
          <div>
            <p className="section-tag mb-1">{initial ? "EDITAR BASE" : "NUEVA BASE DE DATOS"}</p>
            <h3 className="text-lg font-semibold tracking-tight text-[var(--color-text)]">
              {initial ? initial.alias : "Base PostgreSQL adicional"}
            </h3>
          </div>
          <button className="vc-icon-btn" onClick={onClose}><X className="h-4 w-4" /></button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="label">Alias</label>
              <input className="input font-mono text-xs" placeholder="micelu_pg" value={form.alias}
                disabled={!!initial}
                onChange={(e) => set("alias", e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))} />
              <p className="mt-1 text-2xs text-[var(--color-text-subtle)]">Así la llamará la IA. No cambia después.</p>
            </div>
            <div>
              <label className="label">Nombre visible</label>
              <input className="input" placeholder="Base MICELU" value={form.label}
                onChange={(e) => set("label", e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="label">Host</label>
              <input className="input" value={form.host} onChange={(e) => set("host", e.target.value)} />
            </div>
            <div>
              <label className="label">Puerto</label>
              <input className="input" type="number" value={form.port} onChange={(e) => set("port", Number(e.target.value))} />
            </div>
            <div>
              <label className="label">Base de datos</label>
              <input className="input" value={form.database} onChange={(e) => set("database", e.target.value)} />
            </div>
            <div>
              <label className="label">Usuario</label>
              <input className="input" value={form.user} onChange={(e) => set("user", e.target.value)} />
            </div>
            <div>
              <label className="label">Contraseña {initial && "(vacío = conservar)"}</label>
              <input className="input" type="password" value={form.password} onChange={(e) => set("password", e.target.value)} />
            </div>
            <div>
              <label className="label">Schema</label>
              <input className="input" value={form.schema_name} onChange={(e) => set("schema_name", e.target.value)} />
            </div>
          </div>

          <div>
            <label className="label">Tablas (separadas por coma)</label>
            <input className="input font-mono text-xs" placeholder="ventas, clientes, productos"
              value={tablesText} onChange={(e) => setTablesText(e.target.value)} />
          </div>

          <div>
            <label className="label">Descripción del esquema (opcional)</label>
            <textarea className="input font-mono text-xs" rows={4} value={form.schema_description ?? ""}
              onChange={(e) => set("schema_description", e.target.value)}
              placeholder="Puedes detectarlo automáticamente o pegar columnas aquí." />
          </div>

          <label className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
            <input type="checkbox" checked={form.is_active} onChange={(e) => set("is_active", e.target.checked)} />
            Activa
          </label>

          {error && (
            <div className="flex items-start gap-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-2xs text-red-700">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" /> {error}
            </div>
          )}
          {status === "ok" && (
            <p className="flex items-center gap-1.5 text-2xs text-[var(--color-accent-strong)]">
              <CheckCircle2 className="h-3.5 w-3.5" /> Conexión/esquema correcto
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--color-border-subtle)] px-5 py-3">
          <div className="flex gap-2">
            <button className="btn-secondary px-3 py-2 text-2xs" onClick={test} disabled={status === "testing"}>
              {status === "testing" ? "PROBANDO..." : "PROBAR"}
            </button>
            <button className="btn-secondary px-3 py-2 text-2xs" onClick={discover} disabled={status === "discovering"}>
              {status === "discovering" ? "DETECTANDO..." : "DETECTAR ESQUEMA"}
            </button>
          </div>
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={onClose}>CANCELAR</button>
            <button className="btn-primary" onClick={save} disabled={busy || !form.alias || !form.host || !form.database}>
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "GUARDAR"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function TenantDatabasesConfig({ tenantId }: { tenantId?: number }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<TenantDatabaseInfo | null | undefined>(undefined);
  const { data: databases = [], isLoading } = useQuery({
    queryKey: ["tenant-databases", tenantId],
    queryFn: () => tenantDatabasesApi.list(tenantId as number),
    enabled: !!tenantId,
  });
  const remove = useMutation({
    mutationFn: (id: number) => tenantDatabasesApi.remove(tenantId as number, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenant-databases", tenantId] }),
  });

  return (
    <div className="border-t border-[var(--color-border-subtle)] pt-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-[var(--color-accent-strong)]" />
          <div>
            <p className="section-tag mb-0.5">BASES DE DATOS ADICIONALES</p>
            <p className="text-xs text-[var(--color-text-subtle)]">
              Agrega más PostgreSQL por tienda. La base principal sigue en la sección anterior.
            </p>
          </div>
        </div>
        {tenantId && (
          <button className="btn-secondary flex items-center gap-1.5 px-3 py-2 text-2xs" onClick={() => setEditing(null)}>
            <Plus className="h-3.5 w-3.5" /> AGREGAR
          </button>
        )}
      </div>

      {!tenantId ? (
        <p className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg)] px-3 py-2 text-xs text-[var(--color-text-subtle)]">
          Guarda el cliente primero y luego agrega sus bases adicionales.
        </p>
      ) : isLoading ? (
        <div className="h-16 animate-pulse rounded-lg border border-[var(--color-border-subtle)]" />
      ) : databases.length === 0 ? (
        <p className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg)] px-3 py-2 text-xs text-[var(--color-text-subtle)]">
          Sin bases adicionales. Puedes agregar las que necesites.
        </p>
      ) : (
        <div className="space-y-2">
          {databases.map((db) => (
            <div key={db.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg)] px-3 py-2">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-[var(--color-text)]">{db.alias}</span>
                  <span className={`badge ${db.is_active ? "badge-green" : "badge-slate"}`}>{db.is_active ? "Activa" : "Inactiva"}</span>
                </div>
                <p className="truncate text-2xs text-[var(--color-text-subtle)]">
                  {db.label || db.alias} · {db.host}:{db.port}/{db.database} · {db.tables.length} tablas
                </p>
              </div>
              <div className="flex items-center gap-1">
                <button className="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-accent-strong)]" onClick={() => setEditing(db)} title="Editar">
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                <button className="p-1.5 text-[var(--color-text-muted)] hover:text-red-700"
                  onClick={() => window.confirm(`¿Eliminar la base ${db.alias}?`) && remove.mutate(db.id)} title="Eliminar">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {tenantId && editing !== undefined && (
        <DatabaseModal
          tenantId={tenantId}
          initial={editing}
          onClose={() => setEditing(undefined)}
          onSaved={() => {
            setEditing(undefined);
            qc.invalidateQueries({ queryKey: ["tenant-databases", tenantId] });
            qc.invalidateQueries({ queryKey: ["data-sources", tenantId] });
            qc.invalidateQueries({ queryKey: ["roles", tenantId] });
          }}
        />
      )}
    </div>
  );
}
