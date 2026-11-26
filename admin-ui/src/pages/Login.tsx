import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, LockKeyhole } from "lucide-react";
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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[var(--color-bg)] px-4 py-10">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(32,33,36,0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(32,33,36,0.05) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse at 50% 40%, black 20%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(ellipse at 50% 40%, black 20%, transparent 75%)",
        }}
      />

      <div className="relative w-full max-w-md rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-8 shadow-[0_28px_70px_-30px_rgba(32,33,36,0.3)] sm:p-10">
        <div className="mb-8 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-accent)] bg-[var(--color-accent)]">
            <span className="text-sm font-bold text-[var(--color-accent-contrast)]">M</span>
          </div>
          <div>
            <p className="text-sm font-semibold tracking-tight text-[var(--color-text)]">Mind</p>
            <p className="text-[11px] font-medium text-[var(--color-text-subtle)]">by Versat</p>
          </div>
        </div>

        <h1 className="text-xl font-semibold tracking-tight text-[var(--color-text)]">
          Inicia sesión
        </h1>

        {error && (
          <div className="mt-5 flex items-start gap-2.5 rounded-lg border border-red-300 bg-red-50 px-3.5 py-3">
            <LockKeyhole className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-700" />
            <p className="text-[13px] font-medium text-red-700">{error}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-5">
          <div>
            <label className="label">Usuario</label>
            <input
              type="text"
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              autoComplete="username"
            />
          </div>
          <div>
            <label className="label">Contraseña</label>
            <input
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="btn-primary mt-2 w-full py-3"
          >
            {loading ? "Verificando..." : "Entrar"}
            {!loading && <ArrowRight className="h-4 w-4" />}
          </button>
        </form>
      </div>
    </div>
  );
}
