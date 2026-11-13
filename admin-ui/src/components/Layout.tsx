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
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/chat", icon: MessagesSquare, label: "Chat" },
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
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/chat", icon: MessagesSquare, label: "Chat" },
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
      <div className="px-3 py-2 border border-[#1a1a1a] bg-[#050505]">
        <p className="font-mono text-[9px] uppercase tracking-widest text-white mb-1">CLIENTE</p>
        <p className="text-xs font-medium text-[#00e5a0] truncate">
          {activeTenant?.name ?? "—"}
        </p>
      </div>
    );
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full px-3 py-2 border border-[#1a1a1a] bg-[#050505] hover:border-[#2a2a2a] transition-colors flex items-center justify-between gap-2"
      >
        <div className="min-w-0 text-left">
          <p className="font-mono text-[9px] uppercase tracking-widest text-white">CLIENTE ACTIVO</p>
          <p className="text-xs font-medium text-white truncate mt-0.5">
            {activeTenant?.name ?? "— Todos —"}
          </p>
        </div>
        <ChevronDown className={`w-3 h-3 text-white flex-shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 border border-[#2a2a2a] bg-[#0d0d0d] shadow-xl max-h-56 overflow-y-auto">
          {/* Opción "todos" solo para superadmin */}
          <button
            onClick={() => { setActiveTenant(null); setOpen(false); }}
            className={`w-full text-left px-3 py-2.5 border-b border-[#111] transition-colors hover:bg-[#050505] ${
              activeTenant === null ? "text-[#00e5a0]" : "text-white"
            }`}
          >
            <p className="font-mono text-[10px] uppercase tracking-widest">— Todos los clientes —</p>
          </button>
          {tenants.map((t: Tenant) => (
            <button
              key={t.id}
              onClick={() => { setActiveTenant(t); setOpen(false); }}
              className={`w-full text-left px-3 py-2.5 border-b border-[#111] transition-colors hover:bg-[#050505] ${
                activeTenant?.id === t.id ? "bg-[#00e5a0]/5" : ""
              }`}
            >
              <div className="flex items-center gap-2">
                <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${t.is_active ? "bg-[#00e5a0]" : "bg-[#333]"}`} />
                <div className="min-w-0">
                  <p className={`text-xs font-medium truncate ${activeTenant?.id === t.id ? "text-[#00e5a0]" : "text-white"}`}>
                    {t.name}
                  </p>
                  <p className="font-mono text-[9px] text-white truncate">{t.slug}</p>
                </div>
              </div>
            </button>
          ))}
          {tenants.length === 0 && (
            <p className="px-3 py-3 font-mono text-[10px] text-white text-center">Sin clientes</p>
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
    <div className="flex h-screen overflow-hidden bg-[#111]">

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
        flex flex-col w-72 lg:w-56 bg-[#0d0d0d] border-r border-[#2a2a2a] flex-shrink-0
        transition-transform duration-300
        ${sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
      `}>

        {/* Logo */}
        <div className="px-5 py-5 border-b border-[#2a2a2a]">
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold text-xs tracking-widest" style={{ color: "#00e5a0" }}>⬡</span>
            <span className="font-bold text-white text-sm tracking-tight">MIND</span>
            <span className="font-mono text-xs" style={{ color: "#ffffff" }}> / ADMIN</span>
          </div>
          <div className="mt-1 flex items-center gap-2">
            <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "#ffffff" }}>by Versat</span>
            {isSuperAdmin && (
              <span className="font-mono text-[9px] px-1.5 py-0.5 border border-[#00e5a0]/20 text-[#00e5a0] uppercase tracking-widest">
                SUPER
              </span>
            )}
          </div>
        </div>

        {/* Selector de tenant */}
        <div className="px-3 py-3 border-b border-[#1a1a1a]">
          <TenantSelector />
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2 py-4 space-y-0.5 overflow-y-auto">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `nav-link ${isActive ? "active text-[#00e5a0]" : ""}`
              }
            >
              <Icon className="w-3.5 h-3.5 flex-shrink-0" />
              {label}
            </NavLink>
          ))}

          {isSuperAdmin && (
            <div className="pt-3 mt-3 border-t border-[#1a1a1a]">
              <p className="px-3.5 pb-2 font-mono text-[9px] uppercase tracking-[0.2em] text-[#3a3a3a]">
                Sistema
              </p>
              <NavLink
                to="/superadmins"
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  `nav-link ${isActive ? "active text-[#00e5a0]" : ""}`
                }
              >
                <ShieldCheck className="w-3.5 h-3.5 flex-shrink-0" />
                Super Admins
              </NavLink>
            </div>
          )}
        </nav>

        {/* User */}
        <div className="px-4 py-4 border-t border-[#2a2a2a]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 border border-[#00e5a0]/50 flex items-center justify-center">
                <span className="font-mono text-[10px] text-[#00e5a0]">
                  {username?.[0]?.toUpperCase()}
                </span>
              </div>
              <span className="font-mono text-[11px] text-white">{username}</span>
            </div>
            <button
              onClick={async () => { await logout(); navigate("/login"); }}
              className="text-white hover:text-red-500 transition-colors"
              title="Salir"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto bg-[#111] min-w-0">
        {/* Hamburger */}
        <button
          onClick={() => setSidebarOpen((v) => !v)}
          className="lg:hidden fixed top-4 left-4 z-30 w-9 h-9 flex items-center justify-center border border-[#2a2a2a] bg-[#0d0d0d] hover:bg-[#1a1a1a]"
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
