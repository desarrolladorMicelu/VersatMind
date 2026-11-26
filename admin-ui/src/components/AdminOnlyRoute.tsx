import { Navigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useTenant } from "../contexts/TenantContext";

export default function AdminOnlyRoute({ children }: { children: React.ReactNode }) {
  const { role, loading } = useAuth();
  const { isPortalAdmin } = useTenant();
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--color-bg)]">
        <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (role !== "superadmin" && role !== "tenant_admin" && !isPortalAdmin) {
    return <Navigate to="/chat" replace />;
  }
  return <>{children}</>;
}
