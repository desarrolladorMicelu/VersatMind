import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus } from "lucide-react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

const ALL_PERMISSIONS = [
  "READ_SALES","READ_KPI","READ_FINANCE","GENERATE_REPORT","MANAGE_TASKS",
  "READ_EXTERNAL_DB","READ_MAIL","READ_CALENDAR",
];
const PERM_LABELS: Record<string, string> = {
  READ_SALES: "VER VENTAS", READ_KPI: "VER KPIS",
  READ_FINANCE: "VER FINANZAS", GENERATE_REPORT: "INFORMES", MANAGE_TASKS: "TAREAS",
  READ_EXTERNAL_DB: "DB EXTERNA", READ_MAIL: "CORREO", READ_CALENDAR: "CALENDARIO",
};

export default function Roles() {
  const qc = useQueryClient();
  const { tenantId } = useTenant();
  const p = tenantId ? { tenant_id: tenantId } : undefined;
  const [newRole, setNewRole] = useState({ name: "", description: "" });
  const [creating, setCreating] = useState(false);

  const { data: roles = [], isLoading } = useQuery({
    queryKey: ["roles", tenantId],
    queryFn: () => api.get("/roles", { params: p }).then((r) => r.data),
    enabled: tenantId !== null,
  });

  const updatePerms = useMutation({
    mutationFn: ({ role_id, permissions }: { role_id: number; permissions: string[] }) =>
      api.put(`/roles/${role_id}/permisos`, { permissions }),
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

  const toggle = (role: any, perm: string) => {
    const current: string[] = role.permissions ?? [];
    updatePerms.mutate({
      role_id: role.id,
      permissions: current.includes(perm) ? current.filter((p) => p !== perm) : [...current, perm],
    });
  };

  if (!tenantId) {
    return (
      <div>
        <PageHeader tag="PERMISOS" title="Roles" description="Selecciona un cliente" />
        <div className="px-5 py-16 sm:px-8 text-center">
          <p className="text-xs text-[var(--color-text)] uppercase tracking-[0.06em]">Selecciona un cliente en el panel izquierdo</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        tag="PERMISOS" title="Roles" description="Controla qué puede hacer cada rol"
        action={
          <button className="btn-primary flex items-center gap-2" onClick={() => setCreating(!creating)}>
            <Plus className="w-3 h-3" /> NUEVO ROL
          </button>
        }
      />
      <div className="px-5 py-6 sm:px-8 sm:py-8 space-y-4">

        {creating && (
          <div className="border border-accent/20 bg-[var(--color-bg-elevated)] p-5">
            <p className="section-tag mb-4">NUEVO ROL</p>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="label">Nombre del rol</label>
                <input className="input" placeholder="analyst" value={newRole.name}
                  onChange={(e) => setNewRole({ ...newRole, name: e.target.value })} />
              </div>
              <div>
                <label className="label">Descripción</label>
                <input className="input" placeholder="Opcional" value={newRole.description}
                  onChange={(e) => setNewRole({ ...newRole, description: e.target.value })} />
              </div>
            </div>
            <div className="flex gap-2">
              <button className="btn-primary" onClick={() => createRole.mutate(newRole)} disabled={!newRole.name}>CREAR →</button>
              <button className="btn-secondary" onClick={() => setCreating(false)}>CANCELAR</button>
            </div>
          </div>
        )}

        {isLoading
          ? <div className="rounded-xl border border-[var(--color-border-subtle)] h-40 animate-pulse" />
          : roles.map((role: any) => (
            <div key={role.id} className="rounded-xl border border-[var(--color-border-subtle)]">
              <div className="px-5 py-3 bg-[var(--color-bg-elevated)] border-b border-[var(--color-border-subtle)] flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="font-bold text-[var(--color-text)]">{role.name}</span>
                  {role.description && <span className="text-xs text-[var(--color-text)]">{role.description}</span>}
                </div>
                <span className="text-xs text-[var(--color-text)]">ID {role.id}</span>
              </div>
              <div className="p-5 flex flex-wrap gap-2">
                {ALL_PERMISSIONS.map((perm) => {
                  const active = (role.permissions ?? []).includes(perm);
                  return (
                    <button key={perm} onClick={() => toggle(role, perm)}
                      className={`text-xs uppercase tracking-[0.06em] px-3 py-1.5 border transition-all ${
                        active ? "border-accent text-accent bg-accent/5" : "border-[var(--color-border)] text-[var(--color-text)] hover:border-[var(--color-text-subtle)]"
                      }`}>
                      {active ? "✓ " : ""}{PERM_LABELS[perm] ?? perm}
                    </button>
                  );
                })}
              </div>
            </div>
          ))
        }
        {!isLoading && roles.length === 0 && (
          <p className="text-center text-xs text-[var(--color-text)] py-10">SIN ROLES — CREA UNO</p>
        )}
      </div>
    </div>
  );
}
