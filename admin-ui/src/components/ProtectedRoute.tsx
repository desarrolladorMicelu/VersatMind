import { Navigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { username, loading } = useAuth();
  if (loading) return (
    <div className="flex h-screen items-center justify-center bg-[var(--color-bg)]">
      <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
    </div>
  );
  if (!username) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
