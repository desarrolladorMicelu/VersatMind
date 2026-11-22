import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Power, Trash2, Pencil, Plus, Save } from "lucide-react";
import { knowledgeApi } from "../lib/api";
import type { KnowledgeEntry } from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

const EMPTY = { id: null as number | null, title: "", content: "", source: "", tags: "" };
type FormState = typeof EMPTY;

export default function Conocimiento() {
  const qc = useQueryClient();
  const { tenantId } = useTenant();
  const [form, setForm] = useState<FormState | null>(null);

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ["conocimiento", tenantId],
    queryFn: () => knowledgeApi.list(tenantId as number),
    enabled: tenantId !== null,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["conocimiento", tenantId] });

  const save = useMutation({
    mutationFn: (f: FormState) => {
      const payload = { title: f.title, content: f.content, source: f.source || "manual", tags: f.tags };
      return f.id
        ? knowledgeApi.update(tenantId as number, f.id, payload)
        : knowledgeApi.create(tenantId as number, payload);
    },
    onSuccess: () => { setForm(null); invalidate(); },
  });

  const toggle = useMutation({
    mutationFn: (id: number) => knowledgeApi.toggle(tenantId as number, id),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: number) => knowledgeApi.remove(tenantId as number, id),
    onSuccess: invalidate,
  });

  const startEdit = (e: KnowledgeEntry) =>
    setForm({ id: e.id, title: e.title, content: e.content, source: e.source, tags: e.tags });

  if (!tenantId) {
    return (
      <div>
        <PageHeader tag="CONTEXTO" title="Base de conocimiento" description="Selecciona un cliente" />
        <div className="px-5 py-16 sm:px-8 text-center">
          <p className="text-xs text-[var(--color-text)] uppercase tracking-[0.06em]">Selecciona un cliente en el panel izquierdo</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        tag="CONTEXTO"
        title="Base de conocimiento"
        description={`${entries.length} entradas cargadas`}
        action={
          <button className="btn-primary" onClick={() => setForm({ ...EMPTY })}>
            <Plus className="w-3.5 h-3.5" /> Nueva información
          </button>
        }
      />
      <div className="px-5 py-6 sm:px-8 sm:py-8 space-y-6">

        {form && (
          <div className="border border-accent/30 bg-[var(--color-bg-elevated)] p-6 space-y-5">
            <p className="section-tag">{form.id ? "Editar información" : "Cargar información"}</p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <div className="md:col-span-2">
                <label className="label text-[var(--color-text)]">Título</label>
                <input className="input" value={form.title}
                  placeholder="Metas de venta por asesor"
                  onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </div>
              <div>
                <label className="label text-[var(--color-text)]">Origen</label>
                <input className="input" value={form.source}
                  placeholder="manual / archivo.csv"
                  onChange={(e) => setForm({ ...form, source: e.target.value })} />
              </div>
            </div>

            <div>
              <label className="label text-[var(--color-text)]">Contenido</label>
              <textarea className="input" rows={10} value={form.content}
                placeholder="Pega aquí la información del negocio: metas, políticas, precios, catálogos, contexto de la tienda, etc."
                onChange={(e) => setForm({ ...form, content: e.target.value })} />
            </div>

            <div>
              <label className="label text-[var(--color-text)]">Etiquetas (separadas por coma)</label>
              <input className="input" value={form.tags}
                placeholder="ventas, margen, metas"
                onChange={(e) => setForm({ ...form, tags: e.target.value })} />
            </div>

            <div className="flex items-center gap-3">
              <button className="btn-primary" disabled={save.isPending || !form.title || !form.content}
                onClick={() => save.mutate(form)}>
                <Save className="w-3.5 h-3.5" /> Guardar
              </button>
              <button className="btn-ghost" onClick={() => setForm(null)}>Cancelar</button>
            </div>
          </div>
        )}

        <div className="rounded-xl border border-[var(--color-border-subtle)]">
          <div className="grid grid-cols-12 bg-[var(--color-bg-elevated)] border-b border-[var(--color-border-subtle)]">
            <div className="col-span-5 th">Título</div>
            <div className="col-span-2 th">Origen</div>
            <div className="col-span-2 th">Etiquetas</div>
            <div className="col-span-1 th">Estado</div>
            <div className="col-span-2 th">Actualizado</div>
          </div>

          {isLoading ? (
            Array(3).fill(0).map((_, i) => <div key={i} className="h-12 border-b border-[var(--color-border-subtle)] animate-pulse" />)
          ) : entries.length === 0 ? (
            <p className="px-5 py-10 text-center text-xs text-[var(--color-text)]">SIN INFORMACIÓN CARGADA</p>
          ) : (
            entries.map((e) => (
              <div key={e.id} className="grid grid-cols-12 border-b border-[var(--color-border-subtle)] hover:bg-[var(--color-bg-elevated)] transition-colors items-center">
                <div className="col-span-5 td">
                  <p className="text-sm text-[var(--color-text)]">{e.title}</p>
                  <p className="text-xs text-[var(--color-text)] truncate">{e.content.slice(0, 90)}</p>
                </div>
                <div className="col-span-2 td text-xs text-[var(--color-text)]">{e.source || "—"}</div>
                <div className="col-span-2 td text-xs text-[var(--color-text)] truncate">{e.tags || "—"}</div>
                <div className="col-span-1 td">
                  <span className={`badge ${e.is_active ? "badge-green" : "badge-slate"}`}>{e.is_active ? "ON" : "OFF"}</span>
                </div>
                <div className="col-span-2 td">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-[var(--color-text)]">{fmtDate(e.updated_at)}</span>
                    <div className="flex items-center gap-1.5">
                      <button title="Editar" onClick={() => startEdit(e)}
                        className="p-1.5 text-[var(--color-text)] hover:text-accent transition-colors">
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button title={e.is_active ? "Desactivar" : "Activar"} onClick={() => toggle.mutate(e.id)}
                        className={`p-1.5 transition-colors ${e.is_active ? "text-[var(--color-text)] hover:text-amber-700" : "text-[var(--color-text)] hover:text-accent"}`}>
                        <Power className="w-3.5 h-3.5" />
                      </button>
                      <button title="Eliminar" onClick={() => window.confirm("¿Eliminar esta información?") && remove.mutate(e.id)}
                        className="p-1.5 text-[var(--color-text)] hover:text-red-700 transition-colors">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
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
