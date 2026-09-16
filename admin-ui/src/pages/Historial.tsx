import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import api from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";

export default function Historial() {
  const qc = useQueryClient();
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["historial", selectedChatId],
    queryFn: () => api.get("/historial", { params: selectedChatId ? { chat_id: selectedChatId } : {} }).then((r) => r.data),
  });

  const limpiar = useMutation({
    mutationFn: (chat_id: number) => api.delete(`/historial/${chat_id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["historial"] }),
  });

  const users = data?.users ?? [];
  const messages = data?.messages ?? [];

  const ROLE_BADGE: Record<string, string> = { user: "badge-indigo", assistant: "badge-green", tool: "badge-slate" };

  return (
    <div>
      <PageHeader tag="LOGS" title="Historial" description="Conversaciones por usuario" />
      <div className="px-8 py-8 flex gap-6">

        {/* User list */}
        <div className="w-48 flex-shrink-0">
          <p className="section-tag mb-3">// USUARIOS</p>
          <div className="border border-[#1a1a1a]">
            {isLoading ? (
              Array(3).fill(0).map((_, i) => <div key={i} className="h-10 border-b border-[#111] animate-pulse" />)
            ) : users.length === 0 ? (
              <p className="p-4 font-mono text-[10px] text-[#333] text-center">VACÍO</p>
            ) : users.map((u: any) => (
              <button
                key={u.chat_id}
                onClick={() => setSelectedChatId(u.chat_id)}
                className={`w-full text-left px-4 py-3 border-b border-[#111] transition-colors ${
                  selectedChatId === u.chat_id
                    ? "bg-[#00e5a0]/5 border-l-2 border-l-[#00e5a0]"
                    : "hover:bg-[#050505]"
                }`}
              >
                <p className="text-xs font-medium text-white">{u.username || "—"}</p>
                <p className="font-mono text-[10px] text-[#333]">{u.chat_id}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 min-w-0">
          {!selectedChatId ? (
            <div className="border border-[#1a1a1a] flex items-center justify-center py-20">
              <p className="font-mono text-xs text-[#333] uppercase tracking-widest">Selecciona un usuario</p>
            </div>
          ) : (
            <div className="border border-[#1a1a1a]">
              <div className="px-5 py-3 bg-[#050505] border-b border-[#1a1a1a] flex items-center justify-between">
                <span className="section-tag">// {messages.length} mensajes</span>
                <button
                  onClick={() => window.confirm("¿Limpiar historial?") && limpiar.mutate(selectedChatId)}
                  className="flex items-center gap-1.5 font-mono text-[10px] text-red-500 hover:text-red-400 uppercase tracking-widest transition-colors"
                >
                  <Trash2 className="w-3 h-3" /> LIMPIAR
                </button>
              </div>
              <div className="max-h-[600px] overflow-y-auto divide-y divide-[#111]">
                {messages.length === 0 ? (
                  <p className="px-5 py-10 text-center font-mono text-xs text-[#333]">SIN MENSAJES</p>
                ) : messages.map((m: any) => (
                  <div key={m.id} className={`px-5 py-4 ${m.role === "assistant" ? "bg-[#050505]" : ""}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`badge ${ROLE_BADGE[m.role] ?? "badge-slate"}`}>{m.role}</span>
                      {m.tool_name && <span className="font-mono text-[10px] text-[#444]">{m.tool_name}</span>}
                      <span className="font-mono text-[10px] text-[#333] ml-auto">{fmtDate(m.created_at)}</span>
                    </div>
                    <p className="text-sm text-[#aaa] whitespace-pre-wrap leading-relaxed">{m.content}</p>
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
