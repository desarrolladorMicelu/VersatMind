import { useState, useEffect } from "react";
import { Check, FileSpreadsheet, X, Loader2, ScanSearch, ExternalLink } from "lucide-react";
import { externalExcelApi } from "../lib/api";
import type { ExternalExcelPayload } from "../lib/api";

type Status =
  | "idle"
  | "testing"
  | "tested"
  | "error"
  | "discovering"
  | "discovered";

function ExternalExcelConfig({
  value,
  onChange,
  tenantId,
}: {
  value: ExternalExcelPayload | null;
  onChange: (v: ExternalExcelPayload | null) => void;
  tenantId?: number;
}) {
  const configured = value !== null && value !== undefined;
  const [local, setLocal] = useState<ExternalExcelPayload>(
    value ?? {}
  );
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [connected, setConnected] = useState(configured);
  const [urlInput, setUrlInput] = useState("");
  const [urlStatus, setUrlStatus] = useState<"idle" | "busy" | "error">("idle");
  const [urlError, setUrlError] = useState("");
  const [schemaPreview, setSchemaPreview] = useState(value?.schema_description ?? "");

  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data?.type === "excel_connected") {
        setConnected(true);
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  const isEdit = tenantId !== undefined;

  const handleConnect = async () => {
    if (!tenantId) return;
    setErrorMessage("");
    try {
      const res = await externalExcelApi.getAuthUrl(tenantId);
      window.open(res.url, "_blank", "resizable,scrollbars");
    } catch (e: unknown) {
      setErrorMessage(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (e as Error)?.message ??
          "Error al obtener la URL de conexión."
      );
    }
  };

  const handleResolveUrl = async () => {
    if (!tenantId || !urlInput.trim()) return;
    setUrlStatus("busy");
    setUrlError("");
    try {
      const res = await externalExcelApi.resolveFile(tenantId, { file_url: urlInput.trim() });
      if (res.ok && res.file) {
        const next: ExternalExcelPayload = {
          ...local,
          file_id: res.file.id,
          file_name: res.file.name,
          file_url: res.file.webUrl || urlInput.trim(),
          schema_description: undefined,
        };
        setLocal(next);
        onChange(next);
        setUrlInput("");
        setStatus("idle");
        setSchemaPreview("");
      } else {
        setUrlStatus("error");
        setUrlError(res.error ?? "No se pudo resolver el archivo.");
      }
    } catch (e: unknown) {
      setUrlStatus("error");
      setUrlError(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (e as Error)?.message ??
          "Error al resolver el archivo."
      );
    }
  };

  const handleTest = async () => {
    if (!tenantId) return;
    setStatus("testing");
    setErrorMessage("");
    try {
      const res = await externalExcelApi.testConnection(tenantId, {
        file_id: local.file_id,
        file_name: local.file_name,
        file_url: local.file_url,
      });
      if (res.ok) {
        setStatus("tested");
      } else {
        setStatus("error");
        setErrorMessage(res.error ?? "No se pudo conectar a OneDrive.");
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
      const res = await externalExcelApi.discoverSheets(tenantId, {
        file_id: local.file_id,
        file_name: local.file_name,
        file_url: local.file_url,
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

  const handleClearFile = () => {
    const next = { ...local, file_id: undefined, file_name: undefined, file_url: undefined, schema_description: undefined };
    setLocal(next);
    setSchemaPreview("");
    setStatus("idle");
  };

  return (
    <div className="border border-[#1a1a1a]">
      <div className="px-4 py-2.5 border-b border-[#1a1a1a] bg-[#050505] flex items-center gap-2">
        <FileSpreadsheet className="w-3 h-3 text-[#00e5a0]" />
        <span className="section-tag">// EXCEL (OneDrive/SharePoint)</span>
      </div>

      <div className="p-4 grid grid-cols-1 gap-4">
        {/* Estado de conexión */}
        <div>
          <label className="label">Conexión a OneDrive</label>
          {connected ? (
            <p className="flex items-center gap-2 font-mono text-[11px] text-[#00e5a0]">
              <Check className="w-3.5 h-3.5" />
              OneDrive conectado
            </p>
          ) : (
            <p className="font-mono text-[10px] text-[#555] mt-1.5">
              Conectá OneDrive para poder leer el archivo Excel del cliente.
            </p>
          )}

          {isEdit && !connected && (
            <button
              type="button"
              className="btn-secondary mt-2"
              onClick={handleConnect}
            >
              <ExternalLink className="w-3 h-3" />
              CONECTAR ONEDRIVE
            </button>
          )}
          {isEdit && connected && !local.file_id && (
            <button
              type="button"
              className="btn-secondary mt-2"
              onClick={handleConnect}
            >
              <ExternalLink className="w-3 h-3" />
              RECONECTAR
            </button>
          )}
        </div>

        {/* Ingresar link del archivo */}
        {connected && isEdit && !local.file_id && (
          <div>
            <label className="label">Link del archivo Excel</label>
            <div className="flex items-center gap-2">
              <input
                className="input font-mono text-xs"
                placeholder="Pegá el link del archivo Excel en OneDrive/SharePoint"
                value={urlInput}
                onChange={(e) => {
                  setUrlInput(e.target.value);
                  setUrlStatus("idle");
                  setUrlError("");
                }}
                onKeyDown={(e) => e.key === "Enter" && handleResolveUrl()}
              />
              <button
                type="button"
                className="btn-secondary"
                disabled={urlStatus === "busy" || !urlInput.trim()}
                onClick={handleResolveUrl}
              >
                {urlStatus === "busy" ? <Loader2 className="w-3 h-3 animate-spin" /> : <ScanSearch className="w-3 h-3" />}
                AGREGAR
              </button>
            </div>
            <p className="font-mono text-[10px] text-[#555] mt-1.5">
              Ej: https://excel.cloud.microsoft/open/onedrive/?docId=... o un link de
              onedrive.live.com / SharePoint
            </p>
            {urlStatus === "error" && urlError && (
              <p className="font-mono text-[10px] text-red-400 mt-1.5 break-all">{urlError}</p>
            )}
          </div>
        )}

        {/* Archivo seleccionado */}
        {local.file_id && (
          <div>
            <label className="label">Archivo seleccionado</label>
            <p className="flex items-center gap-2 font-mono text-[11px] text-[#00e5a0]">
              <Check className="w-3.5 h-3.5" />
              {local.file_name || "Archivo Excel"}
            </p>
          </div>
        )}

        {/* Acciones de edición */}
        {isEdit && local.file_id ? (
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
              <button
                type="button"
                className="btn-secondary"
                onClick={handleClearFile}
              >
                CAMBIAR ARCHIVO
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

            {schemaPreview ? (
              <div>
                <label className="label">Descripción detectada — editable (se guarda con el cliente)</label>
                <textarea
                  className="font-mono text-xs text-white p-3 border border-[#1a1a1a] bg-[#050505] min-h-[160px] resize-y w-full"
                  value={schemaPreview}
                  onChange={(e) => {
                    setSchemaPreview(e.target.value);
                    const next = { ...local, schema_description: e.target.value };
                    setLocal(next);
                    onChange(next);
                  }}
                />
                <p className="font-mono text-[10px] text-white mt-1.5">
                  Podés corregir lo que la IA detectó antes de guardar el cliente.
                </p>
              </div>
            ) : null}
          </>
        ) : null}

        {!isEdit && (
          <p className="font-mono text-[10px] text-white leading-relaxed">
            Después de crear el cliente, editalo para conectar OneDrive y pegar
            el link del archivo Excel que se leerá.
          </p>
        )}
      </div>
    </div>
  );
}

export default ExternalExcelConfig;