import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import api from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

const EVENT_TYPES = ["", "interaction", "unauthorized", "tool_failure", "scheduler"];
const STATUS_OPTIONS = ["", "success", "error"];
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
        tag="LOGS" title="Auditoría" description="Registro completo de actividad"
        action={<button className="btn-secondary" onClick={() => refetch()}>↺ ACTUALIZAR</button>}
      />
      <div className="px-8 py-8 space-y-5">

        <div className="border border-[#1a1a1a] bg-[#050505] px-5 py-4 flex flex-wrap gap-5 items-end">
          <div>
            <label className="label">Tipo de evento</label>
            <select className="input w-44" value={eventType} onChange={(e) => setEventType(e.target.value)}>
              {EVENT_TYPES.map((t) => <option key={t} value={t}>{t || "Todos"}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Estado</label>
            <select className="input w-32" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s || "Todos"}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Límite</label>
            <select className="input w-24" value={limit} onChange={(e) => setLimit(parseInt(e.target.value))}>
              {[50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="font-mono text-[10px] text-white pb-2">{logs.length} registros</div>
        </div>

        <div className="border border-[#1a1a1a]">
          <div className="grid grid-cols-12 bg-[#050505] border-b border-[#1a1a1a]">
            <div className="col-span-2 th">Evento</div>
            <div className="col-span-1 th">Chat</div>
            <div className="col-span-5 th">Mensaje / Herramienta</div>
            <div className="col-span-2 th">Estado</div>
            <div className="col-span-2 th">Fecha</div>
          </div>

          {isLoading
            ? Array(5).fill(0).map((_, i) => <div key={i} className="h-10 border-b border-[#111] animate-pulse" />)
            : logs.length === 0
            ? <p className="px-5 py-10 text-center font-mono text-xs text-white">SIN REGISTROS</p>
            : logs.map((log: any) => (
              <div key={log.id} className="grid grid-cols-12 border-b border-[#111] hover:bg-[#050505] transition-colors">
                <div className="col-span-2 td">
                  <span className={`badge ${EVENT_BADGE[log.event_type] ?? "badge-slate"}`}>{log.event_type}</span>
                </div>
                <div className="col-span-1 td font-mono text-[11px] text-white">{log.chat_id ?? "—"}</div>
                <div className="col-span-5 td">
                  <p className="text-xs text-white truncate">{log.request_content || log.tool_invoked || "—"}</p>
                  {log.error_description && (
                    <p className="font-mono text-[10px] text-red-500 truncate mt-0.5">{log.error_description}</p>
                  )}
                </div>
                <div className="col-span-2 td">
                  {log.status && (
                    <span className={`font-mono text-[10px] uppercase tracking-widest ${log.status === "success" ? "text-[#00e5a0]" : "text-red-500"}`}>
                      {log.status}
                    </span>
                  )}
                </div>
                <div className="col-span-2 td font-mono text-[11px] text-white">{fmtDate(log.timestamp_utc)}</div>
              </div>
            ))
          }
        </div>

      </div>
    </div>
  );
}
