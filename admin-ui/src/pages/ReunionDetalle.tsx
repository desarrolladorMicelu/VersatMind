import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { ArrowLeft, CheckCircle2, ListChecks, SquareCheck } from "lucide-react";
import { meetingsApi } from "../lib/api";
import type { Meeting } from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

const STATUS_LABEL: Record<string, { label: string; cls: string }> = {
  recording: { label: "GRABANDO", cls: "badge-red" },
  processing: { label: "PROCESANDO", cls: "badge-amber" },
  ready: { label: "LISTO", cls: "badge-green" },
  error: { label: "ERROR", cls: "badge-red" },
};

function fmtDuration(sec: number | null) {
  if (!sec) return "—";
  const total = Math.floor(sec);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function Section({ title, items }: { title: string; items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <h3 className="section-tag mb-2">{title}</h3>
      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 text-sm text-white leading-relaxed">
            <span className="text-[#00e5a0] mt-1.5">•</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ReunionDetalle() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { tenantId } = useTenant();

  const { data: meeting, isLoading } = useQuery<Meeting>({
    queryKey: ["meeting", tenantId, id],
    queryFn: () => meetingsApi.get(tenantId as number, Number(id)),
    enabled: tenantId !== null && !!id,
    refetchInterval: (query) => {
      const m = query.state.data as Meeting | undefined;
      return m?.status === "processing" ? 4000 : false;
    },
  });

  // La transcripción crece con el polling (processing): autoscroll al final.
  const transcriptRef = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [meeting?.transcript]);

  if (!tenantId) {
    return (
      <div>
        <PageHeader tag="REUNIÓN" title="Detalle" description="Selecciona un cliente" />
      </div>
    );
  }

  if (isLoading || !meeting) {
    return (
      <div>
        <PageHeader tag="REUNIÓN" title="Detalle" />
        <div className="px-8 py-16">
          <div className="h-12 border-b border-[#111] animate-pulse" />
        </div>
      </div>
    );
  }

  const meta = STATUS_LABEL[meeting.status] ?? { label: meeting.status.toUpperCase(), cls: "badge-slate" };
  const summary = meeting.summary ?? {};

  return (
    <div>
      <PageHeader
        tag="REUNIÓN"
        title={meeting.title}
        description={`${fmtDate(meeting.created_at)} · ${fmtDuration(meeting.duration_seconds)}`}
        action={
          <button className="btn-ghost" onClick={() => navigate("/reuniones")}>
            <ArrowLeft className="w-3.5 h-3.5" /> Volver
          </button>
        }
      />

      <div className="px-8 py-8 space-y-8 max-w-3xl">
        <div className="flex items-center gap-3">
          <span className={`badge ${meta.cls}`}>{meta.label}</span>
          <span className="font-mono text-[11px] text-white">
            creada por {meeting.created_by || "—"}
          </span>
        </div>

        {meeting.status === "error" && meeting.error_message && (
          <div className="border border-red-500/40 bg-red-500/5 p-4 text-sm text-red-400">
            {meeting.error_message}
          </div>
        )}

        {meeting.status === "processing" && (
          <div className="border border-[#2a2a2a] bg-[#050505] p-4">
            <p className="section-tag">// Procesando</p>
            <p className="text-sm text-white mt-2">
              Transcribiendo y generando el resumen. Esto puede tardar unos
              minutos.
            </p>
          </div>
        )}

        {meeting.status !== "recording" && (meeting.transcript || meeting.summary || meeting.status === "error") && (
          <>
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="border border-[#1a1a1a] bg-[#050505] p-5 space-y-4">
                  <div className="flex items-center gap-2">
                    <ListChecks className="w-4 h-4 text-[#00e5a0]" />
                    <h3 className="section-tag">Resumen estructurado</h3>
                  </div>
                  {summary.resumen_general && (
                      <div>
                        <h3 className="section-tag mb-2">Resumen general</h3>
                        <p className="text-sm text-white leading-relaxed">{summary.resumen_general}</p>
                      </div>
                    )}
                  <Section title="Puntos clave" items={summary.puntos_clave ?? []} />
                  <Section title="Decisiones" items={summary.decisiones ?? []} />
                  {(summary.tareas ?? []).length > 0 && (
                    <div>
                      <h3 className="section-tag mb-2">Tareas y responsables</h3>
                      <ul className="space-y-2">
                        {(summary.tareas ?? []).map((t, i) => (
                          <li key={i} className="flex gap-2 text-sm text-white leading-relaxed">
                            <SquareCheck className="w-4 h-4 text-[#00e5a0] flex-shrink-0 mt-0.5" />
                            <span>
                              {t.tarea}
                              {t.responsable ? (
                                <span className="text-white"> — <span className="text-[#00e5a0]">{t.responsable}</span></span>
                              ) : null}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {!summary.resumen_general && !summary.puntos_clave?.length && !summary.decisiones?.length && !summary.tareas?.length && (
                    <p className="text-xs text-white">
                      No se detectó contenido de reunión para resumir (revisa la
                      transcripción).
                    </p>
                  )}
                </div>

                <div className="border border-[#1a1a1a] bg-[#050505] p-5 space-y-4">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#00e5a0]" />
                    <h3 className="section-tag">Audio</h3>
                  </div>
                  <audio
                    controls
                    preload="none"
                    className="w-full"
                    src={meetingsApi.audioUrl(tenantId, meeting.id)}
                  />
                </div>
              </div>

              {meeting.transcript && (
                <div className="border border-[#1a1a1a] bg-[#050505] p-5">
                  <h3 className="section-tag mb-3">Transcripción</h3>
                  <pre ref={transcriptRef} className="whitespace-pre-wrap text-sm text-white leading-relaxed max-h-96 overflow-y-auto">
                    {meeting.transcript}
                  </pre>
                </div>
              )}
            </div>
          </>
        )}

        {meeting.status === "recording" && (
          <p className="text-sm text-white">La reunión sigue grabándose. Finalízala desde el listado.</p>
        )}
      </div>
    </div>
  );
}