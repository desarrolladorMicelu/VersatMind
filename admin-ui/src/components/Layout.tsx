import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useTenant } from "../contexts/TenantContext";
import {
  LayoutDashboard, Bot, Users, KeyRound,
  Shield, Clock, MessageSquare, Activity, LogOut,
  Building2, ChevronDown, Coins, CalendarClock, BookOpen, MessagesSquare, Mail, Mic,
  ShieldCheck,
} from "lucide-react";
import { useState, useRef, useEffect } from "react";
import type { Tenant } from "../lib/api";

const NAV_SUPERADMIN = [
  { to: "/chat", icon: MessagesSquare, label: "Chat" },
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/reuniones", icon: Mic, label: "Reuniones" },
  { to: "/tenants", icon: Building2, label: "Clientes" },
  { to: "/consumo", icon: Coins, label: "Consumo" },
  { to: "/programados", icon: CalendarClock, label: "Programados" },
  { to: "/conocimiento", icon: BookOpen, label: "Conocimiento" },
  { to: "/integraciones", icon: Mail, label: "Integraciones" },
  { to: "/agente", icon: Bot, label: "Agente" },
  { to: "/usuarios", icon: Users, label: "Usuarios" },
  { to: "/accesos", icon: KeyRound, label: "Accesos" },
  { to: "/roles", icon: Shield, label: "Roles" },
  { to: "/tareas", icon: Clock, label: "Tareas" },
  { to: "/historial", icon: MessageSquare, label: "Historial" },
  { to: "/auditoria", icon: Activity, label: "Auditoría" },
];

const NAV_TENANT = [
  { to: "/chat", icon: MessagesSquare, label: "Chat" },
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/reuniones", icon: Mic, label: "Reuniones" },
  { to: "/consumo", icon: Coins, label: "Consumo" },
  { to: "/programados", icon: CalendarClock, label: "Programados" },
  { to: "/conocimiento", icon: BookOpen, label: "Conocimiento" },
  { to: "/integraciones", icon: Mail, label: "Integraciones" },
  { to: "/agente", icon: Bot, label: "Agente" },
  { to: "/usuarios", icon: Users, label: "Usuarios" },
  { to: "/accesos", icon: KeyRound, label: "Accesos" },
  { to: "/roles", icon: Shield, label: "Roles" },
  { to: "/tareas", icon: Clock, label: "Tareas" },
  { to: "/historial", icon: MessageSquare, label: "Historial" },
  { to: "/auditoria", icon: Activity, label: "Auditoría" },
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
      <div className="rounded-lg border border-[#1f232a] bg-[#0e1013] px-3 py-2.5">
        <p className="mb-1 text-2xs font-semibold uppercase tracking-[0.1em] text-[#667085]">Cliente</p>
        <p className="truncate text-xs font-medium text-[#34d399]">
          {activeTenant?.name ?? "—"}
        </p>
      </div>
    );
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-[#1f232a] bg-[#0e1013] px-3 py-2.5 transition-colors hover:border-[#343b45]"
      >
        <div className="min-w-0 text-left">
          <p className="text-2xs font-semibold uppercase tracking-[0.1em] text-[#667085]">Cliente activo</p>
          <p className="mt-1 truncate text-xs font-medium text-[#e8ebf0]">
            {activeTenant?.name ?? "Todos"}
          </p>
        </div>
        <ChevronDown className={`h-3.5 w-3.5 flex-shrink-0 text-[#7d8592] transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-60 overflow-y-auto rounded-lg border border-[#343b45] bg-[#14171c] p-1 shadow-2xl">
          {/* Opción "todos" solo para superadmin */}
          <button
            onClick={() => { setActiveTenant(null); setOpen(false); }}
            className={`w-full rounded-md px-2.5 py-2 text-left transition-colors hover:bg-white/5 ${
              activeTenant === null ? "text-[#34d399]" : "text-[#a8b0bd]"
            }`}
          >
            <p className="text-xs font-medium">Todos los clientes</p>
          </button>
          {tenants.map((t: Tenant) => (
            <button
              key={t.id}
              onClick={() => { setActiveTenant(t); setOpen(false); }}
              className={`w-full rounded-md px-2.5 py-2 text-left transition-colors hover:bg-white/5 ${
                activeTenant?.id === t.id ? "bg-[#34d399]/10" : ""
              }`}
            >
              <div className="flex items-center gap-2.5">
                <div className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${t.is_active ? "bg-[#34d399]" : "bg-[#343b45]"}`} />
                <div className="min-w-0">
                  <p className={`truncate text-xs font-medium ${activeTenant?.id === t.id ? "text-[#34d399]" : "text-[#e8ebf0]"}`}>
                    {t.name}
                  </p>
                  <p className="truncate text-2xs text-[#7d8592]">{t.slug}</p>
                </div>
              </div>
            </button>
          ))}
          {tenants.length === 0 && (
            <p className="px-3 py-3 text-center text-xs text-[#7d8592]">Sin clientes</p>
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
  const NAV = isSuperAdmin ? NAV_SUPERADMIN : NAV_TENANT;
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-[#0b0c0e]">

      {/* Overlay móvil */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed lg:relative inset-y-0 left-0 z-50
        flex flex-col w-72 lg:w-60 bg-[#101216] border-r border-[#262b33] shadow-[1px_0_0_rgba(255,255,255,0.02)] flex-shrink-0
        transition-transform duration-300
        ${sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
      `}>

        {/* Logo */}
        <div className="px-4 py-5 border-b border-[#1f232a]">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#34d399]/25 bg-[#34d399]/10">
              <span className="text-sm font-bold text-[#34d399]">M</span>
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold tracking-tight text-white">Mind</span>
                <span className="text-xs font-medium text-[#7d8592]">Admin</span>
                {isSuperAdmin && (
                  <span className="rounded border border-[#34d399]/25 bg-[#34d399]/10 px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-[0.04em] text-[#34d399]">
                    Super
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-2xs font-medium text-[#7d8592]">by Versat</p>
            </div>
          </div>
        </div>

        {/* Selector de tenant */}
        <div className="px-3 py-3 border-b border-[#1f232a]">
          <TenantSelector />
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2.5 py-4 space-y-0.5 overflow-y-auto">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `nav-link ${isActive ? "active text-[#34d399]" : ""}`
              }
            >
              <Icon className="w-3.5 h-3.5 flex-shrink-0" />
              {label}
            </NavLink>
          ))}

          {isSuperAdmin && (
            <div className="pt-4 mt-4 border-t border-[#1f232a]">
              <p className="px-3 pb-1.5 text-2xs font-semibold uppercase tracking-[0.12em] text-[#667085]">
                Sistema
              </p>
              <NavLink
                to="/superadmins"
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  `nav-link ${isActive ? "active text-[#34d399]" : ""}`
                }
              >
                <ShieldCheck className="w-3.5 h-3.5 flex-shrink-0" />
                Super Admins
              </NavLink>
            </div>
          )}
        </nav>

        {/* User */}
        <div className="border-t border-[#1f232a] px-3 py-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2.5">
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border border-[#34d399]/25 bg-[#34d399]/10">
                <span className="text-xs font-semibold text-[#34d399]">
                  {username?.[0]?.toUpperCase()}
                </span>
              </div>
              <span className="truncate text-xs font-medium text-[#e8ebf0]">{username}</span>
            </div>
            <button
              onClick={async () => { await logout(); navigate("/login"); }}
              className="rounded-md p-1.5 text-[#7d8592] transition-colors hover:bg-red-500/10 hover:text-red-400"
              title="Salir"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto bg-[#0b0c0e] min-w-0">
        {/* Hamburger */}
        <button
          onClick={() => setSidebarOpen((v) => !v)}
          className="lg:hidden fixed top-4 left-4 z-30 w-9 h-9 flex items-center justify-center border border-[#262b33] bg-[#101216] hover:bg-[#14171c]"
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
