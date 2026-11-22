import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useTenant } from "../contexts/TenantContext";
import {
  LayoutDashboard, Bot, Users, KeyRound,
  Shield, Clock, MessageSquare, Activity, LogOut,
  Building2, ChevronDown, Coins, CalendarClock, BookOpen, MessagesSquare, Mail, Mic,
  ShieldCheck, ArrowUpRight,
} from "lucide-react";
import { useState, useRef, useEffect } from "react";
import type { Tenant } from "../lib/api";

const NAV_GROUPS_SUPERADMIN = [
  {
    title: "Principal",
    items: [
      { to: "/chat", icon: MessagesSquare, label: "Asistente" },
      { to: "/", icon: LayoutDashboard, label: "Resumen" },
    ],
  },
  {
    title: "Operación",
    items: [
      { to: "/reuniones", icon: Mic, label: "Reuniones" },
      { to: "/programados", icon: CalendarClock, label: "Programados" },
      { to: "/conocimiento", icon: BookOpen, label: "Conocimiento" },
      { to: "/integraciones", icon: Mail, label: "Integraciones" },
      { to: "/agente", icon: Bot, label: "Agente" },
      { to: "/consumo", icon: Coins, label: "Consumo" },
    ],
  },
  {
    title: "Administración",
    items: [
      { to: "/tenants", icon: Building2, label: "Clientes" },
      { to: "/usuarios", icon: Users, label: "Usuarios" },
      { to: "/accesos", icon: KeyRound, label: "Accesos" },
      { to: "/roles", icon: Shield, label: "Roles" },
      { to: "/tareas", icon: Clock, label: "Tareas" },
      { to: "/historial", icon: MessageSquare, label: "Historial" },
      { to: "/auditoria", icon: Activity, label: "Auditoría" },
    ],
  },
  {
    title: "Sistema",
    items: [
      { to: "/superadmins", icon: ShieldCheck, label: "Superadmins" },
    ],
  },
];

const NAV_GROUPS_TENANT = [
  {
    title: "Principal",
    items: [
      { to: "/chat", icon: MessagesSquare, label: "Asistente" },
      { to: "/", icon: LayoutDashboard, label: "Resumen" },
    ],
  },
  {
    title: "Operación",
    items: [
      { to: "/reuniones", icon: Mic, label: "Reuniones" },
      { to: "/programados", icon: CalendarClock, label: "Programados" },
      { to: "/conocimiento", icon: BookOpen, label: "Conocimiento" },
      { to: "/integraciones", icon: Mail, label: "Integraciones" },
      { to: "/agente", icon: Bot, label: "Agente" },
      { to: "/consumo", icon: Coins, label: "Consumo" },
    ],
  },
  {
    title: "Administración",
    items: [
      { to: "/usuarios", icon: Users, label: "Usuarios" },
      { to: "/accesos", icon: KeyRound, label: "Accesos" },
      { to: "/roles", icon: Shield, label: "Roles" },
      { to: "/tareas", icon: Clock, label: "Tareas" },
      { to: "/historial", icon: MessageSquare, label: "Historial" },
      { to: "/auditoria", icon: Activity, label: "Auditoría" },
    ],
  },
];

// ── Selector de tenant ────────────────────────────────────────────────────────

function TenantSelector() {
  const { tenants, activeTenant, setActiveTenant, isSuperAdmin } = useTenant();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (!isSuperAdmin) {
    // Tenant admin: muestra su tenant fijo, sin selector
    return (
      <div className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] px-3 py-2.5">
        <p className="mb-1 text-2xs font-semibold uppercase tracking-[0.1em] text-[var(--color-text-subtle)]">Cliente</p>
        <p className="truncate text-xs font-medium text-[var(--color-accent-strong)]">
          {activeTenant?.name ?? "—"}
        </p>
      </div>
    );
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] px-3 py-2.5 transition-colors hover:border-[var(--color-border)]"
      >
        <div className="min-w-0 text-left">
          <p className="text-2xs font-semibold uppercase tracking-[0.1em] text-[var(--color-text-subtle)]">Cliente activo</p>
          <p className="mt-1 truncate text-xs font-medium text-[var(--color-text)]">
            {activeTenant?.name ?? "Todos"}
          </p>
        </div>
        <ChevronDown className={`h-3.5 w-3.5 flex-shrink-0 text-[var(--color-text-subtle)] transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-60 overflow-y-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-1 shadow-2xl">
          {/* Opción "todos" solo para superadmin */}
          <button
            onClick={() => { setActiveTenant(null); setOpen(false); }}
            className={`w-full rounded-md px-2.5 py-2 text-left transition-colors hover:bg-black/5 ${
              activeTenant === null ? "text-[var(--color-accent-strong)]" : "text-[var(--color-text-muted)]"
            }`}
          >
            <p className="text-xs font-medium">Todos los clientes</p>
          </button>
          {tenants.map((t: Tenant) => (
            <button
              key={t.id}
              onClick={() => { setActiveTenant(t); setOpen(false); }}
              className={`w-full rounded-md px-2.5 py-2 text-left transition-colors hover:bg-black/5 ${
                activeTenant?.id === t.id ? "bg-[var(--color-accent-surface)]" : ""
              }`}
            >
              <div className="flex items-center gap-2.5">
                <div className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${t.is_active ? "bg-accent" : "bg-[var(--color-border)]"}`} />
                <div className="min-w-0">
                  <p className={`truncate text-xs font-medium ${activeTenant?.id === t.id ? "text-[var(--color-accent-strong)]" : "text-[var(--color-text)]"}`}>
                    {t.name}
                  </p>
                  <p className="truncate text-2xs text-[var(--color-text-subtle)]">{t.slug}</p>
                </div>
              </div>
            </button>
          ))}
          {tenants.length === 0 && (
            <p className="px-3 py-3 text-center text-xs text-[var(--color-text-subtle)]">Sin clientes</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Layout principal ──────────────────────────────────────────────────────────

export default function Layout() {
  const { username, logout, role } = useAuth();
  const navigate = useNavigate();
  const isSuperAdmin = role === "superadmin";
  const NAV_GROUPS = isSuperAdmin ? NAV_GROUPS_SUPERADMIN : NAV_GROUPS_TENANT;
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--color-bg)]">

      {/* Overlay móvil */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed lg:relative inset-y-0 left-0 z-50
        flex flex-col w-72 lg:w-64 bg-[var(--color-bg-elevated)] border-r border-[var(--color-border)] shadow-[1px_0_0_var(--color-border-subtle)] flex-shrink-0
        transition-transform duration-300
        ${sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
      `}>

        {/* Logo */}
        <div className="px-4 py-5 border-b border-[var(--color-border-subtle)]">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--color-accent)] bg-[var(--color-accent)]">
              <span className="text-sm font-bold text-[var(--color-accent-contrast)]">M</span>
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold tracking-tight text-[var(--color-text)]">Mind</span>
                <span className="text-xs font-medium text-[var(--color-text-subtle)]">Admin</span>
                {isSuperAdmin && (
                  <span className="rounded-full border border-[var(--color-accent-border)] bg-[var(--color-accent-surface)] px-1.5 py-0.5 text-3xs font-semibold leading-none text-[var(--color-accent-strong)]">
                    Super
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-2xs font-medium text-[var(--color-text-subtle)]">by Versat</p>
            </div>
          </div>
        </div>

        {/* Selector de tenant */}
        <div className="px-3 py-3 border-b border-[var(--color-border-subtle)]">
          <TenantSelector />
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
          {NAV_GROUPS.map((group) => (
            <div key={group.title}>
              <p className="px-2 pb-2 text-2xs font-semibold uppercase tracking-[0.1em] text-[var(--color-text-subtle)]">
                {group.title}
              </p>
              <div className="space-y-0.5">
                {group.items.map(({ to, icon: Icon, label }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === "/"}
                    onClick={() => setSidebarOpen(false)}
                    className={({ isActive }) =>
                      `nav-link ${isActive ? "active text-[var(--color-accent-strong)]" : ""}`
                    }
                  >
                    <Icon className="h-4 w-4 flex-shrink-0" />
                    {label}
                    {to === "/chat" && (
                      <ArrowUpRight className="ml-auto h-3.5 w-3.5 flex-shrink-0 opacity-40" />
                    )}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* User */}
        <div className="border-t border-[var(--color-border-subtle)] px-3 py-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2.5">
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border border-[var(--color-accent)] bg-[var(--color-accent)]">
                <span className="text-xs font-semibold text-[var(--color-accent-contrast)]">
                  {username?.[0]?.toUpperCase()}
                </span>
              </div>
              <span className="truncate text-xs font-medium text-[var(--color-text)]">{username}</span>
            </div>
            <button
              onClick={async () => { await logout(); navigate("/login"); }}
              className="rounded-md p-1.5 text-[var(--color-text-subtle)] transition-colors hover:bg-red-100 hover:text-red-700"
              title="Salir"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto bg-[var(--color-bg)] min-w-0">
        {/* Hamburger */}
        <button
          onClick={() => setSidebarOpen((v) => !v)}
          className="lg:hidden fixed top-4 left-4 z-30 w-9 h-9 flex items-center justify-center border border-[var(--color-border)] bg-[var(--color-bg-elevated)] hover:bg-[var(--color-surface)]"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="white" strokeWidth="1.5">
            <line x1="2" y1="3" x2="12" y2="3" />
            <line x1="2" y1="7" x2="12" y2="7" />
            <line x1="2" y1="11" x2="12" y2="11" />
          </svg>
        </button>
        <Outlet />
      </main>

    </div>
  );
}
