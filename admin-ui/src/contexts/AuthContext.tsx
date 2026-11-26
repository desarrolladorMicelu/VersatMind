import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import api, { tenantsApi } from "../lib/api";
import { useTenant } from "./TenantContext";

type Role = "superadmin" | "tenant_admin" | "portal_user" | null;

interface AuthState {
  username: string | null;
  loading: boolean;
  role: Role;
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<Role>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ username: null, loading: true, role: null });
  const {
    setTenants, setActiveTenant, setIsSuperAdmin, setJwtTenantId, setIsPortalUser,
  } = useTenant();

  const _loadTenants = async (role: Role, jwtTenantId: number | null, memberships: any[] = []) => {
    if (role === "portal_user") {
      setIsSuperAdmin(false);
      setIsPortalUser(true);
      setJwtTenantId(null);
      const list = (memberships ?? []).map((m) => ({
        id: m.tenant_id,
        name: m.tenant_name,
        slug: m.tenant_slug,
        role_id: m.role_id,
        role_name: m.role_name,
      }));
      setTenants(list as any);
      setActiveTenant((list[0] as any) ?? null);
      return;
    }

    setIsPortalUser(false);
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
      setTenants([]);
      if (jwtTenantId) {
        setActiveTenant({ id: jwtTenantId } as any);
      }
    }
  };

  useEffect(() => {
    api.get("/me")
      .then((r) => {
        const { username, role, tenant_id, memberships } = r.data;
        const nextRole: Role = role ?? "superadmin";
        setState({ username, loading: false, role: nextRole });
        _loadTenants(nextRole, tenant_id ?? null, memberships ?? []);
      })
      .catch(() => setState({ username: null, loading: false, role: null }));
  }, []);

  const login = async (username: string, password: string): Promise<Role> => {
    const r = await api.post("/login", { username, password });
    const { username: uname, role, tenant_id, memberships } = r.data;
    const nextRole: Role = role ?? "superadmin";
    setState({ username: uname, loading: false, role: nextRole });
    await _loadTenants(nextRole, tenant_id ?? null, memberships ?? []);
    return nextRole;
  };

  const logout = async () => {
    await api.post("/logout");
    setState({ username: null, loading: false, role: null });
    setTenants([]);
    setActiveTenant(null);
    setIsSuperAdmin(true);
    setIsPortalUser(false);
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
