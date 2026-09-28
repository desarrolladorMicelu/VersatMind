import { useState } from "react";
import { Check, FileText, X, Loader2, ScanSearch } from "lucide-react";
import { alegraApi } from "../lib/api";
import type { AlegraPayload } from "../lib/api";

type Status = "idle" | "testing" | "tested" | "error" | "discovering" | "discovered";

function AlegraConfig({
  value,
  onChange,
  tenantId,
}: {
  value: AlegraPayload | null;
  onChange: (v: AlegraPayload | null) => void;
  tenantId?: number;
}) {
  const [local, setLocal] = useState<AlegraPayload>(
    value ?? { email: "", token: "" }
  );
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [schemaPreview, setSchemaPreview] = useState(value?.schema_description ?? "");

  const isEdit = tenantId !== undefined;

  const setField = (k: keyof AlegraPayload, v: string | string[] | undefined) => {
    const next = { ...local, [k]: v };
    setLocal(next);
    onChange(next);
    setStatus("idle");
  };

  const handleTest = async () => {
    if (!tenantId) return;
    setStatus("testing");
    setErrorMessage("");
    try {
      const res = await alegraApi.testConnection(tenantId, {
        email: local.email,
        token: local.token,
        groups: local.groups,
      });
      if (res.ok) {
        setStatus("tested");
      } else {
        setStatus("error");
        setErrorMessage(res.error ?? "No se pudo conectar a Alegra.");
      }
    } catch (e: unknown) {
      setStatus("error");
      setErrorMessage(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (e as Error)?.message ??
          "Error de conexión."
      );
    }
  };

  const handleDiscover = async () => {
    if (!tenantId) return;
    setStatus("discovering");
    setErrorMessage("");
    setSchemaPreview("");
    try {
      const res = await alegraApi.discoverTools(tenantId, {
        email: local.email,
        token: local.token,
        groups: local.groups,
      });
      if (res.schema_description) {
        setSchemaPreview(res.schema_description);
        const next = { ...local, schema_description: res.schema_description };
        setLocal(next);
        onChange(next);
        setStatus("discovered");
      } else if (res.error) {
        setStatus("error");
        setErrorMessage(res.error);
      } else {
        setStatus("error");
        setErrorMessage("No se pudieron detectar herramientas en Alegra.");
      }
    } catch (e: unknown) {
      setStatus("error");
      setErrorMessage(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (e as Error)?.message ??
          "Error al detectar herramientas."
      );
    }
  };

  return (
    <div className="border border-[#1a1a1a]">
      <div className="px-4 py-2.5 border-b border-[#1a1a1a] bg-[#050505] flex items-center gap-2">
        <FileText className="w-3 h-3 text-[#00e5a0]" />
        <span className="section-tag">// ALEGRA (CONTABILIDAD)</span>
      </div>

      <div className="p-4 grid grid-cols-1 gap-4">
        {/* Email */}
        <div>
          <label className="label">
            Email de Alegra
            {value && <span className="text-[#333] ml-2">(vacío conserva el guardado)</span>}
          </label>
          <input
            className="input font-mono text-xs"
            placeholder="tu@email.com"
            value={local.email}
            onChange={(e) => setField("email", e.target.value)}
          />
        </div>

        {/* Token */}
        <div>
          <label className="label">
            Token de API
            {value && <span className="text-[#333] ml-2">(vacío conserva el guardado)</span>}
          </label>
          <input
            className="input font-mono text-xs"
            type="password"
            placeholder="Token de Alegra"
            value={local.token}
            onChange={(e) => setField("token", e.target.value)}
          />
          <p className="font-mono text-[10px] text-[#333] mt-1.5">
            Obtenlo en Alegra → Configuración → API
          </p>
        </div>

        {isEdit ? (
          <>
            <div className="flex items-center gap-3">
              <button
                type="button"
                className="btn-secondary"
                disabled={status === "testing"}
                onClick={handleTest}
              >
                {status === "testing" && <Loader2 className="w-3 h-3 animate-spin" />}
                PROBAR CONEXIÓN
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={status === "discovering"}
                onClick={handleDiscover}
              >
                {status === "discovering" && <Loader2 className="w-3 h-3 animate-spin" />}
                <ScanSearch className="w-3 h-3" />
                DESCUBRIR TOOLS
              </button>

              {status === "tested" && (
                <span className="flex items-center gap-1.5 font-mono text-[11px] text-[#00e5a0]">
                  <Check className="w-3.5 h-3.5" /> Conexión exitosa
                </span>
              )}
              {status === "discovered" && (
                <span className="flex items-center gap-1.5 font-mono text-[11px] text-[#00e5a0]">
                  <Check className="w-3.5 h-3.5" /> Tools detectadas
                </span>
              )}
              {status === "error" && errorMessage && (
                <span className="flex items-center gap-1.5 font-mono text-[11px] text-red-400 break-all">
                  <X className="w-3.5 h-3.5 flex-shrink-0" /> {errorMessage}
                </span>
              )}
            </div>

            {schemaPreview && (
              <div>
                <label className="label">Descripción detectada (vista previa)</label>
                <pre className="font-mono text-xs text-[#888] p-3 border border-[#1a1a1a] bg-[#050505] max-h-60 overflow-y-auto whitespace-pre-wrap">
                  {schemaPreview}
                </pre>
              </div>
            )}
          </>
        ) : (
          <p className="font-mono text-[10px] text-[#333] leading-relaxed">
            La conexión se probará automáticamente al guardar el cliente. Las tools se
            detectan después: edita el cliente y usa «Descubrir tools».
          </p>
        )}
      </div>
    </div>
  );
}

export default AlegraConfig;