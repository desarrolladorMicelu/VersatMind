import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import {
  LayoutDashboard, Bot, Users, KeyRound,
  Shield, Clock, MessageSquare, Activity, LogOut, Building2,
} from "lucide-react";

const NAV = [
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

export default function Layout() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="flex h-screen overflow-hidden bg-[#111]">

      {/* Sidebar */}
      <aside className="flex flex-col w-56 bg-[#0d0d0d] border-r border-[#2a2a2a] flex-shrink-0">

        {/* Logo */}
        <div className="px-5 py-5 border-b border-[#2a2a2a]">
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold text-xs tracking-widest" style={{color:'#00e5a0'}}>⬡</span>
            <span className="font-bold text-white text-sm tracking-tight">MIND</span>
            <span className="font-mono text-xs" style={{color:'#444'}}> / ADMIN</span>
          </div>
          <div className="mt-1">
            <span className="font-mono text-[10px] uppercase tracking-widest" style={{color:'#444'}}>by Versat</span>
          </div>
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
