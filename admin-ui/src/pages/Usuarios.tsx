import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { UserX, UserCheck, Trash2 } from "lucide-react";
import api from "../lib/api";
import { fmtDateShort } from "../lib/utils";
import { activeLabel } from "../lib/labels";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

export default function Usuarios() {
  const qc = useQueryClient();
  const { tenantId } = useTenant();
  const p = tenantId ? { tenant_id: tenantId } : undefined;

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["usuarios", tenantId],
    queryFn: () => api.get("/usuarios", { params: p }).then((r) => r.data),
    enabled: tenantId !== null,
  });

  const { data: roles = [] } = useQuery({
    queryKey: ["roles", tenantId],
    queryFn: () => api.get("/roles", { params: p }).then((r) => r.data),
    enabled: tenantId !== null,
  });

  const toggle = useMutation({
    mutationFn: (chat_id: number) => api.patch(`/usuarios/${chat_id}/toggle`, null, { params: p }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["usuarios", tenantId] }),
  });

  const changeRole = useMutation({
    mutationFn: ({ chat_id, role_id }: { chat_id: number; role_id: number }) =>
      api.patch(`/usuarios/${chat_id}/rol`, { role_id }, { params: p }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["usuarios", tenantId] }),
  });

  const remove = useMutation({
    mutationFn: (chat_id: number) => api.delete(`/usuarios/${chat_id}`, { params: p }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["usuarios", tenantId] }),
  });

  if (!tenantId) {
    return (
      <div>
        <PageHeader tag="ACCESO" title="Usuarios" description="Selecciona un cliente para ver sus usuarios" />
        <div className="px-5 py-16 sm:px-8 text-center">
          <p className="text-xs text-[var(--color-text)] uppercase tracking-[0.06em]">Selecciona un cliente en el panel izquierdo</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader tag="ACCESO" title="Usuarios" description={`${users.length} ${users.length === 1 ? "registrado" : "registrados"}`} />
      <div className="px-5 py-6 sm:px-8 sm:py-8">
        <div className="overflow-hidden rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface)]">
          <div className="grid grid-cols-[repeat(13,minmax(0,1fr))] bg-[var(--color-bg-elevated)] border-b border-[var(--color-border-subtle)]">
            <div className="col-span-3 th">Usuario</div>
            <div className="col-span-2 th">ID de Telegram</div>
            <div className="col-span-3 th">Rol</div>
            <div className="col-span-2 th">Estado</div>
            <div className="col-span-2 th">Registrado</div>
            <div className="col-span-1 th" />
          </div>

          {isLoading
            ? Array(4).fill(0).map((_, i) => <div key={i} className="h-12 border-b border-[var(--color-border-subtle)] animate-pulse" />)
            : users.map((u: any) => (
              <div key={u.chat_id} className="grid grid-cols-[repeat(13,minmax(0,1fr))] border-b border-[var(--color-border-subtle)] hover:bg-[var(--color-bg-elevated)] transition-colors">
                <div className="col-span-3 td">
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 border border-[var(--color-border)] flex items-center justify-center flex-shrink-0">
                      <span className="text-xs text-[var(--color-accent-strong)]">
                        {(u.username || String(u.user_id))[0]?.toUpperCase()}
                      </span>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-[var(--color-text)]">{u.username || "—"}</p>
                      <p className="text-2xs text-[var(--color-text-subtle)]">ID de usuario: {u.user_id}</p>
                    </div>
                  </div>
                </div>
                <div className="col-span-2 td text-xs text-[var(--color-text)]">{u.chat_id}</div>
                <div className="col-span-3 td">
                  <select
                    className="w-full bg-[var(--color-bg)] border border-[var(--color-border)] text-xs text-[var(--color-text)] px-2 py-1 focus:outline-none focus:border-accent transition-colors"
                    value={u.role_id}
                    onChange={(e) => changeRole.mutate({ chat_id: u.chat_id, role_id: parseInt(e.target.value) })}
                  >
                    {roles.map((r: any) => <option key={r.id} value={r.id}>{r.description || r.name}</option>)}
                  </select>
                </div>
                <div className="col-span-2 td">
                  <span className={`badge ${u.is_active ? "badge-green" : "badge-slate"}`}>
                    {activeLabel(u.is_active)}
                  </span>
                </div>
                <div className="col-span-2 td text-xs text-[var(--color-text)]">{fmtDateShort(u.created_at)}</div>
                <div className="col-span-1 td">
                  <div className="flex items-center gap-1.5 justify-end">
                    <button onClick={() => toggle.mutate(u.chat_id)}
                      className={`p-1.5 transition-colors ${u.is_active ? "text-[var(--color-text)] hover:text-amber-700" : "text-[var(--color-text)] hover:text-[var(--color-accent-strong)]"}`}>
                      {u.is_active ? <UserX className="w-3.5 h-3.5" /> : <UserCheck className="w-3.5 h-3.5" />}
                    </button>
                    <button onClick={() => window.confirm("¿Eliminar?") && remove.mutate(u.chat_id)}
                      className="p-1.5 text-[var(--color-text)] hover:text-red-700 transition-colors">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))
          }
          {!isLoading && users.length === 0 && (
            <p className="px-5 py-10 text-center text-xs text-[var(--color-text)]">Aún no hay usuarios</p>
          )}
        </div>
      </div>
    </div>
  );
}
