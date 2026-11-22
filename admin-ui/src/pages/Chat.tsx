import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowLeft, Check, Folder, History, LayoutDashboard, LogOut, Menu,
  MessageSquare, MoreHorizontal, PanelLeftClose, PanelLeftOpen, Plus,
  Send, Settings, Square, Trash2, X,
} from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
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

type Panel = "config" | "projects" | null;

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
  const navigate = useNavigate();
  const { username, role, logout } = useAuth();
  const { tenantId, activeTenant, tenants, setActiveTenant, isSuperAdmin } = useTenant();

  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [panel, setPanel] = useState<Panel>(null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const justCreatedRef = useRef(false);

  const { data: conversations = [] } = useQuery({
    queryKey: ["chat-convs", tenantId],
    queryFn: () => api.get<Conversation[]>("/chat/conversations", { params: { tenant_id: tenantId } }).then((r) => r.data),
    enabled: tenantId !== null,
  });

  useEffect(() => {
    let cancelled = false;
    if (!tenantId || !activeId) return;
    if (justCreatedRef.current) { justCreatedRef.current = false; return; }
    api
      .get<ChatMessage[]>(`/chat/conversations/${activeId}/messages`, { params: { tenant_id: tenantId } })
      .then((r) => { if (!cancelled) setMessages(r.data); })
      .catch(() => { if (!cancelled) setMessages([]); });
    return () => { cancelled = true; };
  }, [activeId, tenantId]);

  useEffect(() => () => { abortRef.current?.abort(); }, []);

  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, stage]);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [input]);

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menuOpen]);

  useEffect(() => {
    if (!panel) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setPanel(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [panel]);

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
    setMenuOpen(false);

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
    setMenuOpen(false);
    inputRef.current?.focus();
  };

  const removeConversation = async (id: number) => {
    if (!window.confirm("¿Eliminar esta conversación?")) return;
    await api.delete(`/chat/conversations/${id}`, { params: { tenant_id: tenantId } });
    if (activeId === id) { setActiveId(null); setMessages([]); }
    qc.invalidateQueries({ queryKey: ["chat-convs", tenantId] });
  };

  const openConversation = (id: number) => {
    setActiveId(id);
    setSidebarOpen(false);
    setMenuOpen(false);
  };

  const chooseTenant = (id: number) => {
    const tenant = tenants.find((t) => t.id === id);
    if (!tenant) return;
    setActiveTenant(tenant);
    setActiveId(null);
    setMessages([]);
    setError("");
  };

  const openPanel = (next: Panel) => {
    setPanel(next);
    setSidebarOpen(false);
    setMenuOpen(false);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const activeConversation = conversations.find((c) => c.id === activeId);
  const showEmpty = messages.length === 0;

  if (!tenantId) {
    return (
      <div className="vc-app" style={{ alignItems: "center", justifyContent: "center" }}>
        <div className="vc-empty" style={{ textAlign: "center" }}>
          <div className="vc-empty-mark" style={{ margin: "0 auto var(--space-4)" }}>M</div>
          <h1 className="vc-empty-title">Selecciona un cliente</h1>
          <p className="vc-empty-sub" style={{ margin: "var(--space-3) auto var(--space-6)" }}>
            Elige un cliente en el panel para comenzar a conversar.
          </p>
          <button className="btn-secondary" onClick={() => navigate("/")}>
            <LayoutDashboard size={14} /> Ir al panel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="vc-app">
      {sidebarOpen && <div className="vc-overlay show" onClick={() => setSidebarOpen(false)} />}

      <aside className={`vc-sidebar ${collapsed ? "collapsed" : ""} ${sidebarOpen ? "open" : ""}`}>
        <div className="vc-side-top">
          <div className="vc-brand">
            <div className="vc-logo">M</div>
            <div className="vc-brand-text">
              <div className="vc-brand-name">Mind</div>
              <div className="vc-brand-sub">by Versat</div>
            </div>
          </div>
          <button
            className="vc-collapse"
            onClick={() => setCollapsed((v) => !v)}
            title={collapsed ? "Expandir menú" : "Colapsar menú"}
            aria-label={collapsed ? "Expandir menú" : "Colapsar menú"}
          >
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
          <button
            className="vc-mobile-close"
            onClick={() => setSidebarOpen(false)}
            aria-label="Cerrar menú"
          >
            <X size={18} />
          </button>
        </div>

        <div className="vc-side-body">
          <button className="vc-new" onClick={newConversation} title="Nuevo chat">
            <Plus size={16} />
            <span>Nuevo chat</span>
          </button>

          <nav className="vc-nav" aria-label="Navegación del chat">
            <button className="vc-nav-item" onClick={() => setCollapsed(false)} title="Historial">
              <History className="vc-nav-icon" size={16} />
              <span className="vc-nav-label">Historial</span>
            </button>
            <button className="vc-nav-item" onClick={() => openPanel("projects")} title="Proyectos">
              <Folder className="vc-nav-icon" size={16} />
              <span className="vc-nav-label">Proyectos</span>
              <span className="vc-nav-badge">Pronto</span>
            </button>
            <button className="vc-nav-item" onClick={() => openPanel("config")} title="Configuración">
              <Settings className="vc-nav-icon" size={16} />
              <span className="vc-nav-label">Configuración</span>
            </button>
            <div className="vc-nav-sep" />
            <button className="vc-nav-item" onClick={() => navigate("/")} title="Volver al panel">
              <LayoutDashboard className="vc-nav-icon" size={16} />
              <span className="vc-nav-label">Panel de administración</span>
            </button>
          </nav>

          <div className="vc-side-section">
            <span>Recientes</span>
            <span>{conversations.length}</span>
          </div>
          <div className="vc-conv-list">
            {conversations.length === 0 ? (
              <p className="vc-side-empty">Tus conversaciones aparecerán aquí.</p>
            ) : (
              conversations.map((c) => (
                <button
                  key={c.id}
                  className={`vc-conv ${activeId === c.id ? "active" : ""}`}
                  onClick={() => openConversation(c.id)}
                  title={c.title || "Nueva conversación"}
                >
                  <MessageSquare className="vc-conv-icon" size={14} />
                  <span className="vc-conv-text">
                    <span className="vc-conv-title">{c.title || "Nueva conversación"}</span>
                    <span className="vc-conv-date">{fmtWhen(c.updated_at)}</span>
                  </span>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="vc-side-foot">
          <button className="vc-tenant" onClick={() => openPanel("config")} title="Cambiar cliente">
            <span className="vc-tenant-dot" />
            <span className="vc-tenant-text">
              <span className="vc-tenant-label">Cliente</span>
              <span className="vc-tenant-name">{activeTenant?.name ?? "Tu empresa"}</span>
            </span>
          </button>
        </div>
      </aside>

      <div className="vc-main">
        <header className="vc-header">
          <button className="vc-menu-btn" onClick={() => setSidebarOpen(true)} aria-label="Abrir menú">
            <Menu size={18} />
          </button>

          <button className="vc-back" onClick={() => navigate("/")} title="Volver al panel de administración">
            <ArrowLeft size={16} />
            <span>Panel</span>
          </button>

          <div className="vc-header-info">
            <div className="vc-header-title">{activeConversation?.title || "Nuevo chat"}</div>
            <div className="vc-header-sub">Asistente de {activeTenant?.name ?? "tu empresa"}</div>
          </div>

          <div className="vc-header-actions" ref={menuRef}>
            <button
              className="vc-icon-btn"
              onClick={() => setMenuOpen((v) => !v)}
              aria-label="Más opciones"
              aria-expanded={menuOpen}
            >
              <MoreHorizontal size={18} />
            </button>
            {menuOpen && (
              <div className="vc-menu-pop">
                <button className="vc-menu-item" onClick={newConversation}>
                  <Plus size={14} /> Nuevo chat
                </button>
                {activeId !== null && (
                  <button
                    className="vc-menu-item danger"
                    onClick={() => { setMenuOpen(false); removeConversation(activeId); }}
                  >
                    <Trash2 size={14} /> Eliminar conversación
                  </button>
                )}
                <div className="vc-menu-sep" />
                <button className="vc-menu-item" onClick={() => openPanel("config")}>
                  <Settings size={14} /> Configuración
                </button>
              </div>
            )}
          </div>
        </header>

        <div className="vc-messages" ref={scrollerRef}>
          {showEmpty ? (
            <div className="vc-empty">
              <div className="vc-empty-mark">M</div>
              <h1 className="vc-empty-title">¿En qué puedo ayudarte?</h1>
              <p className="vc-empty-sub">
                Pregunta por ventas, márgenes, inventario o cualquier dato de tu negocio.
                Consulto tus fuentes en tiempo real.
              </p>
              <div className="vc-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s.title} className="vc-suggestion" onClick={() => send(s.text)}>
                    <span className="vc-suggestion-title">{s.title}</span>
                    <span className="vc-suggestion-text">{s.text}</span>
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
                        m.streaming && <p className="vc-thinking-label">{stage || "Pensando…"}</p>
                      )}
                    </div>
                  </div>
                )
              )}
            </div>
          )}
        </div>

        <div className="vc-composer-wrap">
          <div className="vc-composer-inner">
            {error && <div className="vc-error">{error}</div>}
            <div className="vc-composer">
              <textarea
                ref={inputRef}
                className="vc-input"
                placeholder="Escribe un mensaje…"
                value={input}
                rows={1}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
              />
              {streaming ? (
                <button className="vc-stop" onClick={stop} title="Detener" aria-label="Detener respuesta">
                  <Square size={14} />
                </button>
              ) : (
                <button
                  className="vc-send"
                  onClick={() => send()}
                  disabled={!input.trim()}
                  title="Enviar"
                  aria-label="Enviar mensaje"
                >
                  <Send size={15} />
                </button>
              )}
            </div>
            <p className="vc-hint">Mind puede cometer errores. Verifica la información importante.</p>
          </div>
        </div>
      </div>

      {panel && (
        <div className="vc-modal-backdrop" onClick={() => setPanel(null)}>
          <div className="vc-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="vc-modal-head">
              <div>
                <h2 className="vc-modal-title">{panel === "config" ? "Configuración" : "Proyectos"}</h2>
                <p className="vc-modal-sub">
                  {panel === "config"
                    ? "Cuenta, cliente activo y acceso al panel."
                    : "Un espacio para organizar tus conversaciones."}
                </p>
              </div>
              <button className="vc-icon-btn" onClick={() => setPanel(null)} aria-label="Cerrar">
                <X size={18} />
              </button>
            </div>

            {panel === "config" ? (
              <>
                <div className="vc-modal-body">
                  <div>
                    <div className="vc-settings-row">
                      <span className="vc-settings-label">Cuenta</span>
                      <span className="vc-settings-value">{username}</span>
                    </div>
                    <div className="vc-settings-row">
                      <span className="vc-settings-label">Rol</span>
                      <span className="vc-settings-value">
                        {role === "superadmin" ? "Super admin" : "Administrador"}
                      </span>
                    </div>
                  </div>

                  {isSuperAdmin && tenants.length > 0 ? (
                    <div className="vc-field">
                      <label className="label" htmlFor="chat-tenant">Cliente activo</label>
                      <select
                        id="chat-tenant"
                        className="vc-select"
                        value={activeTenant?.id ?? ""}
                        onChange={(e) => chooseTenant(Number(e.target.value))}
                      >
                        {tenants.map((t) => (
                          <option key={t.id} value={t.id}>{t.name}</option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <div className="vc-settings-row">
                      <span className="vc-settings-label">Cliente</span>
                      <span className="vc-settings-value">{activeTenant?.name ?? "Tu empresa"}</span>
                    </div>
                  )}
                </div>

                <div className="vc-modal-actions">
                  <button
                    className="btn-primary"
                    onClick={() => { setPanel(null); setSidebarOpen(false); navigate("/"); }}
                  >
                    <LayoutDashboard size={14} /> Ir al panel
                  </button>
                  <button
                    className="btn-ghost"
                    onClick={async () => { await logout(); navigate("/login"); }}
                  >
                    <LogOut size={14} /> Cerrar sesión
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="vc-modal-body">
                  <div className="vc-project-note">
                    <Folder size={18} />
                    <div>
                      Muy pronto podrás agrupar conversaciones por cliente, iniciativa o equipo.
                      El acceso ya está reservado en la barra lateral.
                    </div>
                  </div>
                </div>
                <div className="vc-modal-actions">
                  <button className="btn-secondary" onClick={() => setPanel(null)}>Entendido</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
