import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { UserX, UserCheck, Trash2 } from "lucide-react";
import api from "../lib/api";
import { fmtDateShort } from "../lib/utils";
import PageHeader from "../components/PageHeader";

export default function Usuarios() {
  const qc = useQueryClient();

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["usuarios"],
    queryFn: () => api.get("/usuarios").then((r) => r.data),
  });

  const { data: roles = [] } = useQuery({
    queryKey: ["roles"],
    queryFn: () => api.get("/roles").then((r) => r.data),
  });

  const toggle = useMutation({
    mutationFn: (chat_id: number) => api.patch(`/usuarios/${chat_id}/toggle`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["usuarios"] }),
  });

  const changeRole = useMutation({
    mutationFn: ({ chat_id, role_id }: { chat_id: number; role_id: number }) =>
      api.patch(`/usuarios/${chat_id}/rol`, { role_id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["usuarios"] }),
  });

  const remove = useMutation({
    mutationFn: (chat_id: number) => api.delete(`/usuarios/${chat_id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["usuarios"] }),
  });

  return (
    <div>
      <PageHeader tag="ACCESO" title="Usuarios" description={`${users.length} registrados`} />
      <div className="px-8 py-8">
        <div className="border border-[#1a1a1a]">
          <div className="grid grid-cols-12 bg-[#050505] border-b border-[#1a1a1a]">
            <div className="col-span-4 th">Usuario</div>
            <div className="col-span-2 th">Chat ID</div>
            <div className="col-span-2 th">Rol</div>
            <div className="col-span-1 th">Estado</div>
            <div className="col-span-2 th">Registrado</div>
            <div className="col-span-1 th" />
          </div>

          {isLoading
            ? Array(4).fill(0).map((_, i) => <div key={i} className="h-12 border-b border-[#111] animate-pulse" />)
            : users.map((u: any) => (
              <div key={u.chat_id} className="grid grid-cols-12 border-b border-[#111] hover:bg-[#050505] transition-colors">
                <div className="col-span-4 td">
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 border border-[#2a2a2a] flex items-center justify-center flex-shrink-0">
                      <span className="font-mono text-[10px] text-[#00e5a0]">
                        {(u.username || String(u.user_id))[0]?.toUpperCase()}
                      </span>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-white">{u.username || "—"}</p>
                      <p className="font-mono text-[10px] text-[#333]">uid {u.user_id}</p>
                    </div>
                  </div>
                </div>
                <div className="col-span-2 td font-mono text-xs text-[#555]">{u.chat_id}</div>
                <div className="col-span-2 td">
                  <select
                    className="bg-black border border-[#2a2a2a] text-xs text-white px-2 py-1 font-mono focus:outline-none focus:border-[#00e5a0] transition-colors"
                    value={u.role_id}
                    onChange={(e) => changeRole.mutate({ chat_id: u.chat_id, role_id: parseInt(e.target.value) })}
                  >
                    {roles.map((r: any) => <option key={r.id} value={r.id}>{r.name}</option>)}
                  </select>
                </div>
                <div className="col-span-1 td">
                  <span className={`badge ${u.is_active ? "badge-green" : "badge-slate"}`}>
                    {u.is_active ? "ON" : "OFF"}
                  </span>
                </div>
                <div className="col-span-2 td font-mono text-[11px] text-[#333]">{fmtDateShort(u.created_at)}</div>
                <div className="col-span-1 td">
                  <div className="flex items-center gap-1.5 justify-end">
                    <button
                      onClick={() => toggle.mutate(u.chat_id)}
                      className={`p-1.5 transition-colors ${u.is_active ? "text-[#333] hover:text-yellow-500" : "text-[#333] hover:text-[#00e5a0]"}`}
                    >
                      {u.is_active ? <UserX className="w-3.5 h-3.5" /> : <UserCheck className="w-3.5 h-3.5" />}
                    </button>
                    <button
                      onClick={() => window.confirm("¿Eliminar?") && remove.mutate(u.chat_id)}
                      className="p-1.5 text-[#333] hover:text-red-500 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))
          }
          {!isLoading && users.length === 0 && (
            <p className="px-5 py-10 text-center font-mono text-xs text-[#333]">SIN USUARIOS</p>
          )}
        </div>
      </div>
    </div>
  );
}
