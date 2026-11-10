import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Mic, Square, Pause, Play, X, ArrowLeft, Circle, RefreshCw } from "lucide-react";
import { meetingsApi } from "../lib/api";
import type { Meeting, MeetingStatus } from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";
import { useRecorder } from "../hooks/useRecorder";
import { useNavigate } from "react-router-dom";

const STATUS_META: Record<MeetingStatus, { label: string; cls: string }> = {
  recording: { label: "GRABANDO", cls: "badge-red" },
  processing: { label: "PROCESANDO", cls: "badge-amber" },
  ready: { label: "LISTO", cls: "badge-green" },
  error: { label: "ERROR", cls: "badge-red" },
};

function fmtMs(ms: number) {
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

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

// ── Vista de grabación en vivo ────────────────────────────────────────────────

const pagePad = "px-4 sm:px-8";
const RECORDING_SESSION_KEY = "mind-active-recording";

function RecordingView({
  meeting,
  tenantId,
  onDone,
}: {
  meeting: Meeting;
  tenantId: number;
  onDone: () => void;
}) {
  const navigate = useNavigate();
  const [finishing, setFinishing] = useState(false);
  const { state, elapsedMs, error, chunksUploaded, start, pause, resume, stop } =
    useRecorder({ tenantId, meetingId: meeting.id });

  const alreadyStarted = state !== "idle";

  // Persistir el estado en sessionStorage para recuperación tras recarga
  useEffect(() => {
    sessionStorage.setItem(RECORDING_SESSION_KEY, JSON.stringify({
      meetingId: meeting.id, tenantId, title: meeting.title,
    }));
    return () => {
      sessionStorage.removeItem(RECORDING_SESSION_KEY);
    };
  }, [meeting.id, meeting.title, tenantId]);

  // Advertir al usuario si intenta cerrar la pestaña mientras graba
  useEffect(() => {
    if (!alreadyStarted || finishing) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [alreadyStarted, finishing]);

  // Transcripción en vivo: mientras se graba, se va mostrando lo transcrito.
  const { data: live } = useQuery({
    queryKey: ["meeting-transcript", tenantId, meeting.id],
    queryFn: () => meetingsApi.transcript(tenantId, meeting.id),
    enabled: alreadyStarted && !finishing,
    refetchInterval: 5000,
  });

  // Autoscroll: el contenedor baja solo conforme llega nueva transcripción.
  const liveRef = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (liveRef.current) {
      liveRef.current.scrollTop = liveRef.current.scrollHeight;
    }
  }, [live?.transcript]);

  const handleFinish = async () => {
    if (finishing) return;
    setFinishing(true);
    await stop();
    try {
      await meetingsApi.finish(tenantId, meeting.id);
      navigate(`/reuniones/${meeting.id}`);
    } catch {
      navigate(`/reuniones/${meeting.id}`);
    }
  };

  return (
    <div className={`${pagePad} py-8 max-w-2xl`}>
      <button className="btn-ghost mb-6" onClick={onDone}>
        <ArrowLeft className="w-3.5 h-3.5" /> Volver
      </button>

      <div className="border border-[#1a1a1a] bg-[#050505] p-4 sm:p-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="section-tag">// GRABACIÓN EN CURSO</p>
            <h2 className="text-xl font-bold text-white tracking-tight mt-1">{meeting.title}</h2>
          </div>
          <Circle className={`w-4 h-4 ${state === "recording" ? "text-red-500 animate-pulse" : "text-white"}`} />
        </div>

        <p className="font-mono text-4xl text-white tabular-nums">{fmtMs(elapsedMs)}</p>

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex items-center gap-3 flex-wrap">
          {!alreadyStarted ? (
            <button className="btn-primary" onClick={start}>
              <Mic className="w-3.5 h-3.5" /> Comenzar grabación
            </button>
          ) : (
            <>
              {state === "recording" ? (
                <button className="btn-ghost" onClick={pause}>
                  <Pause className="w-3.5 h-3.5" /> Pausar
                </button>
              ) : (
                <button className="btn-ghost" onClick={resume}>
                  <Play className="w-3.5 h-3.5" /> Reanudar
                </button>
              )}
              <button className="btn-primary" disabled={finishing} onClick={handleFinish}>
                <Square className="w-3.5 h-3.5" />
                {finishing ? "Finalizando…" : "Finalizar grabación"}
              </button>
            </>
          )}
        </div>

        {alreadyStarted && (
          <p className="font-mono text-[11px] text-white">
            {chunksUploaded} segmento(s) subido(s)
            {state === "paused" && " · pausada"}
          </p>
        )}

        {alreadyStarted && live?.transcript && (
          <div className="border-t border-[#1a1a1a] pt-4">
            <p className="section-tag mb-2">// Transcripción en vivo</p>
            <pre ref={liveRef} className="whitespace-pre-wrap text-sm text-white leading-relaxed max-h-56 overflow-y-auto">
              {live.transcript}
            </pre>
          </div>
        )}

        <p className="text-xs text-white leading-relaxed">
          Mantén MIND abierto durante la reunión. El audio se sube y transcribe
          por segmentos: si el teléfono se bloquea o cierras la pestaña, lo ya
          grabado quedará guardado y podrás finalizarlo desde el listado.
        </p>
      </div>
    </div>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function Reuniones() {
  const { tenantId } = useTenant();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [showNew, setShowNew] = useState(false);
  const [title, setTitle] = useState("");
  const [language, setLanguage] = useState<"es" | "en">("es");
  const [recording, setRecording] = useState<Meeting | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [restoreRec, setRestoreRec] = useState<Meeting | null>(null);

  // Recuperar grabación pendiente de sessionStorage (tras recarga)
  useEffect(() => {
    const raw = sessionStorage.getItem(RECORDING_SESSION_KEY);
    if (!raw || !tenantId) return;
    try {
      const { meetingId } = JSON.parse(raw);
      if (!meetingId) return;
      meetingsApi.get(tenantId, meetingId).then((m) => {
        if (m.status === "recording" || m.status === "processing") {
          setRestoreRec(m);
        }
      }).catch(() => {});
    } catch {
      sessionStorage.removeItem(RECORDING_SESSION_KEY);
    }
  }, [tenantId]);

  const { data: meetings = [], isLoading } = useQuery({
    queryKey: ["meetings", tenantId],
    queryFn: () => meetingsApi.list(tenantId as number),
    enabled: tenantId !== null,
    refetchInterval: (query) => {
      const rows = query.state.data as Meeting[] | undefined;
      const active = rows?.some((m) => m.status === "recording" || m.status === "processing");
      return active ? 4000 : false;
    },
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["meetings", tenantId] });

  const create = useMutation({
    mutationFn: (payload: { title: string; language: "es" | "en" }) =>
      meetingsApi.create(tenantId as number, payload.title, payload.language),
    onSuccess: (m) => {
      setShowNew(false);
      setTitle("");
      setLanguage("es");
      setCreateError(null);
      setRecording(m);
      invalidate();
    },
    onError: (e) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setCreateError(detail ?? "No se pudo crear la reunión");
      invalidate();
    },
  });

  const finish = useMutation({
    mutationFn: (id: number) => meetingsApi.finish(tenantId as number, id),
    onSuccess: invalidate,
  });

  if (!tenantId) {
    return (
      <div>
        <PageHeader tag="REUNIONES" title="Reuniones" description="Selecciona un cliente" />
        <div className="px-8 py-16 text-center">
          <p className="font-mono text-xs text-white uppercase tracking-widest">
            Selecciona un cliente en el panel izquierdo
          </p>
        </div>
      </div>
    );
  }

  const mobilePad = "lg:pt-0 pt-14";

  if (recording) {
    return (
      <div className={mobilePad}>
        <PageHeader tag="REUNIONES" title="Reuniones" description="Grabación de reuniones con transcripción y resumen automáticos" />
        <RecordingView meeting={recording} tenantId={tenantId} onDone={() => setRecording(null)} />
      </div>
    );
  }

  return (
    <div className={mobilePad}>
      <PageHeader
        tag="REUNIONES"
        title="Reuniones"
        description={`${meetings.length} reunión(es)`}
        action={
          <button className="btn-primary" onClick={() => setShowNew(true)}>
            <Plus className="w-3.5 h-3.5" /> Nueva reunión
          </button>
        }
      />

      {showNew && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center px-4">
          <div className="w-full max-w-md border border-[#2a2a2a] bg-[#0d0d0d] p-6 space-y-5">
            <div className="flex items-center justify-between">
              <p className="section-tag">// Nueva reunión</p>
              <button className="text-white hover:text-[#00e5a0]" onClick={() => { setShowNew(false); setCreateError(null); }}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <div>
              <label className="label text-white">Motivo de la reunión</label>
              <input
                className="input"
                value={title}
                placeholder="Ej: Junta directiva — presupuesto Q4"
                onChange={(e) => { setTitle(e.target.value); setCreateError(null); }}
                onKeyDown={(e) => { if (e.key === "Enter" && title.trim()) create.mutate({ title: title.trim(), language }); }}
              />
            </div>
            <div>
              <label className="label text-white">Idioma de la reunión</label>
              <select
                className="input"
                value={language}
                onChange={(e) => setLanguage(e.target.value === "en" ? "en" : "es")}
              >
                <option value="es">Español</option>
                <option value="en">English</option>
              </select>
              <p className="text-[11px] text-white mt-1.5">
                Se usa para la transcripción y mejora la precisión.
              </p>
            </div>
            {createError && <p className="text-xs text-red-400">{createError}</p>}
            {create.isPending && <p className="text-xs text-white">Creando…</p>}
            <div className="flex items-center gap-3">
              <button
                className="btn-primary"
                disabled={create.isPending || !title.trim()}
                onClick={() => create.mutate({ title: title.trim(), language })}
              >
                <Mic className="w-3.5 h-3.5" /> Crear y grabar
              </button>
              <button className="btn-ghost" onClick={() => setShowNew(false)}>Cancelar</button>
            </div>
            <p className="text-[11px] text-white leading-relaxed">
              Al crear se pedirá acceso al micrófono del dispositivo. Necesario
              HTTPS (o localhost).
            </p>
          </div>
        </div>
      )}

      <div className={`${pagePad} py-8`}>
        <div className="border border-[#1a1a1a]">
          <div className="hidden sm:grid grid-cols-12 bg-[#050505] border-b border-[#1a1a1a]">
            <div className="col-span-4 th">Título</div>
            <div className="col-span-2 th">Fecha</div>
            <div className="col-span-2 th">Duración</div>
            <div className="col-span-2 th">Estado</div>
            <div className="col-span-2 th">Acciones</div>
          </div>

          {isLoading ? (
            Array(3).fill(0).map((_, i) => (
              <div key={i} className="h-12 border-b border-[#111] animate-pulse" />
            ))
          ) : meetings.length === 0 ? (
            <p className="px-5 py-10 text-center font-mono text-xs text-white">SIN REUNIONES</p>
          ) : (
            <>
              {/* Desktop: tabla */}
              {meetings.map((m) => {
                const meta = STATUS_META[m.status];
                return (
                  <div
                    key={m.id}
                    className="hidden sm:grid grid-cols-12 border-b border-[#111] hover:bg-[#050505] transition-colors items-center cursor-pointer"
                    onClick={() => navigate(`/reuniones/${m.id}`)}
                  >
                    <div className="col-span-4 td">
                      <p className="text-sm text-white truncate">{m.title}</p>
                    </div>
                    <div className="col-span-2 td font-mono text-[11px] text-white">{fmtDate(m.created_at)}</div>
                    <div className="col-span-2 td font-mono text-[11px] text-white">{fmtDuration(m.duration_seconds)}</div>
                    <div className="col-span-2 td">
                      <span className={`badge ${meta.cls}`}>{meta.label}</span>
                    </div>
                    <div className="col-span-2 td">
                      {m.status === "recording" && (
                        <button
                          className="text-[11px] font-mono uppercase tracking-widest text-white px-2 py-1 border border-[#2a2a2a] hover:border-red-500 hover:text-red-400 transition-colors"
                          onClick={(e) => { e.stopPropagation(); finish.mutate(m.id); }}
                        >
                          Finalizar
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
              {/* Mobile: lista de cards */}
              <div className="sm:hidden space-y-2">
                {meetings.map((m) => {
                  const meta = STATUS_META[m.status];
                  return (
                    <div
                      key={m.id}
                      className="border border-[#1a1a1a] bg-[#050505] px-3 py-3 cursor-pointer"
                      onClick={() => navigate(`/reuniones/${m.id}`)}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs font-medium text-white truncate flex-1">{m.title}</p>
                        <span className={`badge ${meta.cls} shrink-0`}>{meta.label}</span>
                      </div>
                      <div className="flex items-center gap-3 mt-1.5">
                        <span className="font-mono text-[10px] text-white">{fmtDate(m.created_at)}</span>
                        <span className="font-mono text-[10px] text-white">{fmtDuration(m.duration_seconds)}</span>
                      </div>
                      {m.status === "recording" && (
                        <button
                          className="mt-2 text-[11px] font-mono uppercase tracking-widest text-white px-2 py-1 border border-[#2a2a2a] hover:border-red-500 hover:text-red-400 transition-colors"
                          onClick={(e) => { e.stopPropagation(); finish.mutate(m.id); }}
                        >
                          Finalizar
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}