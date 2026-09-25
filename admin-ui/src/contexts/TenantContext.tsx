import {
  createContext, useContext, useState, useCallback,
  type ReactNode,
} from "react";
import type { Tenant } from "../lib/api";

interface TenantContextType {
  activeTenant: Tenant | null;
  setActiveTenant: (t: Tenant | null) => void;
  tenants: Tenant[];
  setTenants: (ts: Tenant[]) => void;
  // tenant_id efectivo para queries
  tenantId: number | null;
  isSuperAdmin: boolean;
  setIsSuperAdmin: (v: boolean) => void;
  jwtTenantId: number | null;
  setJwtTenantId: (id: number | null) => void;
}

const TenantContext = createContext<TenantContextType | null>(null);

export function TenantProvider({ children }: { children: ReactNode }) {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [activeTenant, _setActiveTenant] = useState<Tenant | null>(null);
  const [isSuperAdmin, setIsSuperAdmin] = useState(true);
  const [jwtTenantId, setJwtTenantId] = useState<number | null>(null);

  const setActiveTenant = useCallback((t: Tenant | null) => {
    _setActiveTenant(t);
    // Sin localStorage — el estado vive solo en memoria de sesión
  }, []);

  // tenant_admin: el tenant es el del JWT, no elegible
  // superadmin: el que elija en el selector
  const tenantId: number | null = isSuperAdmin
    ? activeTenant?.id ?? null
    : jwtTenantId;

  return (
    <TenantContext.Provider value={{
      activeTenant,
      setActiveTenant,
      tenants,
      setTenants,
      tenantId,
      isSuperAdmin,
      setIsSuperAdmin,
      jwtTenantId,
      setJwtTenantId,
    }}>
      {children}
    </TenantContext.Provider>
  );
}

export function useTenant() {
  const ctx = useContext(TenantContext);
  if (!ctx) throw new Error("useTenant must be inside TenantProvider");
  return ctx;
}
