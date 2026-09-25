import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useTenant } from "../contexts/TenantContext";
import {
  LayoutDashboard, Bot, Users, KeyRound,
  Shield, Clock, MessageSquare, Activity, LogOut,
  Building2, ChevronDown,
} from "lucide-react";
import { useState, useRef, useEffect } from "react";
import type { Tenant } from "../lib/api";

const NAV_SUPERADMIN = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/tenants", icon: Building2, label: "Clientes" },
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
        <p className="font-mono text-[9px] uppercase tracking-widest text-[#444] mb-1">CLIENTE</p>
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
          <p className="font-mono text-[9px] uppercase tracking-widest text-[#444]">CLIENTE ACTIVO</p>
          <p className="text-xs font-medium text-white truncate mt-0.5">
            {activeTenant?.name ?? "— Todos —"}
          </p>
        </div>
        <ChevronDown className={`w-3 h-3 text-[#444] flex-shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 border border-[#2a2a2a] bg-[#0d0d0d] shadow-xl max-h-56 overflow-y-auto">
          {/* Opción "todos" solo para superadmin */}
          <button
            onClick={() => { setActiveTenant(null); setOpen(false); }}
            className={`w-full text-left px-3 py-2.5 border-b border-[#111] transition-colors hover:bg-[#050505] ${
              activeTenant === null ? "text-[#00e5a0]" : "text-[#555]"
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
                  <p className="font-mono text-[9px] text-[#333] truncate">{t.slug}</p>
                </div>
              </div>
            </button>
          ))}
          {tenants.length === 0 && (
            <p className="px-3 py-3 font-mono text-[10px] text-[#333] text-center">Sin clientes</p>
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

  return (
    <div className="flex h-screen overflow-hidden bg-[#111]">

      {/* Sidebar */}
      <aside className="flex flex-col w-56 bg-[#0d0d0d] border-r border-[#2a2a2a] flex-shrink-0">

        {/* Logo */}
        <div className="px-5 py-5 border-b border-[#2a2a2a]">
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold text-xs tracking-widest" style={{ color: "#00e5a0" }}>⬡</span>
            <span className="font-bold text-white text-sm tracking-tight">MIND</span>
            <span className="font-mono text-xs" style={{ color: "#444" }}> / ADMIN</span>
          </div>
          <div className="mt-1 flex items-center gap-2">
            <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "#444" }}>by Versat</span>
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
              className={({ isActive }) =>
                `nav-link ${isActive ? "active text-[#00e5a0]" : ""}`
              }
            >
              <Icon className="w-3.5 h-3.5 flex-shrink-0" />
              {label}
            </NavLink>
          ))}
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
              <span className="font-mono text-[11px] text-[#888]">{username}</span>
            </div>
            <button
              onClick={async () => { await logout(); navigate("/login"); }}
              className="text-[#333] hover:text-red-500 transition-colors"
              title="Salir"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto bg-[#111]">
        <Outlet />
      </main>

    </div>
  );
}
