import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Play, Power, Trash2, Pencil, Plus, Send } from "lucide-react";
import { promptsApi } from "../lib/api";
import type { Frequency, ScheduledPrompt, ScheduledPromptPayload } from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

const WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const WEEKDAY_LABELS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

const EMPTY_FORM = {
  id: null as number | null,
  name: "",
  description: "",
  prompt: "",
  chat_id: "",
  chat_label: "",
  frequency: "daily" as Frequency,
  time: "08:00",
  weekday: 0,
  cron: "0 8 * * *",
  is_active: true,
};

type FormState = typeof EMPTY_FORM;

function promptToForm(p: ScheduledPrompt): FormState {
  const parts = (p.cron_expression || "").trim().split(/\s+/);
  const minute = parseInt(parts[0], 10);
  const hour = parseInt(parts[1], 10);
  const hh = String(isNaN(hour) ? 8 : hour).padStart(2, "0");
  const mm = String(isNaN(minute) ? 0 : minute).padStart(2, "0");
  let weekday = 0;
  if (p.frequency === "weekly" && parts[4]) {
    const idx = WEEKDAY_KEYS.indexOf(parts[4].toLowerCase());
    if (idx >= 0) weekday = idx;
  }
  return {
    id: p.id,
    name: p.name,
    description: p.description || "",
    prompt: p.prompt,
    chat_id: String(p.chat_id),
    chat_label: p.chat_label || "",
    frequency: p.frequency,
    time: `${hh}:${mm}`,
    weekday,
    cron: p.cron_expression,
    is_active: p.is_active,
  };
}

function formToPayload(f: FormState): ScheduledPromptPayload {
  const [hStr, mStr] = f.time.split(":");
  const hour = parseInt(hStr, 10);
  const minute = parseInt(mStr, 10);
  return {
    name: f.name,
    description: f.description,
    prompt: f.prompt,
    chat_id: parseInt(f.chat_id, 10),
    chat_label: f.chat_label,
    frequency: f.frequency,
    hour: isNaN(hour) ? 8 : hour,
    minute: isNaN(minute) ? 0 : minute,
    weekday: f.weekday,
    cron_expression: f.frequency === "custom" ? f.cron : null,
    timezone: "America/Bogota",
    is_active: f.is_active,
  };
}

function FrequencyLabel({ p }: { p: ScheduledPrompt }) {
  if (p.frequency === "daily") return <span>Diaria</span>;
  if (p.frequency === "weekly") return <span>Semanal</span>;
  return <span>Personalizada</span>;
}

export default function Programados() {
  const qc = useQueryClient();
  const { tenantId } = useTenant();
  const [form, setForm] = useState<FormState | null>(null);
  const [preview, setPreview] = useState("");
  const [error, setError] = useState("");

  const { data: prompts = [], isLoading } = useQuery({
    queryKey: ["prompts", tenantId],
    queryFn: () => promptsApi.list(tenantId as number),
    enabled: tenantId !== null,
  });

  const { data: variables = [] } = useQuery({
    queryKey: ["prompt-variables"],
    queryFn: () => promptsApi.variables(),
    enabled: tenantId !== null,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["prompts", tenantId] });

  const save = useMutation({
    mutationFn: (f: FormState) => {
      const payload = formToPayload(f);
      return f.id
        ? promptsApi.update(tenantId as number, f.id, payload)
        : promptsApi.create(tenantId as number, payload);
    },
    onSuccess: () => { setForm(null); setPreview(""); setError(""); invalidate(); },
    onError: () => setError("No se pudo guardar. Revisa la expresión cron y los campos."),
  });

  const toggle = useMutation({
    mutationFn: (id: number) => promptsApi.toggle(tenantId as number, id),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: number) => promptsApi.remove(tenantId as number, id),
    onSuccess: invalidate,
  });

  const runNow = useMutation({
    mutationFn: (id: number) => promptsApi.runNow(tenantId as number, id),
    onSuccess: (res) => {
      invalidate();
      window.alert(res.ok ? "Prompt ejecutado y enviado por Telegram." : `Error: ${res.error ?? "desconocido"}`);
    },
    onError: () => window.alert("No se pudo ejecutar el prompt."),
  });

  const doPreview = async () => {
    if (!form) return;
    try {
      const res = await promptsApi.preview(tenantId as number, form.prompt);
      setPreview(res.rendered);
    } catch {
      setPreview("No se pudo generar la vista previa.");
    }
  };

  const insertVar = (key: string) => {
    setForm((f) => (f ? { ...f, prompt: `${f.prompt}{{${key}}}` } : f));
  };

  if (!tenantId) {
    return (
      <div>
        <PageHeader tag="AUTOMATIZACIÓN" title="Programados" description="Selecciona un cliente" />
        <div className="px-8 py-16 text-center">
          <p className="font-mono text-xs text-white uppercase tracking-widest">Selecciona un cliente en el panel izquierdo</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        tag="AUTOMATIZACIÓN"
        title="Prompts programados"
        description="Reportes e insights automáticos enviados por Telegram"
        action={
          <button className="btn-primary" onClick={() => { setForm({ ...EMPTY_FORM }); setPreview(""); setError(""); }}>
            <Plus className="w-3.5 h-3.5" /> Nuevo prompt
          </button>
        }
      />
      <div className="px-8 py-8 space-y-6">

        {form && (
          <div className="border border-[#00e5a0]/30 bg-[#050505] p-6 space-y-5">
            <p className="section-tag">{form.id ? "// Editar prompt" : "// Nuevo prompt"}</p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div>
                <label className="label">Nombre</label>
                <input className="input" value={form.name}
                  placeholder="Resumen matutino"
                  onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div>
                <label className="label">Descripción</label>
                <input className="input" value={form.description}
                  placeholder="Resumen de ventas del día anterior"
                  onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>
              <div>
                <label className="label">Chat ID destino (usuario o grupo)</label>
                <input className="input" value={form.chat_id} inputMode="numeric"
                  placeholder="123456789"
                  onChange={(e) => setForm({ ...form, chat_id: e.target.value.replace(/[^0-9-]/g, "") })} />
              </div>
              <div>
                <label className="label">Etiqueta del destino</label>
                <input className="input" value={form.chat_label}
                  placeholder="Cristian (jefe)"
                  onChange={(e) => setForm({ ...form, chat_label: e.target.value })} />
              </div>
            </div>

            <div>
              <label className="label">Prompt</label>
              <textarea className="input" rows={5} value={form.prompt}
                placeholder="Genera el resumen de ventas de ayer ({{ayer}}) y valida si los márgenes estuvieron dentro de lo aprobado."
                onChange={(e) => setForm({ ...form, prompt: e.target.value })} />
              <div className="flex flex-wrap gap-1.5 mt-2">
                {variables.map((v) => (
                  <button key={v.key} type="button" title={v.desc}
                    onClick={() => insertVar(v.key)}
                    className="font-mono text-[10px] px-2 py-1 border border-[#2a2a2a] text-white hover:border-[#00e5a0] hover:text-[#00e5a0] transition-colors">
                    {`{{${v.key}}}`}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <div>
                <label className="label">Frecuencia</label>
                <select className="input" value={form.frequency}
                  onChange={(e) => setForm({ ...form, frequency: e.target.value as Frequency })}>
                  <option value="daily">Diaria</option>
                  <option value="weekly">Semanal</option>
                  <option value="custom">Personalizada (cron)</option>
                </select>
              </div>

              {form.frequency !== "custom" && (
                <div>
                  <label className="label">Hora</label>
                  <input type="time" className="input" value={form.time}
                    onChange={(e) => setForm({ ...form, time: e.target.value })} />
                </div>
              )}

              {form.frequency === "weekly" && (
                <div>
                  <label className="label">Día de la semana</label>
                  <select className="input" value={form.weekday}
                    onChange={(e) => setForm({ ...form, weekday: parseInt(e.target.value, 10) })}>
                    {WEEKDAY_LABELS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                  </select>
                </div>
              )}

              {form.frequency === "custom" && (
                <div className="md:col-span-2">
                  <label className="label">Expresión cron (5 campos)</label>
                  <input className="input" value={form.cron}
                    placeholder="0 8 * * 1-5"
                    onChange={(e) => setForm({ ...form, cron: e.target.value })} />
                  <p className="font-mono text-[10px] text-white mt-1">Ej: <span className="text-[#00e5a0]">0 8 * * *</span> (diaria 8:00), <span className="text-[#00e5a0]">30 7 * * mon</span> (lunes 7:30)</p>
                </div>
              )}
            </div>

            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
              <span className="font-mono text-[11px] uppercase tracking-widest text-white">Activo</span>
            </label>

            <div className="flex items-center gap-3">
              <button className="btn-primary" disabled={save.isPending || !form.name || !form.prompt || !form.chat_id}
                onClick={() => save.mutate(form)}>
                <Send className="w-3.5 h-3.5" /> Guardar
              </button>
              <button className="btn-secondary" onClick={doPreview}>Vista previa</button>
              <button className="btn-ghost" onClick={() => { setForm(null); setPreview(""); setError(""); }}>Cancelar</button>
            </div>

            {error && <p className="font-mono text-[10px] text-red-500">{error}</p>}

            {preview && (
              <div className="border border-[#1a1a1a] bg-black p-4">
                <p className="section-tag mb-2">// Vista previa con variables resueltas</p>
                <pre className="font-mono text-xs text-white whitespace-pre-wrap">{preview}</pre>
              </div>
            )}
          </div>
        )}

        <div className="border border-[#1a1a1a]">
          <div className="grid grid-cols-12 bg-[#050505] border-b border-[#1a1a1a]">
            <div className="col-span-3 th">Nombre</div>
            <div className="col-span-2 th">Destino</div>
            <div className="col-span-2 th">Frecuencia</div>
            <div className="col-span-2 th">Próxima</div>
            <div className="col-span-1 th">Estado</div>
            <div className="col-span-2 th">Acciones</div>
          </div>

          {isLoading ? (
            Array(3).fill(0).map((_, i) => <div key={i} className="h-12 border-b border-[#111] animate-pulse" />)
          ) : prompts.length === 0 ? (
            <p className="px-5 py-10 text-center font-mono text-xs text-white">SIN PROMPTS PROGRAMADOS</p>
          ) : (
            prompts.map((p) => (
              <div key={p.id} className="grid grid-cols-12 border-b border-[#111] hover:bg-[#050505] transition-colors items-center">
                <div className="col-span-3 td">
                  <p className="text-sm text-white">{p.name}</p>
                  <p className="font-mono text-[10px] text-white truncate">{p.description || p.cron_expression}</p>
                </div>
                <div className="col-span-2 td">
                  <p className="text-xs text-white">{p.chat_label || "—"}</p>
                  <p className="font-mono text-[10px] text-white">{p.chat_id}</p>
                </div>
                <div className="col-span-2 td">
                  <p className="text-xs text-white"><FrequencyLabel p={p} /></p>
                  <code className="font-mono text-[10px] text-[#00e5a0]">{p.cron_expression}</code>
                </div>
                <div className="col-span-2 td font-mono text-[11px] text-white">
                  {p.next_run_at ? fmtDate(p.next_run_at) : "—"}
                  {p.last_status && (
                    <span className={`block text-[10px] ${p.last_status === "success" ? "text-[#00e5a0]" : "text-red-500"}`}>
                      última: {p.last_status}
                    </span>
                  )}
                </div>
                <div className="col-span-1 td">
                  <span className={`badge ${p.is_active ? "badge-green" : "badge-slate"}`}>{p.is_active ? "ON" : "OFF"}</span>
                </div>
                <div className="col-span-2 td">
                  <div className="flex items-center gap-1.5 justify-end">
                    <button title="Ejecutar ahora" onClick={() => runNow.mutate(p.id)}
                      className="p-1.5 text-white hover:text-[#00e5a0] transition-colors">
                      <Play className="w-3.5 h-3.5" />
                    </button>
                    <button title="Editar" onClick={() => { setForm(promptToForm(p)); setPreview(""); setError(""); }}
                      className="p-1.5 text-white hover:text-[#00e5a0] transition-colors">
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button title={p.is_active ? "Desactivar" : "Activar"} onClick={() => toggle.mutate(p.id)}
                      className={`p-1.5 transition-colors ${p.is_active ? "text-white hover:text-yellow-500" : "text-white hover:text-[#00e5a0]"}`}>
                      <Power className="w-3.5 h-3.5" />
                    </button>
                    <button title="Eliminar" onClick={() => window.confirm("¿Eliminar este prompt?") && remove.mutate(p.id)}
                      className="p-1.5 text-white hover:text-red-500 transition-colors">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

      </div>
    </div>
  );
}
