import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Mail, Calendar, X, Loader2, RefreshCw, Trash2, ExternalLink } from "lucide-react";
import { integrationsApi } from "../lib/api";
import type { IntegrationProviderStatus } from "../lib/api";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

type Banner = { kind: "ok" | "error"; text: string } | null;

function bannerFromUrl(): Banner {
  const params = new URLSearchParams(window.location.search);
  const status = params.get("integration");
  if (!status) return null;
  const provider = params.get("provider") ?? "";
  const message = params.get("message") ?? "";
  if (status === "ok") {
    return { kind: "ok", text: `Cuenta ${provider} vinculada correctamente${message ? ` (${message})` : ""}.` };
  }
  return { kind: "error", text: message || `No se pudo vincular ${provider}.` };
}

function ProviderIcon({ provider }: { provider: string }) {
  return provider === "outlook"
    ? <Mail className="w-4 h-4 text-[#00e5a0]" />
    : <Calendar className="w-4 h-4 text-[#00e5a0]" />;
}

export default function Integraciones() {
  const qc = useQueryClient();
  const { tenantId, activeTenant } = useTenant();
  // Mensaje de retorno del callback OAuth (?integration=ok|error&provider=&message=)
  const [banner, setBanner] = useState<Banner>(() => bannerFromUrl());

  useEffect(() => {
    if (window.location.search.includes("integration=")) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  const { data: providers = [], isLoading } = useQuery({
    queryKey: ["integrations", tenantId],
    queryFn: () => integrationsApi.providers(tenantId as number),
    enabled: tenantId !== null,
  });

  const start = useMutation({
    mutationFn: (provider: string) => integrationsApi.start(tenantId as number, provider),
    onSuccess: (res) => { window.location.href = res.authorize_url; },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setBanner({ kind: "error", text: detail ?? "No se pudo iniciar la vinculación." });
    },
  });

  const test = useMutation({
    mutationFn: (id: number) => integrationsApi.test(tenantId as number, id),
    onSuccess: (res: { ok: boolean; error?: string }) =>
      setBanner(res.ok ? { kind: "ok", text: "Conexión verificada correctamente." } : { kind: "error", text: res.error ?? "La conexión falló." }),
  });

  const remove = useMutation({
    mutationFn: (id: number) => integrationsApi.remove(tenantId as number, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["integrations", tenantId] }),
  });

  if (!tenantId) {
    return (
      <div>
        <PageHeader tag="INTEGRACIONES" title="Correo y calendario" description="Selecciona un cliente" />
        <div className="px-8 py-16 text-center">
          <p className="font-mono text-xs text-white uppercase tracking-widest">Selecciona un cliente en el panel izquierdo</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        tag="INTEGRACIONES"
        title="Correo y calendario"
        description={`Vincula Outlook y/o Google para ${activeTenant?.name ?? "el cliente"}`}
      />
      <div className="px-8 py-8 space-y-6 max-w-3xl">

        {banner && (
          <div className={`px-4 py-3 border font-mono text-xs ${
            banner.kind === "ok"
              ? "border-[#00e5a0]/40 bg-[#00e5a0]/10 text-[#00e5a0]"
              : "border-red-900 bg-red-950/30 text-red-400"
          }`}>
            {banner.text}
          </div>
        )}

        <p className="font-mono text-[11px] text-white leading-relaxed">
          Al vincular una cuenta, el agente podrá leer correos, consultar la agenda y generar
          borradores de respuesta (no envía correos). Los tokens se guardan cifrados y se
          renuevan solos.
        </p>

        {isLoading ? (
          <div className="h-24 border border-[#111] animate-pulse" />
        ) : (
          <div className="space-y-4">
            {providers.map((p: IntegrationProviderStatus) => (
              <div key={p.provider} className="border border-[#1a1a1a] p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 border border-[#2a2a2a] flex items-center justify-center flex-shrink-0">
                      <ProviderIcon provider={p.provider} />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white">{p.label}</p>
                      {p.connected ? (
                        <p className="font-mono text-[11px] text-white truncate">
                          {p.account_email}
                          <span className="ml-2 text-[#00e5a0]">● {p.status}</span>
                        </p>
                      ) : (
                        <p className="font-mono text-[11px] text-white">Sin vincular</p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    {p.connected ? (
                      <>
                        <button
                          className="btn-secondary flex items-center gap-1.5"
                          disabled={test.isPending}
                          onClick={() => p.connection_id && test.mutate(p.connection_id)}
                        >
                          {test.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                          Probar
                        </button>
                        <button
                          className="btn-ghost flex items-center gap-1.5"
                          onClick={() => p.connection_id && window.confirm("¿Desconectar esta cuenta?") && remove.mutate(p.connection_id)}
                        >
                          <Trash2 className="w-3 h-3" /> Desconectar
                        </button>
                      </>
                    ) : p.configured ? (
                      <button
                        className="btn-primary flex items-center gap-1.5"
                        disabled={start.isPending}
                        onClick={() => start.mutate(p.provider)}
                      >
                        {start.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <ExternalLink className="w-3 h-3" />}
                        Conectar
                      </button>
                    ) : (
                      <span className="flex items-center gap-1.5 font-mono text-[10px] text-yellow-500">
                        <X className="w-3 h-3" /> Falta configurar credenciales
                      </span>
                    )}
                  </div>
                </div>

                {!p.configured && (
                  <p className="font-mono text-[10px] text-white mt-3 leading-relaxed">
                    El servidor no tiene las credenciales OAuth de este proveedor. Define
                    {" "}<span className="text-[#00e5a0]">{p.provider === "outlook" ? "MS_CLIENT_ID / MS_CLIENT_SECRET" : "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET"}</span>
                    {" "}y <span className="text-[#00e5a0]">INTEGRATIONS_BASE_URL</span> en el entorno.
                  </p>
                )}
                {p.connected && p.last_error && (
                  <p className="font-mono text-[10px] text-red-400 mt-3 break-all">último error: {p.last_error}</p>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="border border-[#1a1a1a] p-5">
          <p className="section-tag mb-3">// Permisos necesarios</p>
          <p className="font-mono text-[10px] text-white leading-relaxed">
            Asigna a los roles los permisos <span className="text-[#00e5a0]">READ_MAIL</span> y
            {" "}<span className="text-[#00e5a0]">READ_CALENDAR</span> en la sección Roles para que los
            usuarios puedan consultar correo y agenda.
          </p>
        </div>

      </div>
    </div>
  );
}
