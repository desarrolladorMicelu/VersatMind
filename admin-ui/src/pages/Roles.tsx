import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, Lock, Unlock } from "lucide-react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

const ALL_PERMISSIONS = [
  "READ_SALES", "READ_KPI", "READ_FINANCE", "GENERATE_REPORT", "MANAGE_TASKS",
  "READ_EXTERNAL_DB", "READ_MAIL", "READ_CALENDAR", "READ_CUSTOMER_PII",
];

const PERM_LABELS: Record<string, string> = {
  READ_SALES: "VER VENTAS",
  READ_KPI: "VER KPIS",
  READ_FINANCE: "VER FINANZAS",
  GENERATE_REPORT: "INFORMES",
  MANAGE_TASKS: "TAREAS",
  READ_EXTERNAL_DB: "DB EXTERNA",
  READ_MAIL: "CORREO",
  READ_CALENDAR: "CALENDARIO",
  READ_CUSTOMER_PII: "DATOS PERSONALES",
};

const SOURCE_GROUP_LABELS: Record<string, string> = {
  ofima_table: "OFIMA · tablas",
  external_db: "Base de datos externa",
  external_db_table: "Base de datos externa · tablas",
  sheets: "Google Sheets",
  excel: "Excel",
  alegra: "Alegra",
  mail: "Correo",
  calendar: "Calendario",
  knowledge: "Base de conocimiento",
};

interface DataSource {
  id: number;
  kind: string;
  source_key: string;
  display_name: string;
  is_active: boolean;
}

interface Role {
  id: number;
  name: string;
  description: string | null;
  permissions: string[];
  source_ids: number[];
  sources_restricted: boolean;
}

export default function Roles() {
  const qc = useQueryClient();
  const { tenantId } = useTenant();
  const p = tenantId ? { tenant_id: tenantId } : undefined;
  const [newRole, setNewRole] = useState({ name: "", description: "" });
  const [creating, setCreating] = useState(false);

  const { data: roles = [], isLoading } = useQuery<Role[]>({
    queryKey: ["roles", tenantId],
    queryFn: () => api.get("/roles", { params: p }).then((r) => r.data),
    enabled: tenantId !== null,
  });

  const { data: sources = [] } = useQuery<DataSource[]>({
    queryKey: ["data-sources", tenantId],
    queryFn: () => api.get("/data-sources", { params: p }).then((r) => r.data),
    enabled: tenantId !== null,
  });

  const updatePerms = useMutation({
    mutationFn: ({ role_id, permissions }: { role_id: number; permissions: string[] }) =>
      api.put(`/roles/${role_id}/permisos`, { permissions }, { params: p }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles", tenantId] }),
  });

  const updateSources = useMutation({
    mutationFn: ({ role_id, restricted, source_ids }: {
      role_id: number; restricted: boolean; source_ids: number[];
    }) => api.put(`/roles/${role_id}/fuentes`, { restricted, source_ids }, { params: p }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles", tenantId] }),
  });

  const createRole = useMutation({
    mutationFn: (body: { name: string; description: string }) =>
      api.post("/roles", body, { params: p }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["roles", tenantId] });
      setNewRole({ name: "", description: "" });
      setCreating(false);
    },
  });

  const toggle = (role: Role, perm: string) => {
    const current = role.permissions ?? [];
    updatePerms.mutate({
      role_id: role.id,
      permissions: current.includes(perm) ? current.filter((x) => x !== perm) : [...current, perm],
    });
  };

  const toggleSource = (role: Role, sourceId: number) => {
    const current = new Set(role.source_ids ?? []);
    if (current.has(sourceId)) current.delete(sourceId); else current.add(sourceId);
    updateSources.mutate({
      role_id: role.id, restricted: true, source_ids: [...current],
    });
  };

  const restrictSources = (role: Role) => {
    updateSources.mutate({
      role_id: role.id,
      restricted: true,
      source_ids: sources.filter((s) => s.is_active).map((s) => s.id),
    });
  };

  const allowAllSources = (role: Role) => {
    updateSources.mutate({ role_id: role.id, restricted: false, source_ids: [] });
  };

  if (!tenantId) {
    return (
      <div>
        <PageHeader tag="PERMISOS" title="Roles" description="Selecciona un cliente" />
        <div className="px-5 py-16 sm:px-8 text-center">
          <p className="text-sm text-[var(--color-text-subtle)]">Selecciona un cliente en el panel izquierdo</p>
        </div>
      </div>
    );
  }

  const groupedSources = Object.entries(SOURCE_GROUP_LABELS)
    .map(([kind, label]) => ({ kind, label, items: sources.filter((s) => s.kind === kind) }))
    .filter((g) => g.items.length > 0);

  return (
    <div>
      <PageHeader
        tag="PERMISOS"
        title="Roles"
        description="Define qué datos y funciones puede usar cada rol"
        action={
          <button className="btn-primary flex items-center gap-2" onClick={() => setCreating(!creating)}>
            <Plus className="w-3.5 h-3.5" /> NUEVO ROL
          </button>
        }
      />

      <div className="space-y-4 px-5 py-6 sm:px-8 sm:py-8">

        {creating && (
          <div className="rounded-xl border border-[var(--color-accent-border)] bg-[var(--color-surface)] p-5">
            <p className="section-tag mb-4">NUEVO ROL</p>
            <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="label">Nombre del rol</label>
                <input
                  className="input"
                  placeholder="Ej: Comercial"
                  value={newRole.name}
                  onChange={(e) => setNewRole({ ...newRole, name: e.target.value })}
                />
              </div>
              <div>
                <label className="label">Descripción</label>
                <input
                  className="input"
                  placeholder="Opcional"
                  value={newRole.description}
                  onChange={(e) => setNewRole({ ...newRole, description: e.target.value })}
                />
              </div>
            </div>
            <div className="flex gap-2">
              <button className="btn-primary" onClick={() => createRole.mutate(newRole)} disabled={!newRole.name}>
                CREAR
              </button>
              <button className="btn-secondary" onClick={() => setCreating(false)}>CANCELAR</button>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="h-40 animate-pulse rounded-xl border border-[var(--color-border-subtle)]" />
        ) : (
          roles.map((role) => {
            const restricted = role.sources_restricted;
            const allowed = new Set(role.source_ids ?? []);
            return (
              <div key={role.id} className="overflow-hidden rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface)]">
                <div className="flex items-center justify-between gap-3 border-b border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] px-5 py-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-[var(--color-text)]">{role.name}</p>
                    {role.description && (
                      <p className="mt-0.5 text-xs text-[var(--color-text-subtle)]">{role.description}</p>
                    )}
                  </div>
                </div>

                <div className="border-b border-[var(--color-border-subtle)] p-5">
                  <p className="mb-3 text-2xs font-semibold uppercase tracking-[0.08em] text-[var(--color-text-subtle)]">
                    Funciones permitidas
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {ALL_PERMISSIONS.map((perm) => {
                      const active = (role.permissions ?? []).includes(perm);
                      return (
                        <button
                          key={perm}
                          onClick={() => toggle(role, perm)}
                          className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                            active
                              ? "border-[var(--color-accent-border)] bg-[var(--color-accent-surface)] text-[var(--color-accent-strong)]"
                              : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-border-strong)]"
                          }`}
                        >
                          {PERM_LABELS[perm] ?? perm}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="p-5">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <p className="text-2xs font-semibold uppercase tracking-[0.08em] text-[var(--color-text-subtle)]">
                      Fuentes de datos
                    </p>
                    {restricted ? (
                      <button
                        className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-accent-strong)] hover:underline"
                        onClick={() => allowAllSources(role)}
                      >
                        <Unlock className="h-3.5 w-3.5" /> Permitir todas
                      </button>
                    ) : (
                      <button
                        className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] disabled:cursor-not-allowed disabled:opacity-40"
                        onClick={() => restrictSources(role)}
                        disabled={sources.filter((s) => s.is_active).length === 0}
                      >
                        <Lock className="h-3.5 w-3.5" /> Restringir fuentes
                      </button>
                    )}
                  </div>

                  {!restricted ? (
                    <div className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg)] px-4 py-3">
                      <p className="text-xs text-[var(--color-text-muted)]">
                        Acceso completo a todas las fuentes configuradas del cliente.
                        Restringe las fuentes para limitar tablas o conectores específicos.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {groupedSources.map((group) => (
                        <div key={group.kind}>
                          <p className="mb-1.5 text-2xs text-[var(--color-text-subtle)]">{group.label}</p>
                          <div className="flex flex-wrap gap-1.5">
                            {group.items.map((source) => {
                              const active = allowed.has(source.id);
                              return (
                                <button
                                  key={source.id}
                                  onClick={() => toggleSource(role, source.id)}
                                  disabled={!source.is_active}
                                  title={source.is_active ? source.source_key : "Integración no configurada"}
                                  className={`rounded border px-2.5 py-1 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                                    active
                                      ? "border-[var(--color-accent-border)] bg-[var(--color-accent-surface)] text-[var(--color-accent-strong)]"
                                      : "border-[var(--color-border)] text-[var(--color-text-subtle)] hover:text-[var(--color-text)]"
                                  }`}
                                >
                                  {source.display_name}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                      {groupedSources.length === 0 && (
                        <p className="text-xs text-[var(--color-text-subtle)]">
                          Este cliente todavía no tiene fuentes configuradas.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}

        {!isLoading && roles.length === 0 && (
          <p className="py-10 text-center text-sm text-[var(--color-text-subtle)]">
            Aún no hay roles. Crea el primero.
          </p>
        )}
      </div>
    </div>
  );
}
