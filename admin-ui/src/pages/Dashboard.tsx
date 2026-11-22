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
                <div key={i} className="h-[120px] animate-pulse rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]" />
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
                  className="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] p-5 transition-colors hover:border-[var(--color-border)]"
                >
                  <p className="text-2xs font-semibold uppercase tracking-[0.07em] text-[var(--color-text-subtle)]">
                    {label}
                  </p>
                  <p className={`mt-2.5 text-3xl font-semibold tabular-nums tracking-tight ${accent ? "text-accent" : "text-[var(--color-text)]"}`}>
                    {value ?? "—"}
                  </p>
                </div>
              ))
          }
        </div>

        <div>
          <p className="section-tag mb-4">Actividad reciente</p>
          <div className="overflow-hidden rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]">
            <div className="overflow-x-auto">
              <div className="min-w-[880px]">
                <div className="grid grid-cols-12 border-b border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]">
                  <div className="col-span-2 th">Evento</div>
                  <div className="col-span-5 th">Mensaje</div>
                  <div className="col-span-2 th">Estado</div>
                  <div className="col-span-3 th">Hora</div>
                </div>
                {isLoading
                  ? Array(5).fill(0).map((_, i) => <div key={i} className="h-10 border-b border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] animate-pulse" />)
                  : data?.recent_logs?.length === 0
                  ? <p className="px-5 py-10 text-center text-xs text-[var(--color-text-subtle)]">Sin actividad registrada</p>
                  : data?.recent_logs?.map((log: ActivityLog) => (
                      <div key={log.id} className="grid grid-cols-12 border-b border-[var(--color-border-subtle)] transition-colors last:border-b-0 hover:bg-black/[0.03]">
                        <div className="col-span-2 td">
                          <span className={`badge ${EVENT_BADGE[log.event_type] ?? "badge-slate"}`}>{log.event_type}</span>
                        </div>
                        <div className="col-span-5 td truncate text-[var(--color-text)]">
                          {log.request_content || log.tool_invoked || "—"}
                        </div>
                        <div className="col-span-2 td">
                          {log.status && (
                            <span className={`text-2xs font-semibold uppercase tracking-[0.05em] ${log.status === "success" ? "text-accent" : "text-red-700"}`}>
                              {log.status}
                            </span>
                          )}
                        </div>
                        <div className="col-span-3 td text-xs tabular-nums text-[var(--color-text-muted)]">{fmtDate(log.timestamp_utc)}</div>
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
