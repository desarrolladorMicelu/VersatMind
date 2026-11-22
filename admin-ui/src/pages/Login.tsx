import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";
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
            "linear-gradient(to right, rgba(38,35,29,0.045) 1px, transparent 1px), linear-gradient(to bottom, rgba(38,35,29,0.045) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse at 50% 40%, black 20%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(ellipse at 50% 40%, black 20%, transparent 75%)",
        }}
      />

      <div className="relative grid w-full max-w-4xl overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-surface)] shadow-[0_28px_70px_-30px_rgba(38,35,29,0.28)] lg:grid-cols-2">

        {/* Panel de marca */}
        <div className="relative hidden flex-col justify-between gap-14 border-r border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] p-10 lg:flex">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-accent/25 bg-accent/10">
              <span className="text-sm font-bold text-accent">M</span>
            </div>
            <div>
              <p className="text-sm font-semibold tracking-tight text-[var(--color-text)]">Mind</p>
              <p className="text-2xs font-medium text-[var(--color-text-subtle)]">by Versat</p>
            </div>
          </div>

          <div>
            <p className="section-tag mb-3">Panel de administración</p>
            <h1 className="text-3xl font-semibold leading-[1.15] tracking-tight text-[var(--color-text)]">
              Inteligencia clara para decisiones importantes.
            </h1>
            <p className="mt-4 max-w-sm text-sm leading-relaxed text-[var(--color-text-muted)]">
              Administra clientes, usuarios, integraciones y consumo desde un solo
              lugar, con la tranquilidad de tener todo bajo control.
            </p>

            <div className="mt-8 space-y-3">
              {[
                "Acceso multi-cliente con aislamiento total",
                "Control de usuarios, roles y permisos",
                "Consumo, integraciones y auditoría en tiempo real",
              ].map((item) => (
                <div key={item} className="flex items-start gap-2.5">
                  <ShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-accent" />
                  <p className="text-xs leading-relaxed text-[var(--color-text-muted)]">{item}</p>
                </div>
              ))}
            </div>
          </div>

          <p className="text-2xs font-medium text-[var(--color-text-subtle)]">
            Acceso restringido · Solo personal autorizado
          </p>
        </div>

        {/* Formulario */}
        <div className="flex flex-col justify-center p-8 sm:p-10">
          <div className="mb-8 lg:hidden">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-accent/25 bg-accent/10">
                <span className="text-sm font-bold text-accent">M</span>
              </div>
              <div>
                <p className="text-sm font-semibold tracking-tight text-[var(--color-text)]">Mind</p>
                <p className="text-2xs font-medium text-[var(--color-text-subtle)]">by Versat</p>
              </div>
            </div>
          </div>

          <div className="mb-7">
            <h2 className="text-xl font-semibold tracking-tight text-[var(--color-text)]">Inicia sesión</h2>
            <p className="mt-1.5 text-sm text-[var(--color-text-muted)]">
              Ingresa tus credenciales para continuar.
            </p>
          </div>

          {error && (
            <div className="mb-5 flex items-start gap-2.5 rounded-lg border border-red-300 bg-red-50 px-3.5 py-3">
              <LockKeyhole className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-700" />
              <p className="text-xs font-medium text-red-700">{error}</p>
            </div>
          )}

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
                autoComplete="username"
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

          <p className="mt-6 text-center text-2xs leading-relaxed text-[var(--color-text-subtle)]">
            Mind by Versat · Panel de administración
          </p>
        </div>

      </div>
    </div>
  );
}
