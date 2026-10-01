import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Plus, Trash2, Menu, Send, Square, Check, MessageSquare } from "lucide-react";
import api from "../lib/api";
import { useTenant } from "../contexts/TenantContext";
import "../chat.css";

interface Conversation {
  id: number;
  title: string;
  created_at: string | null;
  updated_at: string | null;
}

interface ToolEvent {
  name: string;
  label: string;
  status: "running" | "done";
  ok?: boolean;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  tools?: ToolEvent[];
  streaming?: boolean;
}

type StreamEvent =
  | { type: "status"; stage?: string }
  | { type: "tool"; name: string; label: string; status: "running" | "done"; ok?: boolean }
  | { type: "delta"; text?: string }
  | { type: "done"; text?: string }
  | { type: "error"; message?: string };

const SUGGESTIONS = [
  { title: "Resumen de ventas", text: "Dame el resumen de ventas de este mes por canal." },
  { title: "Margen del mes", text: "¿Cómo estuvo el margen este mes comparado con el anterior?" },
  { title: "Productos top", text: "Muéstrame los 10 productos más vendidos del mes." },
  { title: "Cuentas por pagar", text: "¿Cuáles son las cuentas por pagar pendientes?" },
];

function fmtWhen(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("es-CO", { day: "2-digit", month: "short" });
}

export default function Chat() {
  const qc = useQueryClient();
  const { tenantId, activeTenant } = useTenant();

  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const justCreatedRef = useRef(false);

  const { data: conversations = [] } = useQuery({
    queryKey: ["chat-convs", tenantId],
    queryFn: () => api.get<Conversation[]>("/chat/conversations", { params: { tenant_id: tenantId } }).then((r) => r.data),
    enabled: tenantId !== null,
  });

  // Cargar mensajes al cambiar de conversación
  useEffect(() => {
    let cancelled = false;
    if (!tenantId || !activeId) return;
    // Si la conversación se acaba de crear para enviar un mensaje, no recargar
    // (borraría el mensaje en curso).
    if (justCreatedRef.current) { justCreatedRef.current = false; return; }
    api
      .get<ChatMessage[]>(`/chat/conversations/${activeId}/messages`, { params: { tenant_id: tenantId } })
      .then((r) => { if (!cancelled) setMessages(r.data); })
      .catch(() => { if (!cancelled) setMessages([]); });
    return () => { cancelled = true; };
  }, [activeId, tenantId]);

  // Abortar el stream si se sale de la página
  useEffect(() => () => { abortRef.current?.abort(); }, []);

  // Auto-scroll
  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, stage]);

  // Auto-grow del textarea
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [input]);

  const updateLastAssistant = (fn: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => {
      const copy = [...prev];
      for (let i = copy.length - 1; i >= 0; i--) {
        if (copy[i].role === "assistant") { copy[i] = fn(copy[i]); break; }
      }
      return copy;
    });
  };

  const handleEvent = (evt: StreamEvent) => {
    switch (evt.type) {
      case "status":
        setStage(evt.stage === "thinking" ? "Pensando" : "");
        break;
      case "tool":
        setStage("");
        updateLastAssistant((m) => {
          const tools = [...(m.tools ?? [])];
          if (evt.status === "running") {
            tools.push({ name: evt.name, label: evt.label, status: "running" });
          } else {
            const idx = tools.findIndex((t) => t.name === evt.name && t.status === "running");
            if (idx >= 0) tools[idx] = { ...tools[idx], status: "done", ok: evt.ok };
          }
          return { ...m, tools };
        });
        break;
      case "delta":
        updateLastAssistant((m) => ({ ...m, content: m.content + (evt.text ?? "") }));
        break;
      case "done":
        updateLastAssistant((m) => ({ ...m, streaming: false }));
        break;
      case "error":
        setError(evt.message ?? "Ocurrió un error.");
        updateLastAssistant((m) => ({ ...m, streaming: false }));
        break;
    }
  };

  const send = async (raw?: string) => {
    const text = (raw ?? input).trim();
    if (!text || streaming || !tenantId) return;
    setError("");
    setInput("");
    setSidebarOpen(false);

    let convId = activeId;
    try {
      if (!convId) {
        const r = await api.post<Conversation>("/chat/conversations", {}, { params: { tenant_id: tenantId } });
        convId = r.data.id;
        justCreatedRef.current = true;
        setActiveId(convId);
      }
    } catch {
      setError("No se pudo crear la conversación.");
      return;
    }

    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "", tools: [], streaming: true },
    ]);
    setStreaming(true);
    setStage("Pensando");

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await fetch(`/api/admin/chat/stream?tenant_id=${tenantId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ conversation_id: convId, message: text, tenant_id: tenantId }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) throw new Error("stream no disponible");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let reading = true;
      while (reading) {
        const { value, done } = await reader.read();
        if (done) { reading = false; break; }
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
          const line = block.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          try { handleEvent(JSON.parse(line.slice(5).trim()) as StreamEvent); } catch { /* ignore */ }
        }
      }
    } catch (e) {
      if ((e as Error)?.name !== "AbortError") {
        setError("Se perdió la conexión con el agente. Intenta de nuevo.");
        updateLastAssistant((m) => ({ ...m, streaming: false }));
      }
    } finally {
      setStreaming(false);
      setStage("");
      abortRef.current = null;
      qc.invalidateQueries({ queryKey: ["chat-convs", tenantId] });
    }
  };

  const stop = () => {
    abortRef.current?.abort();
    setStreaming(false);
    setStage("");
    updateLastAssistant((m) => ({ ...m, streaming: false }));
  };

  const newConversation = () => {
    stop();
    setActiveId(null);
    setMessages([]);
    setError("");
    setSidebarOpen(false);
    inputRef.current?.focus();
  };

  const removeConversation = async (id: number) => {
    if (!window.confirm("¿Eliminar esta conversación?")) return;
    await api.delete(`/chat/conversations/${id}`, { params: { tenant_id: tenantId } });
    if (activeId === id) { setActiveId(null); setMessages([]); }
    qc.invalidateQueries({ queryKey: ["chat-convs", tenantId] });
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  if (!tenantId) {
    return (
      <div className="vc-app" style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ textAlign: "center", color: "#9a978f" }}>
          <MessageSquare size={28} style={{ color: "#00c2a8", marginBottom: 10 }} />
          <p>Selecciona un cliente en el panel izquierdo para abrir el chat.</p>
        </div>
      </div>
    );
  }

  const showEmpty = messages.length === 0;

  return (
    <div className="vc-app">
      {sidebarOpen && <div className="vc-overlay show" onClick={() => setSidebarOpen(false)} />}

      {/* Sidebar */}
      <aside className={`vc-sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="vc-side-head">
          <div className="vc-brand">
            <div className="vc-logo">⬡</div>
            <div>
              <div className="vc-brand-name">Mind</div>
              <div className="vc-brand-sub">by Versat.ai</div>
            </div>
          </div>
          <button className="vc-new" onClick={newConversation}>
            <Plus size={16} /> Nueva conversación
          </button>
        </div>

        <div className="vc-conv-list">
          {conversations.length === 0 ? (
            <p className="vc-side-empty">Aún no tienes conversaciones.</p>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                className={`vc-conv ${activeId === c.id ? "active" : ""}`}
                onClick={() => { setActiveId(c.id); setSidebarOpen(false); }}
              >
                <div className="vc-conv-title">{c.title || "Nueva conversación"}</div>
                <div className="vc-conv-date">{fmtWhen(c.updated_at)}</div>
                <span
                  className="vc-conv-del"
                  role="button"
                  onClick={(e) => { e.stopPropagation(); removeConversation(c.id); }}
                >
                  <Trash2 size={14} />
                </span>
              </button>
            ))
          )}
        </div>

        <div className="vc-side-foot">
          <span className="vc-dot" /> {activeTenant?.name ?? "Cliente"}
        </div>
      </aside>

      {/* Main */}
      <div className="vc-main">
        <header className="vc-header">
          <button className="vc-menu-btn" onClick={() => setSidebarOpen((v) => !v)}>
            <Menu size={18} />
          </button>
          <div>
            <div className="vc-header-title">
              {conversations.find((c) => c.id === activeId)?.title || "Nuevo chat"}
            </div>
            <div className="vc-header-sub">Asistente de {activeTenant?.name ?? "tu empresa"}</div>
          </div>
          <div className="vc-header-spacer" />
          <span className="vc-pill"><span className="vc-dot" /> En línea</span>
        </header>

        <div className="vc-messages" ref={scrollerRef}>
          {showEmpty ? (
            <div className="vc-empty">
              <h1>Hola, soy <span className="vc-grad">Mind</span></h1>
              <p>Pregúntame por las ventas, márgenes, inventario o cualquier dato de tu negocio. Puedo consultar tus fuentes en tiempo real.</p>
              <div className="vc-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s.title} className="vc-suggestion" onClick={() => { setInput(s.text); inputRef.current?.focus(); }}>
                    <strong>{s.title}</strong>
                    <span>{s.text}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="vc-thread">
              {messages.map((m, i) =>
                m.role === "user" ? (
                  <div className="vc-row user" key={i}>
                    <div className="vc-bubble-user">{m.content}</div>
                  </div>
                ) : (
                  <div className="vc-row" key={i}>
                    <div className="vc-avatar">M</div>
                    <div className="vc-assistant">
                      {m.tools && m.tools.length > 0 && (
                        <div className="vc-tools">
                          {m.tools.map((t, ti) => (
                            <span key={ti} className={`vc-tool ${t.status}`}>
                              {t.status === "running" ? <span className="vc-spin" /> : <Check size={12} />}
                              {t.label}
                            </span>
                          ))}
                        </div>
                      )}

                      {m.content ? (
                        <div className="vc-md">
                          <Markdown remarkPlugins={[remarkGfm]}>{m.content}</Markdown>
                          {m.streaming && <span className="vc-cursor" />}
                        </div>
                      ) : (
                        m.streaming && (
                          <div className="vc-thinking">
                            <span /><span /><span />
                          </div>
                        )
                      )}
                    </div>
                  </div>
                )
              )}
            </div>
          )}
        </div>

        <div className="vc-composer-wrap">
          {error && <div className="vc-error">{error}</div>}
          <div className="vc-composer">
            <textarea
              ref={inputRef}
              className="vc-input"
              placeholder="Escribe tu pregunta…"
              value={input}
              rows={1}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
            />
            {streaming ? (
              <button className="vc-stop" onClick={stop} title="Detener">
                <Square size={15} />
              </button>
            ) : (
              <button className="vc-send" onClick={() => send()} disabled={!input.trim()} title="Enviar">
                <Send size={16} />
              </button>
            )}
          </div>
          <div className="vc-hint">Mind puede cometer errores. Verifica la información importante. Enter para enviar, Shift+Enter para salto de línea.</div>
        </div>
      </div>
    </div>
  );
}
