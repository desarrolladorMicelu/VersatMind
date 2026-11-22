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
          <p className="text-xs text-[var(--color-text)] uppercase tracking-[0.06em]">Selecciona un cliente en el panel izquierdo</p>
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
          <div className="overflow-hidden rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface)]">
            {isLoading ? (
              Array(3).fill(0).map((_, i) => <div key={i} className="h-10 border-b border-[var(--color-border-subtle)] animate-pulse" />)
            ) : users.length === 0 ? (
              <p className="p-4 text-xs text-[var(--color-text)] text-center">VACÍO</p>
            ) : users.map((u: any) => (
              <button key={u.chat_id} onClick={() => setSelectedChatId(u.chat_id)}
                className={`w-full text-left px-4 py-3 border-b border-[var(--color-border-subtle)] transition-colors ${
                  selectedChatId === u.chat_id ? "bg-[var(--color-accent-surface)] border-l-2 border-l-accent" : "hover:bg-[var(--color-bg-elevated)]"
                }`}>
                <p className="text-xs font-medium text-[var(--color-text)]">{u.username || "—"}</p>
                <p className="text-xs text-[var(--color-text)]">{u.chat_id}</p>
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 min-w-0">
          {!selectedChatId ? (
            <div className="rounded-xl border border-[var(--color-border-subtle)] flex items-center justify-center py-20">
              <p className="text-xs text-[var(--color-text)] uppercase tracking-[0.06em]">Selecciona un usuario</p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface)]">
              <div className="px-5 py-3 bg-[var(--color-bg-elevated)] border-b border-[var(--color-border-subtle)] flex items-center justify-between">
                <span className="section-tag">{messages.length} mensajes</span>
                <button onClick={() => window.confirm("¿Limpiar historial?") && limpiar.mutate(selectedChatId)}
                  className="flex items-center gap-1.5 text-xs text-red-700 hover:text-red-700 uppercase tracking-[0.06em] transition-colors">
                  <Trash2 className="w-3 h-3" /> LIMPIAR
                </button>
              </div>
              <div className="max-h-[600px] overflow-y-auto divide-y divide-[var(--color-border-subtle)]">
                {messages.length === 0 ? (
                  <p className="px-5 py-10 text-center text-xs text-[var(--color-text)]">SIN MENSAJES</p>
                ) : messages.map((m: any) => (
                  <div key={m.id} className={`px-5 py-4 ${m.role === "assistant" ? "bg-[var(--color-bg-elevated)]" : ""}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`badge ${ROLE_BADGE[m.role] ?? "badge-slate"}`}>{m.role}</span>
                      {m.tool_name && <span className="text-xs text-[var(--color-text)]">{m.tool_name}</span>}
                      <span className="text-xs text-[var(--color-text)] ml-auto">{fmtDate(m.created_at)}</span>
                    </div>
                    <p className="text-sm text-[var(--color-text)] whitespace-pre-wrap leading-relaxed">{m.content}</p>
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
