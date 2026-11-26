import { useState } from "react";
import { CheckCircle2, AlertCircle, Loader2, Link2 } from "lucide-react";
import { tenantsApi } from "../lib/api";
import type { JsonSourcesPayload } from "../lib/api";

type Kind = "precios" | "historial";

const LABELS: Record<Kind, string> = {
  precios: "Precios de competencia",
  historial: "Historial de cambios",
};

export default function JsonSourcesConfig({
  value,
  onChange,
  tenantId,
}: {
  value: JsonSourcesPayload | null;
  onChange: (v: JsonSourcesPayload | null) => void;
  tenantId?: number;
}) {
  const sources = value ?? {};
  const [testing, setTesting] = useState<Kind | null>(null);
  const [status, setStatus] = useState<Record<Kind, { ok: boolean; text: string } | null>>({
    precios: null, historial: null,
  });

  const update = (kind: Kind, patch: { url?: string; is_active?: boolean }) => {
    const next = {
      ...sources,
      [kind]: { ...(sources[kind] ?? {}), ...patch },
    };
    onChange(next);
  };

  const test = async (kind: Kind) => {
    const url = String(sources[kind]?.url || "").trim();
    if (!url) return;
    setTesting(kind);
    setStatus((s) => ({ ...s, [kind]: null }));
    try {
      const r = await tenantsApi.testJsonSource(kind, url);
      setStatus((s) => ({
        ...s,
        [kind]: { ok: true, text: `JSON válido · ${r.count} registros` },
      }));
    } catch (e: any) {
      setStatus((s) => ({
        ...s,
        [kind]: {
          ok: false,
          text: e?.response?.data?.detail ?? "No se pudo leer el JSON",
        },
      }));
    } finally {
      setTesting(null);
    }
  };

  return (
    <div className="border-t border-[var(--color-border-subtle)] pt-5">
      <div className="mb-4 flex items-center gap-2">
        <Link2 className="h-4 w-4 text-[var(--color-accent-strong)]" />
        <div>
          <p className="section-tag mb-0.5">FUENTES JSON / R2</p>
          <p className="text-xs text-[var(--color-text-subtle)]">
            Se consultan solo por herramientas filtradas; nunca se envía el archivo completo al chat.
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {(Object.keys(LABELS) as Kind[]).map((kind) => {
          const cfg = sources[kind] ?? {};
          const state = status[kind];
          return (
            <div key={kind} className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface)] p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <label className="label mb-0">{LABELS[kind]}</label>
                <label className="flex items-center gap-2 text-2xs text-[var(--color-text-muted)]">
                  <input
                    type="checkbox"
                    checked={cfg.is_active ?? true}
                    onChange={(e) => update(kind, { is_active: e.target.checked })}
                  />
                  Activa
                </label>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  className="input flex-1 font-mono text-xs"
                  placeholder="https://pub-....r2.dev/precios.json"
                  value={cfg.url ?? ""}
                  onChange={(e) => update(kind, { url: e.target.value })}
                />
                <button
                  type="button"
                  className="btn-secondary px-3 py-2 text-2xs"
                  disabled={!tenantId || !cfg.url?.trim() || testing === kind}
                  onClick={() => test(kind)}
                  title={tenantId ? "Probar y validar el JSON" : "Guarda el cliente primero"}
                >
                  {testing === kind ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "PROBAR"}
                </button>
              </div>
              {state && (
                <div className={`mt-2 flex items-center gap-1.5 text-2xs ${state.ok ? "text-[var(--color-accent-strong)]" : "text-red-700"}`}>
                  {state.ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
                  {state.text}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
