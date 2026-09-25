import { useQuery } from "@tanstack/react-query";
import api from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

const EVENT_BADGE: Record<string, string> = {
  interaction: "badge-indigo", tool_failure: "badge-red",
  unauthorized: "badge-amber", scheduler: "badge-slate",
};

export default function Dashboard() {
  const { tenantId } = useTenant();

  const { data, isLoading } = useQuery({
    queryKey: ["dashboard", tenantId],
    queryFn: () => api.get("/dashboard", { params: tenantId ? { tenant_id: tenantId } : {} }).then((r) => r.data),
    refetchInterval: 30000,
  });

  return (
    <div>
      <PageHeader tag="SISTEMA" title="Dashboard" description="Estado general en tiempo real" />
      <div className="px-8 py-8 space-y-8">

        <div className="grid grid-cols-2 xl:grid-cols-5 gap-px bg-[#1a1a1a]">
          {isLoading
            ? Array(5).fill(0).map((_, i) => <div key={i} className="bg-black p-6 h-24 animate-pulse" />)
            : [
                { label: "Usuarios", value: data?.stats.total_users, accent: false },
                { label: "Solicitudes pendientes", value: data?.stats.pending_requests, accent: data?.stats.pending_requests > 0 },
                { label: "Interacciones", value: data?.stats.total_interactions, accent: false },
                { label: "Tareas activas", value: data?.stats.active_tasks, accent: false },
                { label: "Errores", value: data?.stats.errors_today, accent: data?.stats.errors_today > 0 },
              ].map(({ label, value, accent }) => (
                <div key={label} className="bg-black p-6">
                  <p className="font-mono text-[10px] uppercase tracking-widest text-[#999] mb-3">{label}</p>
                  <p className={`text-3xl font-bold ${accent ? "text-[#00e5a0]" : "text-white"}`}>{value ?? "—"}</p>
                </div>
              ))
          }
        </div>

        <div>
          <p className="section-tag mb-4">// Actividad reciente</p>
          <div className="border border-[#1a1a1a]">
            <div className="grid grid-cols-12 border-b border-[#1a1a1a] bg-[#050505]">
              <div className="col-span-2 th">Evento</div>
              <div className="col-span-6 th">Mensaje</div>
              <div className="col-span-2 th">Estado</div>
              <div className="col-span-2 th">Hora</div>
            </div>
            {isLoading
              ? Array(5).fill(0).map((_, i) => <div key={i} className="h-10 border-b border-[#111] bg-[#050505] animate-pulse" />)
              : data?.recent_logs?.length === 0
              ? <p className="px-5 py-8 font-mono text-xs text-[#333] text-center">SIN ACTIVIDAD</p>
              : data?.recent_logs?.map((log: any) => (
                  <div key={log.id} className="grid grid-cols-12 border-b border-[#111] hover:bg-[#050505] transition-colors">
                    <div className="col-span-2 td">
                      <span className={`badge ${EVENT_BADGE[log.event_type] ?? "badge-slate"}`}>{log.event_type}</span>
                    </div>
                    <div className="col-span-6 td truncate text-[#888]">
                      {log.request_content || log.tool_invoked || "—"}
                    </div>
                    <div className="col-span-2 td">
                      {log.status && (
                        <span className={`font-mono text-[10px] uppercase tracking-widest ${log.status === "success" ? "text-[#00e5a0]" : "text-red-500"}`}>
                          {log.status}
                        </span>
                      )}
                    </div>
                    <div className="col-span-2 td font-mono text-[11px] text-[#aaa]">{fmtDate(log.timestamp_utc)}</div>
                  </div>
                ))
            }
          </div>
        </div>

      </div>
    </div>
  );
}
