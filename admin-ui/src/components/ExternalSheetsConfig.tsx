import { useState } from "react";
import { Check, FileSpreadsheet, X, Loader2, ScanSearch } from "lucide-react";
import { externalSheetsApi } from "../lib/api";
import type { ExternalSheetsPayload } from "../lib/api";

type Status =
  | "idle"
  | "testing"
  | "tested"
  | "error"
  | "discovering"
  | "discovered";

function ExternalSheetsConfig({
  value,
  onChange,
  tenantId,
}: {
  value: ExternalSheetsPayload | null;
  onChange: (v: ExternalSheetsPayload | null) => void;
  tenantId?: number;
}) {
  const [local, setLocal] = useState<ExternalSheetsPayload>(
    value ?? {
      spreadsheet_url: "",
      credentials: undefined,
    }
  );
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [schemaPreview, setSchemaPreview] = useState(value?.schema_description ?? "");

  const isEdit = tenantId !== undefined;

  const setField = (k: keyof ExternalSheetsPayload, v: string | Record<string, unknown> | undefined) => {
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
      const res = await externalSheetsApi.testConnection(tenantId, {
        spreadsheet_url: local.spreadsheet_url,
        credentials: local.credentials,
      });
      if (res.ok) {
        setStatus("tested");
      } else {
        setStatus("error");
        setErrorMessage(res.error ?? "No se pudo conectar a Google Sheets.");
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
      const res = await externalSheetsApi.discoverSheets(tenantId, {
        spreadsheet_url: local.spreadsheet_url,
        credentials: local.credentials,
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
        setErrorMessage("No se pudieron detectar hojas con datos. Verifica el acceso.");
      }
    } catch (e: unknown) {
      setStatus("error");
      setErrorMessage(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (e as Error)?.message ??
          "Error al detectar las hojas."
      );
    }
  };

  const handleCredentialsText = (text: string) => {
    if (!text.trim()) {
      setField("credentials", undefined);
      return;
    }
    try {
      const parsed = JSON.parse(text);
      setField("credentials", parsed);
    } catch {
      // no actualizar si el JSON no es válido
    }
  };

  const getCredentialsText = (): string => {
    if (local.credentials) {
      return JSON.stringify(local.credentials, null, 2);
    }
    return "";
  };

  return (
    <div className="border border-[#1a1a1a]">
      <div className="px-4 py-2.5 border-b border-[#1a1a1a] bg-[#050505] flex items-center gap-2">
        <FileSpreadsheet className="w-3 h-3 text-[#00e5a0]" />
        <span className="section-tag">// GOOGLE SHEETS</span>
      </div>

      <div className="p-4 grid grid-cols-1 gap-4">
        {/* URL del spreadsheet */}
        <div>
          <label className="label">
            URL del spreadsheet            {value && <span className="text-white ml-2">(vacío desconfigura)</span>}
          </label>
          <input
            className="input font-mono text-xs"
            placeholder="https://docs.google.com/spreadsheets/d/ABC123/edit"
            value={local.spreadsheet_url}
            onChange={(e) => setField("spreadsheet_url", e.target.value)}
          />
          <p className="font-mono text-[10px] text-white mt-1.5">
            Comparte la hoja con el client_email de la service account
          </p>
        </div>

        {/* Credenciales JSON */}
        <div>
          <label className="label">
            Credenciales (Service Account JSON)
            {value && <span className="text-white ml-2">(vacío conserva la guardada)</span>}
          </label>
          <textarea
            className="input font-mono text-xs min-h-[120px] resize-y"
            placeholder='{"type": "service_account", "project_id": "...", ...}'
            value={getCredentialsText()}
            onChange={(e) => handleCredentialsText(e.target.value)}
            spellCheck={false}
          />
          <p className="font-mono text-[10px] text-white mt-1.5">
            Google Cloud → Service Accounts → Add Key → JSON. Pega el contenido completo.
          </p>
        </div>

        {/* En creación la conexión se valida al guardar; en edición hay acciones */}
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
                DETECTAR HOJAS
              </button>

              {status === "tested" && (
                <span className="flex items-center gap-1.5 font-mono text-[11px] text-[#00e5a0]">
                  <Check className="w-3.5 h-3.5" /> Conexión exitosa
                </span>
              )}
              {status === "discovered" && (
                <span className="flex items-center gap-1.5 font-mono text-[11px] text-[#00e5a0]">
                  <Check className="w-3.5 h-3.5" /> Hojas detectadas — se guardará con el cliente
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
                <pre className="font-mono text-xs text-white p-3 border border-[#1a1a1a] bg-[#050505] max-h-60 overflow-y-auto whitespace-pre-wrap">
                  {schemaPreview}
                </pre>
              </div>
            )}
          </>
        ) : (
          <p className="font-mono text-[10px] text-white leading-relaxed">
            La conexión se probará automáticamente al guardar el cliente. Las hojas se
            detectan después: edita el cliente y usa «Detectar hojas».
          </p>
        )}
      </div>
    </div>
  );
}

export default ExternalSheetsConfig;