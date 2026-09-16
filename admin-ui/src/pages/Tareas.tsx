import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Power, Trash2 } from "lucide-react";
import api from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";

export default function Tareas() {
  const qc = useQueryClient();

  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ["tareas"],
    queryFn: () => api.get("/tareas").then((r) => r.data),
  });

  const toggle = useMutation({
    mutationFn: (id: string) => api.patch(`/tareas/${id}/toggle`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tareas"] }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/tareas/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tareas"] }),
  });

  const active = tasks.filter((t: any) => t.status === "active").length;

  return (
    <div>
      <PageHeader tag="SCHEDULER" title="Tareas" description={`${active} activas`} />
      <div className="px-8 py-8">
        <div className="border border-[#1a1a1a]">
          <div className="grid grid-cols-12 bg-[#050505] border-b border-[#1a1a1a]">
            <div className="col-span-4 th">Descripción</div>
            <div className="col-span-2 th">Chat ID</div>
            <div className="col-span-2 th">Cron</div>
            <div className="col-span-1 th">Estado</div>
            <div className="col-span-2 th">Última ejec.</div>
            <div className="col-span-1 th" />
          </div>

          {isLoading
            ? Array(3).fill(0).map((_, i) => <div key={i} className="h-12 border-b border-[#111] animate-pulse" />)
            : tasks.map((t: any) => (
              <div key={t.id} className="grid grid-cols-12 border-b border-[#111] hover:bg-[#050505] transition-colors items-center">
                <div className="col-span-4 td">
                  <p className="text-sm text-white">{t.description}</p>
                  <p className="font-mono text-[10px] text-[#333]">{t.id.slice(0, 8)}…</p>
                </div>
                <div className="col-span-2 td font-mono text-xs text-[#555]">{t.chat_id}</div>
                <div className="col-span-2 td">
                  <code className="font-mono text-[11px] text-[#00e5a0] bg-[#00e5a0]/5 px-2 py-0.5 border border-[#00e5a0]/10">
                    {t.cron_expression}
                  </code>
                </div>
                <div className="col-span-1 td">
                  <span className={`badge ${t.status === "active" ? "badge-green" : "badge-slate"}`}>
                    {t.status === "active" ? "ON" : "OFF"}
                  </span>
                </div>
                <div className="col-span-2 td font-mono text-[11px] text-[#333]">{fmtDate(t.last_execution_at)}</div>
                <div className="col-span-1 td">
                  <div className="flex items-center gap-1.5 justify-end">
                    <button
                      onClick={() => toggle.mutate(t.id)}
                      className={`p-1.5 transition-colors ${t.status === "active" ? "text-[#333] hover:text-yellow-500" : "text-[#333] hover:text-[#00e5a0]"}`}
                    >
                      <Power className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => window.confirm("¿Eliminar?") && remove.mutate(t.id)}
                      className="p-1.5 text-[#333] hover:text-red-500 transition-colors">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))
          }
          {!isLoading && tasks.length === 0 && (
            <p className="px-5 py-10 text-center font-mono text-xs text-[#333]">SIN TAREAS</p>
          )}
        </div>
      </div>
    </div>
  );
}
