import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import api, { tenantsApi } from "../lib/api";
import { useTenant } from "./TenantContext";

interface AuthState {
  username: string | null;
  loading: boolean;
  role: "superadmin" | "tenant_admin" | null;
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ username: null, loading: true, role: null });
  const { setTenants, setActiveTenant, setIsSuperAdmin, setJwtTenantId } = useTenant();

  const _loadTenants = async (role: string, jwtTenantId: number | null) => {
    if (role === "superadmin") {
      setIsSuperAdmin(true);
      setJwtTenantId(null);
      try {
        const list = await tenantsApi.list();
        setTenants(list);
        if (list.length > 0) setActiveTenant(list[0]);
      } catch {
        setTenants([]);
      }
    } else {
      setIsSuperAdmin(false);
      setJwtTenantId(jwtTenantId);
      if (jwtTenantId) {
        setActiveTenant({ id: jwtTenantId } as any);
      }
    }
  };

  useEffect(() => {
    api.get("/me")
      .then((r) => {
        const { username, role, tenant_id } = r.data;
        setState({ username, loading: false, role: role ?? "superadmin" });
        _loadTenants(role ?? "superadmin", tenant_id ?? null);
      })
      .catch(() => setState({ username: null, loading: false, role: null }));
  }, []);

  const login = async (username: string, password: string) => {
    const r = await api.post("/login", { username, password });
    const { username: uname, role, tenant_id } = r.data;
    setState({ username: uname, loading: false, role: role ?? "superadmin" });
    await _loadTenants(role ?? "superadmin", tenant_id ?? null);
  };

  const logout = async () => {
    await api.post("/logout");
    setState({ username: null, loading: false, role: null });
    setTenants([]);
    setActiveTenant(null);
    setIsSuperAdmin(true);
    setJwtTenantId(null);
  };

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
