import { useCallback, useEffect, useRef, useState } from "react";
import { meetingsApi } from "../lib/api";

/**
 * Hook de grabación EN VIVO usando Web Audio API.
 *
 * En vez de MediaRecorder (que produce fragmentos WebM/MP4 sin cabecera,
 * no transcribibles individualmente), captura PCM del micrófono y emite
 * chunks WAV de ~5 s: cada uno es un archivo VÁLIDO e independiente que el
 * STT transcribe apenas llega (transcripción en vivo).
 *
 * - Cola FIFO de subidas que NO bloquea la grabación (retry con backoff)
 * - Pausa/reanudación controlando la captura
 * - Screen Wake Lock mientras graba (celular no se apaga), re-adquirido al
 *   volver a la pestaña
 * - `stop()` drena la cola antes de resolver → luego llamar finish()
 */

export type RecorderState = "idle" | "recording" | "paused" | "stopped";

const SEGMENT_MS = 5_000;
const TARGET_RATE = 16_000;
const UPLOAD_ATTEMPTS = 3;
// VAD simple: si el RMS del segmento es menor a este umbral se considera
// silencio y NO se envía al STT (evita alucinaciones de Whisper tipo
// "Gracias por ver" / "Subtítulos por Amara.org" y ahorra costos).
const SILENCE_RMS = 0.01;

function rmsOf(samples: number[]): number {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / samples.length);
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buf);
  const writeStr = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

function decimateTo16k(samples: number[], srcRate: number): Float32Array {
  const ratio = Math.max(1, Math.round(srcRate / TARGET_RATE));
  const out = new Float32Array(Math.ceil(samples.length / ratio));
  for (let i = 0, j = 0; i < samples.length; i += ratio, j++) out[j] = samples[i];
  return out;
}

interface UseRecorderOptions {
  tenantId: number | null;
  meetingId: number | null;
  onUploaded?: (seq: number) => void;
}

export function useRecorder({ tenantId, meetingId, onUploaded }: UseRecorderOptions) {
  const [state, setState] = useState<RecorderState>("idle");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [chunksUploaded, setChunksUploaded] = useState(0);

  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const wakeLockRef = useRef<{ release: () => Promise<void> } | null>(null);
  const capturingRef = useRef(false);
  const samplesRef = useRef<number[]>([]);
  const elapsedRef = useRef(0);
  const segmentTimerRef = useRef<number | null>(null);
  const tickTimerRef = useRef<number | null>(null);
  const seqRef = useRef(0);
  const uploadChainRef = useRef<Promise<void>>(Promise.resolve());

  const cleanup = useCallback(() => {
    if (segmentTimerRef.current) window.clearInterval(segmentTimerRef.current);
    segmentTimerRef.current = null;
    if (tickTimerRef.current) window.clearInterval(tickTimerRef.current);
    tickTimerRef.current = null;
    try { processorRef.current?.disconnect(); } catch { /* noop */ }
    try { sourceRef.current?.disconnect(); } catch { /* noop */ }
    processorRef.current = null;
    sourceRef.current = null;
    try { void ctxRef.current?.close(); } catch { /* noop */ }
    ctxRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    wakeLockRef.current?.release?.().catch(() => undefined);
    wakeLockRef.current = null;
    capturingRef.current = false;
  }, []);

  const acquireWakeLock = useCallback(async () => {
    try {
      if (typeof navigator !== "undefined" && "wakeLock" in navigator) {
        const wl = (navigator as unknown as { wakeLock: { request: (t: string) => Promise<{ release: () => Promise<void> }> } }).wakeLock;
        wakeLockRef.current = await wl.request("screen");
      }
    } catch {
      /* no soportado; no es fatal */
    }
  }, []);

  const enqueueChunk = useCallback(
    (blob: Blob, durationMs: number, silent: boolean) => {
      if (!tenantId || !meetingId || blob.size === 0) return;
      const seq = seqRef.current++;
      uploadChainRef.current = uploadChainRef.current
        .then(async () => {
          for (let attempt = 1; attempt <= UPLOAD_ATTEMPTS; attempt++) {
            try {
              await meetingsApi.uploadChunk(tenantId, meetingId, seq, durationMs, blob, silent);
              setChunksUploaded((c) => c + 1);
              onUploaded?.(seq);
              return;
            } catch {
              if (attempt < UPLOAD_ATTEMPTS) {
                await new Promise((r) => setTimeout(r, 750 * attempt));
              } else {
                setError("No se pudo subir parte del audio (revisa tu conexión)");
              }
            }
          }
        })
        .catch(() => setError("No se pudo subir parte del audio"));
    },
    [tenantId, meetingId, onUploaded]
  );

  const flushSegment = useCallback(
    (finalMs: number) => {
      const samples = samplesRef.current;
      samplesRef.current = [];
      if (samples.length < Math.floor(TARGET_RATE * 0.4)) return; // < 400 ms: descartar
      const pcm = decimateTo16k(samples, ctxRef.current?.sampleRate ?? TARGET_RATE);
      const wav = encodeWav(pcm, TARGET_RATE);
      // Silencio → no transcribir (evita alucinaciones de Whisper).
      const silent = rmsOf(samples) < SILENCE_RMS;
      enqueueChunk(wav, finalMs, silent);
    },
    [enqueueChunk]
  );

  const start = useCallback(async () => {
    setError(null);
    setChunksUploaded(0);
    setElapsedMs(0);
    elapsedRef.current = 0;
    seqRef.current = 0;
    if (!tenantId || !meetingId) return;

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name = (e as { name?: string })?.name;
      if (name === "NotAllowedError") setError("Permiso de micrófono denegado. Habilítalo en el navegador y vuelve a intentarlo.");
      else if (name === "NotFoundError") setError("No se encontró un micrófono en este dispositivo.");
      else if (name === "NotReadableError") setError("El micrófono está en uso por otra aplicación.");
      else if (name === "SecurityError") setError("La grabación requiere una conexión segura (HTTPS).");
      else setError("No se pudo iniciar la grabación. Revisa el acceso al micrófono.");
      setState("idle");
      return;
    }

    cleanup();
    streamRef.current = stream;
    try {
      const Ctx = window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new Ctx();
      await ctx.resume();
      ctxRef.current = ctx;

      const source = ctx.createMediaStreamSource(stream);
      const processor = ctx.createScriptProcessor(4096, 1, 1);
      // Safari requiere que el processor esté conectado a destination para
      // disparar onaudioprocess; se enruta a un gain 0 para no escuchar eco.
      const silence = ctx.createGain();
      silence.gain.value = 0;
      source.connect(processor);
      processor.connect(silence);
      silence.connect(ctx.destination);
      sourceRef.current = source;
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        if (!capturingRef.current) return;
        const input = e.inputBuffer.getChannelData(0);
        for (let i = 0; i < input.length; i++) samplesRef.current.push(input[i]);
      };
    } catch {
      cleanup();
      setError("Este navegador no soporta captura de audio con Web Audio.");
      setState("idle");
      return;
    }

    capturingRef.current = true;
    setState("recording");
    await acquireWakeLock();

    segmentTimerRef.current = window.setInterval(() => {
      if (capturingRef.current) flushSegment(SEGMENT_MS);
    }, SEGMENT_MS);
    tickTimerRef.current = window.setInterval(() => {
      if (capturingRef.current) {
        elapsedRef.current += 500;
        setElapsedMs(elapsedRef.current);
      }
    }, 500);
  }, [tenantId, meetingId, enqueueChunk, flushSegment, cleanup, acquireWakeLock]);

  const pause = useCallback(() => {
    capturingRef.current = false;
    setState("paused");
  }, []);

  const resume = useCallback(() => {
    capturingRef.current = true;
    void ctxRef.current?.resume();
    setState("recording");
  }, []);

  const stop = useCallback((): Promise<void> => {
    return new Promise((resolve) => {
      if (samplesRef.current.length) {
        flushSegment(SEGMENT_MS);
      }
      cleanup();
      setState("stopped");
      uploadChainRef.current.then(() => resolve());
    });
  }, [flushSegment, cleanup]);

  // Re-adquirir wake lock al volver a la pestaña mientras se graba.
  useEffect(() => {
    const handler = () => {
      if (document.visibilityState === "visible" && ctxRef.current && capturingRef.current) {
        acquireWakeLock();
      }
    };
    document.addEventListener("visibilitychange", handler);
    return () => document.removeEventListener("visibilitychange", handler);
  }, [acquireWakeLock]);

  useEffect(() => () => cleanup(), [cleanup]);

  return { state, elapsedMs, error, chunksUploaded, start, pause, resume, stop };
}