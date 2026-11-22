import { useQuery } from "@tanstack/react-query";
import api from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

const EVENT_BADGE: Record<string, string> = {
  interaction: "badge-indigo", tool_failure: "badge-red",
  unauthorized: "badge-amber", scheduler: "badge-slate",
};

interface ActivityLog {
  id: number;
  event_type: string;
  request_content?: string | null;
  tool_invoked?: string | null;
  status?: string | null;
  timestamp_utc: string;
}

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
      <div className="px-5 py-6 sm:px-8 sm:py-8 space-y-8">

        <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
          {isLoading
            ? Array(5).fill(0).map((_, i) => (
                <div key={i} className="h-[104px] animate-pulse rounded-xl border border-[#1f232a] bg-[#101216]" />
              ))
            : [
                { label: "Usuarios", value: data?.stats.total_users, accent: false },
                { label: "Solicitudes pendientes", value: data?.stats.pending_requests, accent: data?.stats.pending_requests > 0 },
                { label: "Interacciones", value: data?.stats.total_interactions, accent: false },
                { label: "Tareas activas", value: data?.stats.active_tasks, accent: false },
                { label: "Errores", value: data?.stats.errors_today, accent: data?.stats.errors_today > 0 },
              ].map(({ label, value, accent }) => (
                <div
                  key={label}
                  className="rounded-xl border border-[#1f232a] bg-[#101216] p-5 transition-colors hover:border-[#343b45]"
                >
                  <p className="text-2xs font-semibold uppercase tracking-[0.07em] text-[#7d8592]">
                    {label}
                  </p>
                  <p className={`mt-2.5 text-3xl font-semibold tabular-nums tracking-tight ${accent ? "text-[#34d399]" : "text-white"}`}>
                    {value ?? "—"}
                  </p>
                </div>
              ))
          }
        </div>

        <div>
          <p className="section-tag mb-4">Actividad reciente</p>
          <div className="overflow-hidden rounded-xl border border-[#1f232a] bg-[#101216]">
            <div className="overflow-x-auto">
              <div className="min-w-[760px]">
                <div className="grid grid-cols-12 border-b border-[#1f232a] bg-[#0e1013]">
                  <div className="col-span-2 th">Evento</div>
                  <div className="col-span-6 th">Mensaje</div>
                  <div className="col-span-2 th">Estado</div>
                  <div className="col-span-2 th">Hora</div>
                </div>
                {isLoading
                  ? Array(5).fill(0).map((_, i) => <div key={i} className="h-10 border-b border-[#1a1e24] bg-[#0e1013] animate-pulse" />)
                  : data?.recent_logs?.length === 0
                  ? <p className="px-5 py-10 text-center text-xs text-[#7d8592]">Sin actividad registrada</p>
                  : data?.recent_logs?.map((log: ActivityLog) => (
                      <div key={log.id} className="grid grid-cols-12 border-b border-[#1a1e24] transition-colors last:border-b-0 hover:bg-white/[0.025]">
                        <div className="col-span-2 td">
                          <span className={`badge ${EVENT_BADGE[log.event_type] ?? "badge-slate"}`}>{log.event_type}</span>
                        </div>
                        <div className="col-span-6 td truncate text-[#e8ebf0]">
                          {log.request_content || log.tool_invoked || "—"}
                        </div>
                        <div className="col-span-2 td">
                          {log.status && (
                            <span className={`text-2xs font-semibold uppercase tracking-[0.05em] ${log.status === "success" ? "text-[#34d399]" : "text-red-400"}`}>
                              {log.status}
                            </span>
                          )}
                        </div>
                        <div className="col-span-2 td text-xs tabular-nums text-[#a8b0bd]">{fmtDate(log.timestamp_utc)}</div>
                      </div>
                    ))
                }
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
