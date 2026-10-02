import { useState } from "react";
import { Eye, FileText, Upload } from "lucide-react";

interface ReportConfigData {
  company_name: string;
  sections: string[];
  company_logo?: string;
  additional_instructions?: string;
}

const ALL_SECTIONS = [
  { id: "balance", label: "Balance General" },
  { id: "income", label: "Estado de Resultados (Ingresos)" },
  { id: "expenses", label: "Estado de Resultados (Gastos)" },
  { id: "cash_flow", label: "Flujo de Caja" },
  { id: "taxes", label: "Resumen de Impuestos" },
  { id: "accounts_receivable", label: "Cuentas por Cobrar" },
  { id: "accounts_payable", label: "Cuentas por Pagar" },
  { id: "inventory", label: "Inventario" },
];

function ReportConfig({
  value,
  onChange,
  tenantId,
}: {
  value: ReportConfigData | null;
  onChange: (v: ReportConfigData | null) => void;
  tenantId?: number;
}) {
  const [local, setLocal] = useState<ReportConfigData>(
    value ?? { company_name: "", sections: ["balance", "income", "expenses"] }
  );
  const [logoPreview, setLogoPreview] = useState("");

  const emit = (next: ReportConfigData) => {
    setLocal(next);
    onChange(next.company_name ? next : null);
  };

  const setField = (k: keyof ReportConfigData, v: string | string[]) => {
    emit({ ...local, [k]: v });
  };

  const toggleSection = (id: string) => {
    const current = local.sections;
    const next = current.includes(id)
      ? current.filter((s: string) => s !== id)
      : [...current, id];
    emit({ ...local, sections: next });
  };

  const handleLogo = async (file: File | undefined) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const b64 = result.split(",")[1] ?? "";
      emit({ ...local, company_logo: b64 });
      setLogoPreview(result);
    };
    reader.readAsDataURL(file);
  };

  const preview = () => {
    if (!tenantId) return;
    window.open(`/api/admin/tenants/${tenantId}/report-preview`, "_blank");
  };

  return (
    <div className="border border-[#1a1a1a]">
      <div className="px-4 py-2.5 border-b border-[#1a1a1a] bg-[#050505] flex items-center gap-2">
        <FileText className="w-3 h-3 text-[#00e5a0]" />
        <span className="section-tag">// INFORMES CONTABLES</span>
        {tenantId && (
          <button
            onClick={preview}
            className="btn-secondary ml-auto inline-flex items-center gap-1.5"
          >
            <Eye className="w-3 h-3" />
            VISTA PREVIA
          </button>
        )}
      </div>

      <div className="p-4 grid grid-cols-1 gap-4">
        {/* Nombre empresa */}
        <div>
          <label className="label">Nombre de la empresa</label>
          <input
            className="input font-mono text-xs"
            placeholder="Razón social"
            value={local.company_name}
            onChange={(e) => setField("company_name", e.target.value)}
          />
        </div>

        {/* Logo */}
        <div>
          <label className="label">Logo de la empresa</label>
          <div className="flex items-center gap-3">
            <input
              type="file"
              accept="image/*"
              className="hidden"
              id="logo-upload"
              onChange={(e) => handleLogo(e.target.files?.[0])}
            />
            <label
              htmlFor="logo-upload"
              className="btn-secondary cursor-pointer inline-flex items-center gap-1.5"
            >
              <Upload className="w-3 h-3" />
              SUBIR LOGO
            </label>
            {local.company_logo && (
              <span className="font-mono text-[10px] text-[#00e5a0]">✓ Logo cargado</span>
            )}
          </div>
          {logoPreview && (
            <img src={logoPreview} className="max-h-16 mt-2" />
          )}
          <p className="font-mono text-[10px] text-[#333] mt-1.5">
            PNG o JPG. Se mostrará en el encabezado del PDF.
          </p>
        </div>

        {/* Secciones */}
        <div>
          <label className="label">Secciones del informe</label>
          <div className="grid grid-cols-2 gap-2 mt-1">
            {ALL_SECTIONS.map((sec) => (
              <label
                key={sec.id}
                className="flex items-center gap-2 font-mono text-[11px] cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={local.sections.includes(sec.id)}
                  onChange={() => toggleSection(sec.id)}
                  className="w-3 h-3 accent-[#00e5a0]"
                />
                {sec.label}
              </label>
            ))}
          </div>
        </div>

        {/* Instrucciones adicionales */}
        <div>
          <label className="label">Instrucciones adicionales para el informe</label>
          <textarea
            className="input font-mono text-xs min-h-[60px] resize-y"
            placeholder="Ej: Incluir comparativa con el mes anterior, destacar variaciones mayores al 10%..."
            value={local.additional_instructions ?? ""}
            onChange={(e) => setField("additional_instructions", e.target.value)}
          />
          <p className="font-mono text-[10px] text-[#333] mt-1.5">
            Instrucciones en lenguaje natural para el agente sobre cómo generar el informe.
          </p>
        </div>
      </div>
    </div>
  );
}

export default ReportConfig;