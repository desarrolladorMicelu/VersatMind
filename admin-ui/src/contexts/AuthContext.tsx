import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import api from "../lib/api";

interface AuthState {
  username: string | null;
  loading: boolean;
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ username: null, loading: true });

  useEffect(() => {
    api.get("/me")
      .then((r) => setState({ username: r.data.username, loading: false }))
      .catch(() => setState({ username: null, loading: false }));
  }, []);

  const login = async (username: string, password: string) => {
    const r = await api.post("/login", { username, password });
    setState({ username: r.data.username, loading: false });
  };

  const logout = async () => {
    await api.post("/logout");
    setState({ username: null, loading: false });
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
