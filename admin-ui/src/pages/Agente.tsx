import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import api from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

const MODELS = [
  "openai/gpt-4o-mini", "openai/gpt-4o",
  "google/gemini-flash-1.5", "deepseek/deepseek-chat", "anthropic/claude-3-haiku",
];

export default function Agente() {
  const qc = useQueryClient();
  const { tenantId, activeTenant } = useTenant();
  const p = tenantId ? { tenant_id: tenantId } : undefined;
  const [saved, setSaved] = useState(false);
  const [form, setForm] = useState({
    system_prompt: "", model: "openai/gpt-4o-mini",
    temperature: 0.7, conversation_window: 20, max_tool_cycles: 5,
  });

  const { data, isLoading } = useQuery({
    queryKey: ["agente", tenantId],
    queryFn: () => api.get("/agente", { params: p }).then((r) => r.data),
    enabled: tenantId !== null,
  });

  useEffect(() => { if (data) setForm(data); }, [data]);

  const mutation = useMutation({
    mutationFn: (payload: typeof form) => api.put("/agente", payload, { params: p }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agente", tenantId] });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    },
  });

  if (!tenantId) {
    return (
      <div>
        <PageHeader tag="CONFIG" title="Agente" description="Selecciona un cliente" />
        <div className="px-8 py-16 text-center">
          <p className="font-mono text-xs text-[#333] uppercase tracking-widest">Selecciona un cliente en el panel izquierdo</p>
        </div>
      </div>
    );
  }

  if (isLoading) return <div className="px-8 py-8"><div className="border border-[#1a1a1a] h-96 animate-pulse" /></div>;

  return (
    <div>
      <PageHeader
        tag="CONFIG"
        title="Agente"
        description={`${activeTenant?.name ?? "Cliente"} — personalidad y comportamiento del bot`}
        action={
          <div className="flex items-center gap-4">
            {saved && <span className="font-mono text-xs text-[#00e5a0] uppercase tracking-widest">// guardado</span>}
            {data?.updated_at && <span className="font-mono text-[11px] text-[#333]">{fmtDate(data.updated_at)}</span>}
            <button className="btn-primary" onClick={() => mutation.mutate(form)} disabled={mutation.isPending}>
              {mutation.isPending ? "GUARDANDO..." : "GUARDAR →"}
            </button>
          </div>
        }
      />
      <div className="px-8 py-8 space-y-6 max-w-4xl">

        <div className="border border-[#1a1a1a]">
          <div className="px-5 py-3 border-b border-[#1a1a1a] bg-[#050505] flex items-center justify-between">
            <span className="section-tag">// SYSTEM PROMPT</span>
            <span className="font-mono text-[10px] text-[#333]">{form.system_prompt.length} chars</span>
          </div>
          <div className="p-5">
            <p className="font-mono text-[11px] text-[#444] mb-3">
              Define la personalidad y reglas del agente para este cliente.
            </p>
            <textarea
              className="input min-h-[260px] resize-y font-mono text-xs leading-relaxed"
              value={form.system_prompt}
              onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
              placeholder="Eres Mind, un asistente ejecutivo..."
            />
          </div>
        </div>

        <div className="border border-[#1a1a1a]">
          <div className="px-5 py-3 border-b border-[#1a1a1a] bg-[#050505]">
            <span className="section-tag">// MODELO Y PARÁMETROS</span>
          </div>
          <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="md:col-span-2">
              <label className="label">Modelo</label>
              <select className="input" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}>
                {MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <input className="input mt-2" placeholder="O escribe un modelo personalizado..."
                value={MODELS.includes(form.model) ? "" : form.model}
                onChange={(e) => e.target.value && setForm({ ...form, model: e.target.value })} />
            </div>
            <div>
              <label className="label">Temperatura — <span className="text-[#00e5a0]">{form.temperature}</span></label>
              <input type="range" min="0" max="2" step="0.1" className="w-full mt-2 accent-[#00e5a0]"
                value={form.temperature} onChange={(e) => setForm({ ...form, temperature: parseFloat(e.target.value) })} />
              <div className="flex justify-between font-mono text-[10px] text-[#333] mt-1">
                <span>0 preciso</span><span>2 creativo</span>
              </div>
            </div>
            <div>
              <label className="label">Ventana de conversación</label>
              <input type="number" min="1" max="100" className="input" value={form.conversation_window}
                onChange={(e) => setForm({ ...form, conversation_window: parseInt(e.target.value) })} />
              <p className="font-mono text-[10px] text-[#333] mt-1.5">Mensajes anteriores que recuerda</p>
            </div>
            <div>
              <label className="label">Máx. ciclos de herramientas</label>
              <input type="number" min="1" max="20" className="input" value={form.max_tool_cycles}
                onChange={(e) => setForm({ ...form, max_tool_cycles: parseInt(e.target.value) })} />
              <p className="font-mono text-[10px] text-[#333] mt-1.5">Límite de tool calls por mensaje</p>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
