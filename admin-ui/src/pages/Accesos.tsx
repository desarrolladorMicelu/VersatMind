import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import api from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

export default function Accesos() {
  const qc = useQueryClient();
  const { tenantId } = useTenant();
  const p = tenantId ? { tenant_id: tenantId } : undefined;

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ["accesos", tenantId],
    queryFn: () => api.get("/accesos", { params: p }).then((r) => r.data),
    refetchInterval: 15000,
    enabled: tenantId !== null,
  });

  const aprobar = useMutation({
    mutationFn: (chat_id: number) => api.post(`/accesos/${chat_id}/aprobar`, null, { params: p }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accesos", tenantId] }),
  });

  const rechazar = useMutation({
    mutationFn: (chat_id: number) => api.post(`/accesos/${chat_id}/rechazar`, null, { params: p }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accesos", tenantId] }),
  });

  const pending = requests.filter((r: any) => r.status === "pending").length;
  const STATUS: Record<string, string> = { pending: "PENDIENTE", approved: "APROBADO", rejected: "RECHAZADO" };
  const STATUS_BADGE: Record<string, string> = { pending: "badge-amber", approved: "badge-green", rejected: "badge-red" };

  if (!tenantId) {
    return (
      <div>
        <PageHeader tag="ACCESO" title="Solicitudes" description="Selecciona un cliente" />
        <div className="px-5 py-16 sm:px-8 text-center">
          <p className="text-xs text-white uppercase tracking-[0.06em]">Selecciona un cliente en el panel izquierdo</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader tag="ACCESO" title="Solicitudes" description={`${pending} pendientes de revisión`} />
      <div className="px-5 py-6 sm:px-8 sm:py-8">
        <div className="rounded-xl border border-[#1f232a]">
          <div className="grid grid-cols-12 bg-[#0e1013] border-b border-[#1f232a]">
            <div className="col-span-3 th">Nombre</div>
            <div className="col-span-3 th">Username</div>
            <div className="col-span-2 th">Chat ID</div>
            <div className="col-span-2 th">Estado</div>
            <div className="col-span-2 th">Solicitado</div>
          </div>

          {isLoading
            ? Array(3).fill(0).map((_, i) => <div key={i} className="h-12 border-b border-[#1a1e24] animate-pulse" />)
            : requests.map((r: any) => (
              <div key={r.id} className="grid grid-cols-12 border-b border-[#1a1e24] hover:bg-[#0e1013] transition-colors items-center">
                <div className="col-span-3 td font-medium text-white">{r.first_name || "—"}</div>
                <div className="col-span-3 td text-xs text-white">@{r.username || "—"}</div>
                <div className="col-span-2 td text-xs text-white">{r.chat_id}</div>
                <div className="col-span-2 td">
                  <span className={`badge ${STATUS_BADGE[r.status] ?? "badge-slate"}`}>
                    {STATUS[r.status] ?? r.status}
                  </span>
                </div>
                <div className="col-span-2 td">
                  {r.status === "pending" ? (
                    <div className="flex items-center gap-2">
                      <button onClick={() => aprobar.mutate(r.chat_id)}
                        className="flex items-center gap-1 text-xs uppercase tracking-[0.06em] text-[#34d399] border border-[#34d399]/30 px-2 py-1 hover:bg-[#34d399]/10 transition-colors">
                        <Check className="w-3 h-3" /> OK
                      </button>
                      <button onClick={() => rechazar.mutate(r.chat_id)}
                        className="flex items-center gap-1 text-xs uppercase tracking-[0.06em] text-red-500 border border-red-900/40 px-2 py-1 hover:bg-red-900/10 transition-colors">
                        <X className="w-3 h-3" /> NO
                      </button>
                    </div>
                  ) : (
                    <span className="text-xs text-white">{fmtDate(r.created_at)}</span>
                  )}
                </div>
              </div>
            ))
          }
          {!isLoading && requests.length === 0 && (
            <p className="px-5 py-10 text-center text-xs text-white">SIN SOLICITUDES</p>
          )}
        </div>
      </div>
    </div>
  );
}
