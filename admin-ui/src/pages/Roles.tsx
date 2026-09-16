import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus } from "lucide-react";
import api from "../lib/api";
import PageHeader from "../components/PageHeader";

const ALL_PERMISSIONS = ["READ_SALES","READ_KPI","READ_FINANCE","GENERATE_REPORT","MANAGE_TASKS"];
const PERM_LABELS: Record<string, string> = {
  READ_SALES: "VER VENTAS", READ_KPI: "VER KPIS",
  READ_FINANCE: "VER FINANZAS", GENERATE_REPORT: "INFORMES", MANAGE_TASKS: "TAREAS",
};

export default function Roles() {
  const qc = useQueryClient();
  const [newRole, setNewRole] = useState({ name: "", description: "" });
  const [creating, setCreating] = useState(false);

  const { data: roles = [], isLoading } = useQuery({
    queryKey: ["roles"],
    queryFn: () => api.get("/roles").then((r) => r.data),
  });

  const updatePerms = useMutation({
    mutationFn: ({ role_id, permissions }: { role_id: number; permissions: string[] }) =>
      api.put(`/roles/${role_id}/permisos`, { permissions }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }),
  });

  const createRole = useMutation({
    mutationFn: (body: { name: string; description: string }) => api.post("/roles", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["roles"] });
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

  return (
    <div>
      <PageHeader
        tag="PERMISOS"
        title="Roles"
        description="Controla qué puede hacer cada rol"
        action={
          <button className="btn-primary flex items-center gap-2" onClick={() => setCreating(!creating)}>
            <Plus className="w-3 h-3" /> NUEVO ROL
          </button>
        }
      />
      <div className="px-8 py-8 space-y-4">

        {creating && (
          <div className="border border-[#00e5a0]/20 bg-[#050505] p-5">
            <p className="section-tag mb-4">// NUEVO ROL</p>
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
          ? <div className="border border-[#1a1a1a] h-40 animate-pulse" />
          : roles.map((role: any) => (
            <div key={role.id} className="border border-[#1a1a1a]">
              <div className="px-5 py-3 bg-[#050505] border-b border-[#1a1a1a] flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="font-bold text-white">{role.name}</span>
                  {role.description && <span className="font-mono text-[11px] text-[#444]">{role.description}</span>}
                </div>
                <span className="font-mono text-[10px] text-[#333]">ID {role.id}</span>
              </div>
              <div className="p-5 flex flex-wrap gap-2">
                {ALL_PERMISSIONS.map((perm) => {
                  const active = (role.permissions ?? []).includes(perm);
                  return (
                    <button
                      key={perm}
                      onClick={() => toggle(role, perm)}
                      className={`font-mono text-[10px] uppercase tracking-widest px-3 py-1.5 border transition-all ${
                        active
                          ? "border-[#00e5a0] text-[#00e5a0] bg-[#00e5a0]/5"
                          : "border-[#2a2a2a] text-[#444] hover:border-[#444]"
                      }`}
                    >
                      {active ? "✓ " : ""}{PERM_LABELS[perm]}
                    </button>
                  );
                })}
              </div>
            </div>
          ))
        }
      </div>
    </div>
  );
}
