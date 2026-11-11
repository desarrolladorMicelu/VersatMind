import { Navigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function SuperAdminRoute({ children }: { children: React.ReactNode }) {
  const { role, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#111]">
        <div className="w-6 h-6 border-2 border-[#00e5a0] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (role !== "superadmin") return <Navigate to="/" replace />;
  return <>{children}</>;
}
