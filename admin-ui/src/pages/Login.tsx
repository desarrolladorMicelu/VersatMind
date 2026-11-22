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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#0b0c0e] px-4 py-10">

      {/* Ambiente */}
      <div className="pointer-events-none absolute -top-40 left-[15%] h-[460px] w-[460px] rounded-full bg-[#34d399]/10 blur-[120px]" />
      <div className="pointer-events-none absolute -bottom-52 right-[10%] h-[420px] w-[420px] rounded-full bg-[#34d399]/5 blur-[120px]" />
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.035) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse at 50% 40%, black 20%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(ellipse at 50% 40%, black 20%, transparent 75%)",
        }}
      />

      <div className="relative grid w-full max-w-4xl overflow-hidden rounded-2xl border border-[#1f232a] bg-[#101216] shadow-[0_32px_90px_-30px_rgba(0,0,0,0.9)] lg:grid-cols-2">

        {/* Panel de marca */}
        <div className="relative hidden flex-col justify-between gap-14 border-r border-[#1f232a] bg-[#0d0f12] p-10 lg:flex">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#34d399]/25 bg-[#34d399]/10">
              <span className="text-sm font-bold text-[#34d399]">M</span>
            </div>
            <div>
              <p className="text-sm font-semibold tracking-tight text-white">Mind</p>
              <p className="text-2xs font-medium text-[#7d8592]">by Versat</p>
            </div>
          </div>

          <div>
            <p className="section-tag mb-3">Panel de administración</p>
            <h1 className="text-3xl font-semibold leading-[1.15] tracking-tight text-white">
              Inteligencia clara para decisiones importantes.
            </h1>
            <p className="mt-4 max-w-sm text-sm leading-relaxed text-[#a8b0bd]">
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
                  <ShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-[#34d399]" />
                  <p className="text-xs leading-relaxed text-[#a8b0bd]">{item}</p>
                </div>
              ))}
            </div>
          </div>

          <p className="text-2xs font-medium text-[#667085]">
            Acceso restringido · Solo personal autorizado
          </p>
        </div>

        {/* Formulario */}
        <div className="flex flex-col justify-center p-8 sm:p-10">
          <div className="mb-8 lg:hidden">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#34d399]/25 bg-[#34d399]/10">
                <span className="text-sm font-bold text-[#34d399]">M</span>
              </div>
              <div>
                <p className="text-sm font-semibold tracking-tight text-white">Mind</p>
                <p className="text-2xs font-medium text-[#7d8592]">by Versat</p>
              </div>
            </div>
          </div>

          <div className="mb-7">
            <h2 className="text-xl font-semibold tracking-tight text-white">Inicia sesión</h2>
            <p className="mt-1.5 text-sm text-[#a8b0bd]">
              Ingresa tus credenciales para continuar.
            </p>
          </div>

          {error && (
            <div className="mb-5 flex items-start gap-2.5 rounded-lg border border-red-500/25 bg-red-500/10 px-3.5 py-3">
              <LockKeyhole className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-400" />
              <p className="text-xs font-medium text-red-300">{error}</p>
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

          <p className="mt-6 text-center text-2xs leading-relaxed text-[#667085]">
            Mind by Versat · Panel de administración
          </p>
        </div>

      </div>
    </div>
  );
}
