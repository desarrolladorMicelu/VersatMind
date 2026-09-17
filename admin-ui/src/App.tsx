import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./contexts/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Tenants from "./pages/Tenants";
import Agente from "./pages/Agente";
import Usuarios from "./pages/Usuarios";
import Accesos from "./pages/Accesos";
import Roles from "./pages/Roles";
import Tareas from "./pages/Tareas";
import Historial from "./pages/Historial";
import Auditoria from "./pages/Auditoria";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30000 } },
});

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <BrowserRouter basename="/admin">
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="tenants" element={<Tenants />} />
              <Route path="agente" element={<Agente />} />
              <Route path="usuarios" element={<Usuarios />} />
              <Route path="accesos" element={<Accesos />} />
              <Route path="roles" element={<Roles />} />
              <Route path="tareas" element={<Tareas />} />
              <Route path="historial" element={<Historial />} />
              <Route path="auditoria" element={<Auditoria />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
