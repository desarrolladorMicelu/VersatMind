import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import api from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

export default function Historial() {
  const qc = useQueryClient();
  const { tenantId } = useTenant();
  const p = tenantId ? { tenant_id: tenantId } : undefined;
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["historial", tenantId, selectedChatId],
    queryFn: () => api.get("/historial", {
      params: { ...p, ...(selectedChatId ? { chat_id: selectedChatId } : {}) }
    }).then((r) => r.data),
    enabled: tenantId !== null,
  });

  const limpiar = useMutation({
    mutationFn: (chat_id: number) => api.delete(`/historial/${chat_id}`, { params: p }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["historial", tenantId] });
      setSelectedChatId(null);
    },
  });

  const users = data?.users ?? [];
  const messages = data?.messages ?? [];
  const ROLE_BADGE: Record<string, string> = { user: "badge-indigo", assistant: "badge-green", tool: "badge-slate" };

  if (!tenantId) {
    return (
      <div>
        <PageHeader tag="LOGS" title="Historial" description="Selecciona un cliente" />
        <div className="px-5 py-16 sm:px-8 text-center">
          <p className="text-xs text-white uppercase tracking-[0.06em]">Selecciona un cliente en el panel izquierdo</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader tag="LOGS" title="Historial" description="Conversaciones por usuario" />
      <div className="px-5 py-6 sm:px-8 sm:py-8 flex gap-6">

        <div className="w-48 flex-shrink-0">
          <p className="section-tag mb-3">USUARIOS</p>
          <div className="rounded-xl border border-[#1f232a]">
            {isLoading ? (
              Array(3).fill(0).map((_, i) => <div key={i} className="h-10 border-b border-[#1a1e24] animate-pulse" />)
            ) : users.length === 0 ? (
              <p className="p-4 text-xs text-white text-center">VACÍO</p>
            ) : users.map((u: any) => (
              <button key={u.chat_id} onClick={() => setSelectedChatId(u.chat_id)}
                className={`w-full text-left px-4 py-3 border-b border-[#1a1e24] transition-colors ${
                  selectedChatId === u.chat_id ? "bg-[#34d399]/5 border-l-2 border-l-[#34d399]" : "hover:bg-[#0e1013]"
                }`}>
                <p className="text-xs font-medium text-white">{u.username || "—"}</p>
                <p className="text-xs text-white">{u.chat_id}</p>
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 min-w-0">
          {!selectedChatId ? (
            <div className="rounded-xl border border-[#1f232a] flex items-center justify-center py-20">
              <p className="text-xs text-white uppercase tracking-[0.06em]">Selecciona un usuario</p>
            </div>
          ) : (
            <div className="rounded-xl border border-[#1f232a]">
              <div className="px-5 py-3 bg-[#0e1013] border-b border-[#1f232a] flex items-center justify-between">
                <span className="section-tag">{messages.length} mensajes</span>
                <button onClick={() => window.confirm("¿Limpiar historial?") && limpiar.mutate(selectedChatId)}
                  className="flex items-center gap-1.5 text-xs text-red-500 hover:text-red-400 uppercase tracking-[0.06em] transition-colors">
                  <Trash2 className="w-3 h-3" /> LIMPIAR
                </button>
              </div>
              <div className="max-h-[600px] overflow-y-auto divide-y divide-[#0b0c0e]">
                {messages.length === 0 ? (
                  <p className="px-5 py-10 text-center text-xs text-white">SIN MENSAJES</p>
                ) : messages.map((m: any) => (
                  <div key={m.id} className={`px-5 py-4 ${m.role === "assistant" ? "bg-[#0e1013]" : ""}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`badge ${ROLE_BADGE[m.role] ?? "badge-slate"}`}>{m.role}</span>
                      {m.tool_name && <span className="text-xs text-white">{m.tool_name}</span>}
                      <span className="text-xs text-white ml-auto">{fmtDate(m.created_at)}</span>
                    </div>
                    <p className="text-sm text-white whitespace-pre-wrap leading-relaxed">{m.content}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
