import { useState } from "react";
import { Check, Database, Eye, EyeOff, X, Loader2, ScanSearch } from "lucide-react";
import { externalDbApi } from "../lib/api";
import type { ExternalDbPayload } from "../lib/api";

type Status =
  | "idle"
  | "testing"
  | "tested"
  | "error"
  | "discovering"
  | "discovered";

function ExternalDbConfig({
  value,
  onChange,
  tenantId,
}: {
  value: ExternalDbPayload | null;
  onChange: (v: ExternalDbPayload | null) => void;
  tenantId?: number;
}) {
  const [local, setLocal] = useState<ExternalDbPayload>(
    value ?? {
      engine: "postgresql",
      host: "",
      port: 5432,
      database: "",
      user: "",
      password: "",
    }
  );
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [schemaPreview, setSchemaPreview] = useState(value?.schema_description ?? "");
  const [showPass, setShowPass] = useState(false);

  const isEdit = tenantId !== undefined;

  const setField = (k: keyof ExternalDbPayload, v: string | number) => {
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
      const res = await externalDbApi.testConnection(tenantId, local);
      if (res.ok) {
        setStatus("tested");
      } else {
        setStatus("error");
        setErrorMessage(res.error ?? "No se pudo conectar a la base de datos externa.");
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
      const res = await externalDbApi.discoverSchema(tenantId, local);
      if (res.schema_description) {
        setSchemaPreview(res.schema_description);
        const next = { ...local, schema_description: res.schema_description };
        setLocal(next);
        onChange(next);
        setStatus("discovered");
      } else {
        setStatus("error");
        setErrorMessage(res.error ?? "No se pudo detectar el esquema de la base de datos.");
      }
    } catch (e: unknown) {
      setStatus("error");
      setErrorMessage(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (e as Error)?.message ??
          "Error al detectar el esquema."
      );
    }
  };

  return (
    <div className="border border-[#1a1a1a]">
      <div className="px-4 py-2.5 border-b border-[#1a1a1a] bg-[#050505] flex items-center gap-2">
        <Database className="w-3 h-3 text-[#00e5a0]" />
        <span className="section-tag">// BASE DE DATOS EXTERNA</span>
      </div>

      <div className="p-4 grid grid-cols-2 gap-4">
        {/* Engine */}
        <div>
          <label className="label">Motor</label>
          <select
            className="input font-mono text-xs"
            value={local.engine}
            onChange={(e) => setField("engine", e.target.value)}
          >
            <option value="postgresql">PostgreSQL</option>
          </select>
          <p className="font-mono text-[10px] text-white mt-1.5">
            Solo lectura — se ejecutan sentencias SELECT
          </p>
        </div>

        {/* Puerto */}
        <div>
          <label className="label">Puerto</label>
          <input
            className="input font-mono text-xs"
            type="number"
            value={local.port || ""}
            placeholder="5432"
            onChange={(e) => setField("port", parseInt(e.target.value) || 5432)}
          />
        </div>

        <div>
          <label className="label">Host / IP</label>
          <input
            className="input font-mono text-xs"
            placeholder="db.cliente.com"
            value={local.host}
            onChange={(e) => setField("host", e.target.value)}
          />
        </div>

        <div>
          <label className="label">Base de datos</label>
          <input
            className="input font-mono text-xs"
            placeholder="nombre_bd"
            value={local.database}
            onChange={(e) => setField("database", e.target.value)}
          />
        </div>

        <div>
          <label className="label">Usuario</label>
          <input
            className="input font-mono text-xs"
            placeholder="db_read"
            value={local.user}
            onChange={(e) => setField("user", e.target.value)}
          />
        </div>

        <div>
          <label className="label">
            Contraseña
            {value && <span className="text-white ml-2">(vacío conserva la guardada)</span>}
          </label>
          <div className="relative">
            <input
              className="input pr-10 font-mono text-xs"
              placeholder="••••••••"
              type={showPass ? "text" : "password"}
              value={local.password}
              onChange={(e) => setField("password", e.target.value)}
            />
            <button
              type="button"
              onClick={() => setShowPass((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-white hover:text-white transition-colors"
            >
              {showPass ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* En creación la conexión se valida al guardar; en edición hay acciones */}
        {isEdit ? (
          <>
            <div className="col-span-2 flex items-center gap-3">
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
                DETECTAR ESQUEMA
              </button>

              {status === "tested" && (
                <span className="flex items-center gap-1.5 font-mono text-[11px] text-[#00e5a0]">
                  <Check className="w-3.5 h-3.5" /> Conexión exitosa
                </span>
              )}
              {status === "discovered" && (
                <span className="flex items-center gap-1.5 font-mono text-[11px] text-[#00e5a0]">
                  <Check className="w-3.5 h-3.5" /> Esquema detectado — se guardará con el cliente
                </span>
              )}
              {status === "error" && errorMessage && (
                <span className="flex items-center gap-1.5 font-mono text-[11px] text-red-400 break-all">
                  <X className="w-3.5 h-3.5 flex-shrink-0" /> {errorMessage}
                </span>
              )}
            </div>

            {schemaPreview && (
              <div className="col-span-2">
                <label className="label">Esquema detectado (vista previa)</label>
                <pre className="font-mono text-xs text-white p-3 border border-[#1a1a1a] bg-[#050505] max-h-60 overflow-y-auto">
                  {schemaPreview}
                </pre>
              </div>
            )}
          </>
        ) : (
          <p className="col-span-2 font-mono text-[10px] text-white leading-relaxed">
            La conexión se probará automáticamente al guardar el cliente. El esquema se
            detecta después: edita el cliente y usa «Detectar esquema».
          </p>
        )}
      </div>
    </div>
  );
}

export default ExternalDbConfig;