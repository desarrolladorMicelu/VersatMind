import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      navigate("/");
    } catch {
      setError("Credenciales incorrectas");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center px-4">

      {/* Background grid lines (decorative) */}
      <div className="fixed inset-0 pointer-events-none"
        style={{
          backgroundImage: "linear-gradient(rgba(0,229,160,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,229,160,0.03) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />

      <div className="w-full max-w-sm relative">

        {/* Corner decorations */}
        <div className="absolute -top-px -left-px w-4 h-4 border-t border-l border-[#00e5a0]" />
        <div className="absolute -top-px -right-px w-4 h-4 border-t border-r border-[#00e5a0]" />
        <div className="absolute -bottom-px -left-px w-4 h-4 border-b border-l border-[#00e5a0]" />
        <div className="absolute -bottom-px -right-px w-4 h-4 border-b border-r border-[#00e5a0]" />

        <div className="bg-[#050505] border border-[#1a1a1a] p-8">

          {/* Header */}
          <div className="mb-8">
            <p className="font-mono text-[10px] text-[#00e5a0] uppercase tracking-widest mb-3">// MIND ADMIN</p>
            <h1 className="text-3xl font-bold text-white leading-none">Acceso</h1>
            <p className="text-sm text-white mt-1">Panel de administración — Versat</p>
          </div>

          {/* Error */}
          {error && (
            <div className="mb-5 border border-red-900/50 bg-red-900/10 px-4 py-2.5">
              <p className="font-mono text-xs text-red-500">{error}</p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="label">Usuario</label>
              <input
                type="text"
                className="input"
                placeholder="admin"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div>
              <label className="label">Contraseña</label>
              <input
                type="password"
                className="input"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full py-3 mt-2">
              {loading ? "Verificando..." : "ENTRAR →"}
            </button>
          </form>

        </div>
      </div>
    </div>
  );
}
