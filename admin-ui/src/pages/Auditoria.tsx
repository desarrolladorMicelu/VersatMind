import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import api from "../lib/api";
import { fmtDate } from "../lib/utils";
import { eventLabel, isOkStatus, statusLabel, toolLabel } from "../lib/labels";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

const EVENT_TYPES = [
  { value: "", label: "Todos" },
  { value: "interaction", label: eventLabel("interaction") },
  { value: "unauthorized", label: eventLabel("unauthorized") },
  { value: "tool_failure", label: eventLabel("tool_failure") },
  { value: "scheduler", label: eventLabel("scheduler") },
];
const STATUS_OPTIONS = [
  { value: "", label: "Todos" },
  { value: "success", label: statusLabel("success") },
  { value: "error", label: statusLabel("error") },
];
const EVENT_BADGE: Record<string, string> = {
  interaction: "badge-indigo", tool_failure: "badge-red",
  unauthorized: "badge-amber", scheduler: "badge-slate",
};

export default function Auditoria() {
  const { tenantId } = useTenant();
  const [eventType, setEventType] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [limit, setLimit] = useState(100);

  const { data: logs = [], isLoading, refetch } = useQuery({
    queryKey: ["auditoria", tenantId, eventType, statusFilter, limit],
    queryFn: () => api.get("/auditoria", {
      params: {
        ...(tenantId ? { tenant_id: tenantId } : {}),
        event_type: eventType,
        status_filter: statusFilter,
        limit,
      }
    }).then((r) => r.data),
  });

  return (
    <div>
      <PageHeader
        tag="REGISTRO" title="Auditoría" description="Historial de conversaciones y acciones del asistente"
        action={<button className="btn-secondary" onClick={() => refetch()}>↺ ACTUALIZAR</button>}
      />
      <div className="px-5 py-6 sm:px-8 sm:py-8 space-y-5">

        <div className="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface)] px-5 py-4 flex flex-wrap gap-5 items-end">
          <div>
            <label className="label">Tipo de evento</label>
            <select className="input w-52" value={eventType} onChange={(e) => setEventType(e.target.value)}>
              {EVENT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Estado</label>
            <select className="input w-40" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              {STATUS_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Mostrar</label>
            <select className="input w-24" value={limit} onChange={(e) => setLimit(parseInt(e.target.value))}>
              {[50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="text-xs text-[var(--color-text)] pb-2">{logs.length} registros</div>
        </div>

        <div className="overflow-hidden rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface)]">
          <div className="grid grid-cols-12 bg-[var(--color-bg-elevated)] border-b border-[var(--color-border-subtle)]">
            <div className="col-span-2 th">Tipo</div>
            <div className="col-span-1 th">Conversación</div>
            <div className="col-span-5 th">Detalle</div>
            <div className="col-span-2 th">Resultado</div>
            <div className="col-span-2 th">Fecha</div>
          </div>

          {isLoading
            ? Array(5).fill(0).map((_, i) => <div key={i} className="h-10 border-b border-[var(--color-border-subtle)] animate-pulse" />)
            : logs.length === 0
            ? <p className="px-5 py-10 text-center text-xs text-[var(--color-text)]">Aún no hay registros</p>
            : logs.map((log: any) => (
              <div key={log.id} className="grid grid-cols-12 border-b border-[var(--color-border-subtle)] hover:bg-[var(--color-bg-elevated)] transition-colors">
                <div className="col-span-2 td">
                  <span
                    className={`badge ${EVENT_BADGE[log.event_type] ?? "badge-slate"}`}
                    title={log.event_type}
                  >
                    {eventLabel(log.event_type)}
                  </span>
                </div>
                <div className="col-span-1 td text-xs text-[var(--color-text)]">{log.chat_id ?? "—"}</div>
                <div className="col-span-5 td">
                  <p className="text-xs text-[var(--color-text)] truncate">
                    {log.request_content || toolLabel(log.tool_invoked)}
                  </p>
                  {log.request_content && log.tool_invoked && (
                    <p className="mt-0.5 truncate text-2xs text-[var(--color-text-subtle)]">
                      Acción: {toolLabel(log.tool_invoked)}
                    </p>
                  )}
                  {log.error_description && (
                    <p className="text-xs text-red-700 truncate mt-0.5">{log.error_description}</p>
                  )}
                </div>
                <div className="col-span-2 td">
                  {log.status && (
                    <span
                      className={`text-xs font-semibold ${
                        isOkStatus(log.status) ? "text-[var(--color-accent-strong)]" : "text-red-700"
                      }`}
                      title={log.status}
                    >
                      {statusLabel(log.status)}
                    </span>
                  )}
                </div>
                <div className="col-span-2 td text-xs text-[var(--color-text)]">{fmtDate(log.timestamp_utc)}</div>
              </div>
            ))
          }
        </div>

      </div>
    </div>
  );
}
