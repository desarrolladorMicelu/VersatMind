import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, Bell, BellOff, Check } from "lucide-react";
import { consumoApi } from "../lib/api";
import type { UsageGlobalRow, UsageSettings } from "../lib/api";
import { fmtDate } from "../lib/utils";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmtUsd = (v: number | null | undefined) =>
  `$${(v ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const fmtNum = (v: number | null | undefined) =>
  (v ?? 0).toLocaleString("es-CO");

function Kpi({ label, value, accent, danger }: { label: string; value: string; accent?: boolean; danger?: boolean }) {
  return (
    <div className="bg-black p-6">
      <p className="font-mono text-[10px] uppercase tracking-widest text-white mb-3">{label}</p>
      <p className={`text-3xl font-bold ${danger ? "text-red-500" : accent ? "text-[#00e5a0]" : "text-white"}`}>{value}</p>
    </div>
  );
}

// ── Vista global (superadmin): consumo por cliente ────────────────────────────

function GlobalConsumo({ onSelect }: { onSelect: (row: UsageGlobalRow) => void }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["consumo-global"],
    queryFn: () => consumoApi.global(),
    refetchInterval: 30000,
  });

  const totals = data?.totals;
  const rows = data?.tenants ?? [];

  return (
    <div>
      <PageHeader
        tag="ADMIN"
        title="Consumo"
        description="Tokens y costo estimado por cliente — selecciona uno para el detalle"
      />
      <div className="px-8 py-8 space-y-8">
        {isError && (
          <div className="border border-red-900/50 bg-red-950/20 px-5 py-4">
            <p className="font-mono text-[11px] text-red-400 uppercase tracking-widest">
              No se pudo cargar el consumo. Verifica que el backend esté actualizado y que la
              migración de consumo (0009) esté aplicada.
            </p>
          </div>
        )}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-px bg-[#1a1a1a]">
          {isLoading ? (
            Array(4).fill(0).map((_, i) => <div key={i} className="bg-black p-6 h-24 animate-pulse" />)
          ) : (
            <>
              <Kpi label="Costo total" value={isError ? "—" : fmtUsd(totals?.total_cost_usd)} accent />
              <Kpi label="Tokens totales" value={isError ? "—" : fmtNum(totals?.total_tokens)} />
              <Kpi label="Clientes con consumo" value={isError ? "—" : fmtNum(totals?.tenants_count)} />
              <Kpi label="Usuarios sobre umbral" value={isError ? "—" : fmtNum(totals?.over_threshold_count)} danger={(totals?.over_threshold_count ?? 0) > 0} />
            </>
          )}
        </div>

        <div>
          <p className="section-tag mb-4">// Consumo por cliente</p>
          <div className="border border-[#1a1a1a]">
            <div className="grid grid-cols-12 bg-[#050505] border-b border-[#1a1a1a]">
              <div className="col-span-4 th">Cliente</div>
              <div className="col-span-2 th">Tokens</div>
              <div className="col-span-2 th">Costo USD</div>
              <div className="col-span-2 th">Usuarios</div>
              <div className="col-span-2 th">Sobre umbral</div>
            </div>
            {isLoading ? (
              Array(4).fill(0).map((_, i) => <div key={i} className="h-12 border-b border-[#111] animate-pulse" />)
            ) : rows.length === 0 ? (
              <p className="px-5 py-10 text-center font-mono text-xs text-white">SIN CONSUMO REGISTRADO</p>
            ) : (
              rows.map((r) => (
                <button
                  key={r.tenant_id}
                  onClick={() => onSelect(r)}
                  className="w-full text-left grid grid-cols-12 border-b border-[#111] hover:bg-[#050505] transition-colors items-center"
                >
                  <div className="col-span-4 td">
                    <div className="flex items-center gap-2">
                      <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${r.is_active ? "bg-[#00e5a0]" : "bg-[#333]"}`} />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-white truncate">{r.name}</p>
                        <p className="font-mono text-[10px] text-white">{r.slug}</p>
                      </div>
                    </div>
                  </div>
                  <div className="col-span-2 td font-mono text-xs text-white">{fmtNum(r.total_tokens)}</div>
                  <div className="col-span-2 td font-mono text-xs text-[#00e5a0]">{fmtUsd(r.total_cost_usd)}</div>
                  <div className="col-span-2 td font-mono text-xs text-white">
                    {fmtNum(r.users_count)}
                    {r.paused_count > 0 && <span className="text-red-500 ml-2">({r.paused_count} paus.)</span>}
                  </div>
                  <div className="col-span-2 td">
                    <span className={`badge ${r.over_threshold_count > 0 ? "badge-red" : "badge-green"}`}>
                      {fmtNum(r.over_threshold_count)}
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Formulario de configuración de umbral ─────────────────────────────────────

function SettingsForm({ tenantId, config }: { tenantId: number; config: UsageSettings }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<UsageSettings>(config);

  const save = useMutation({
    mutationFn: () => consumoApi.updateConfig(tenantId, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["consumo-config", tenantId] });
      qc.invalidateQueries({ queryKey: ["consumo-usuarios", tenantId] });
    },
  });

  return (
    <div className="border border-[#1a1a1a] p-6">
      <p className="section-tag mb-5">// Configuración de alertas</p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div>
          <label className="label">Umbral por usuario (USD)</label>
          <input
            type="number" min={0} step="0.5" className="input"
            value={form.threshold_usd}
            onChange={(e) => setForm({ ...form, threshold_usd: parseFloat(e.target.value) || 0 })}
          />
        </div>
        <div>
          <label className="label">Período</label>
          <select
            className="input" value={form.period}
            onChange={(e) => setForm({ ...form, period: e.target.value as UsageSettings["period"] })}
          >
            <option value="month">Mensual</option>
            <option value="total">Acumulado histórico</option>
          </select>
        </div>
        <div>
          <label className="label">Email de alertas (opcional)</label>
          <input
            type="email" className="input" placeholder="admin@empresa.com"
            value={form.admin_email ?? ""}
            onChange={(e) => setForm({ ...form, admin_email: e.target.value || null })}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-6 mt-6">
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={form.auto_pause}
            onChange={(e) => setForm({ ...form, auto_pause: e.target.checked })} />
          <span className="font-mono text-[11px] uppercase tracking-widest text-white">Pausar automáticamente</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={form.notify_telegram}
            onChange={(e) => setForm({ ...form, notify_telegram: e.target.checked })} />
          <span className="font-mono text-[11px] uppercase tracking-widest text-white">Notificar por Telegram</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={form.notify_email}
            onChange={(e) => setForm({ ...form, notify_email: e.target.checked })} />
          <span className="font-mono text-[11px] uppercase tracking-widest text-white">Notificar por email</span>
        </label>
        <button className="btn-primary ml-auto" disabled={save.isPending} onClick={() => save.mutate()}>
          Guardar
        </button>
      </div>
      {save.isSuccess && <p className="font-mono text-[10px] text-[#00e5a0] mt-3">Configuración guardada.</p>}
      {save.isError && <p className="font-mono text-[10px] text-red-500 mt-3">No se pudo guardar.</p>}
    </div>
  );
}

// ── Detalle por cliente ───────────────────────────────────────────────────────

function TenantConsumo({ tenantId }: { tenantId: number }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"usuarios" | "historial" | "alertas">("usuarios");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [source, setSource] = useState("");

  const rangeParams = {
    ...(dateFrom ? { date_from: dateFrom } : {}),
    ...(dateTo ? { date_to: dateTo } : {}),
  };

  const { data: config } = useQuery({
    queryKey: ["consumo-config", tenantId],
    queryFn: () => consumoApi.config(tenantId),
  });

  const { data: usuarios, isLoading: loadingUsers, isError: usersError } = useQuery({
    queryKey: ["consumo-usuarios", tenantId, dateFrom, dateTo],
    queryFn: () => consumoApi.usuarios(tenantId, rangeParams),
    enabled: tenantId !== null,
    refetchInterval: 30000,
  });

  const { data: historial, isLoading: loadingHist } = useQuery({
    queryKey: ["consumo-historial", tenantId, dateFrom, dateTo, source],
    queryFn: () =>
      consumoApi.historial({
        tenant_id: tenantId,
        ...rangeParams,
        ...(source ? { source } : {}),
        limit: 100,
      }),
    enabled: tab === "historial",
  });

  const { data: alertas = [], isLoading: loadingAlerts } = useQuery({
    queryKey: ["consumo-alertas", tenantId],
    queryFn: () => consumoApi.alertas({ tenant_id: tenantId }),
    enabled: tab === "alertas",
    refetchInterval: 30000,
  });

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["consumo-usuarios", tenantId] });
    qc.invalidateQueries({ queryKey: ["consumo-alertas", tenantId] });
    qc.invalidateQueries({ queryKey: ["consumo-global"] });
  };

  const pausar = useMutation({
    mutationFn: (chatId: number) => consumoApi.pausar(tenantId, chatId),
    onSuccess: invalidateAll,
  });
  const reanudar = useMutation({
    mutationFn: (chatId: number) => consumoApi.reanudar(tenantId, chatId),
    onSuccess: invalidateAll,
  });
  const reconocer = useMutation({
    mutationFn: (id: number) => consumoApi.reconocerAlerta(id),
    onSuccess: invalidateAll,
  });

  const threshold = usuarios?.threshold_usd ?? config?.threshold_usd ?? 8;
  const totals = usuarios?.totals;
  const userRows = usuarios?.usuarios ?? [];

  return (
    <div>
      <PageHeader tag="ADMIN" title="Consumo" description="Tokens y costo estimado por usuario" />
      <div className="px-8 py-8 space-y-8">

        {usersError && (
          <div className="border border-red-900/50 bg-red-950/20 px-5 py-4">
            <p className="font-mono text-[11px] text-red-400 uppercase tracking-widest">
              No se pudo cargar el consumo. Verifica que el backend esté actualizado y que la
              migración de consumo (0009) esté aplicada en esta base de datos.
            </p>
          </div>
        )}

        <div className="grid grid-cols-2 xl:grid-cols-4 gap-px bg-[#1a1a1a]">
          {loadingUsers ? (
            Array(4).fill(0).map((_, i) => <div key={i} className="bg-black p-6 h-24 animate-pulse" />)
          ) : (
            <>
              <Kpi label="Costo total" value={usersError ? "—" : fmtUsd(totals?.total_cost_usd)} accent />
              <Kpi label="Tokens totales" value={usersError ? "—" : fmtNum(totals?.total_tokens)} />
              <Kpi label="Usuarios sobre umbral" value={usersError ? "—" : fmtNum(totals?.over_threshold_count)} danger={(totals?.over_threshold_count ?? 0) > 0} />
              <Kpi label="Usuarios pausados" value={usersError ? "—" : fmtNum(totals?.paused_count)} danger={(totals?.paused_count ?? 0) > 0} />
            </>
          )}
        </div>

        {config && <SettingsForm key={JSON.stringify(config)} tenantId={tenantId} config={config} />}

        {/* Filtros */}
        <div className="flex flex-wrap items-end gap-4">
          <div className="w-44">
            <label className="label">Desde</label>
            <input type="date" className="input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div className="w-44">
            <label className="label">Hasta</label>
            <input type="date" className="input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          {(dateFrom || dateTo) && (
            <button className="btn-ghost" onClick={() => { setDateFrom(""); setDateTo(""); }}>Limpiar</button>
          )}
          <div className="ml-auto flex gap-1">
            {(["usuarios", "historial", "alertas"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`font-mono text-[10px] uppercase tracking-widest px-3 py-2 border transition-colors ${
                  tab === t ? "border-[#00e5a0] text-[#00e5a0]" : "border-[#2a2a2a] text-white hover:border-[#3a3a3a]"
                }`}
              >
                {t}
                {t === "alertas" && (usuarios?.totals.over_threshold_count ?? 0) > 0 && (
                  <span className="ml-2 text-red-500">●</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {tab === "usuarios" && (
          <div className="border border-[#1a1a1a]">
            <div className="grid grid-cols-12 bg-[#050505] border-b border-[#1a1a1a]">
              <div className="col-span-3 th">Usuario</div>
              <div className="col-span-2 th">Tokens</div>
              <div className="col-span-2 th">Costo USD</div>
              <div className="col-span-3 th">Consumo vs umbral ({fmtUsd(threshold)})</div>
              <div className="col-span-2 th">Acciones</div>
            </div>
            {loadingUsers ? (
              Array(4).fill(0).map((_, i) => <div key={i} className="h-14 border-b border-[#111] animate-pulse" />)
            ) : userRows.length === 0 ? (
              <p className="px-5 py-10 text-center font-mono text-xs text-white">SIN CONSUMO EN EL PERÍODO</p>
            ) : (
              userRows.map((u) => {
                const pct = threshold > 0 ? Math.min(100, (u.cost_usd / threshold) * 100) : 0;
                return (
                  <div key={u.chat_id} className="grid grid-cols-12 border-b border-[#111] hover:bg-[#050505] transition-colors items-center">
                    <div className="col-span-3 td">
                      <p className="text-sm font-medium text-white">{u.username || "—"}</p>
                      <p className="font-mono text-[10px] text-white">chat {u.chat_id} · {u.role_name}</p>
                    </div>
                    <div className="col-span-2 td font-mono text-xs text-white">{fmtNum(u.total_tokens)}</div>
                    <div className={`col-span-2 td font-mono text-xs ${u.over_threshold ? "text-red-500" : "text-[#00e5a0]"}`}>
                      {fmtUsd(u.cost_usd)}
                    </div>
                    <div className="col-span-3 td">
                      <div className="h-1.5 bg-[#1a1a1a] w-full">
                        <div className="h-full" style={{ width: `${pct}%`, backgroundColor: u.over_threshold ? "#f87171" : "#00e5a0" }} />
                      </div>
                      <p className="font-mono text-[9px] text-white mt-1">
                        {pct.toFixed(0)}% {u.has_alert && <span className="text-red-500 ml-2">ALERTA</span>}
                      </p>
                    </div>
                    <div className="col-span-2 td">
                      <div className="flex items-center gap-2">
                        {u.is_paused ? (
                          <button
                            onClick={() => reanudar.mutate(u.chat_id)}
                            className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-[#00e5a0] border border-[#00e5a0]/30 px-2 py-1 hover:bg-[#00e5a0]/10 transition-colors"
                          >
                            <Play className="w-3 h-3" /> Reanudar
                          </button>
                        ) : (
                          <button
                            onClick={() => window.confirm("¿Pausar el acceso de este usuario?") && pausar.mutate(u.chat_id)}
                            className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-yellow-500 border border-yellow-500/30 px-2 py-1 hover:bg-yellow-500/10 transition-colors"
                          >
                            <Pause className="w-3 h-3" /> Pausar
                          </button>
                        )}
                        {u.is_paused && <span className="badge badge-red">PAUSADO</span>}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {tab === "historial" && (
          <div className="border border-[#1a1a1a]">
            <div className="flex items-center justify-between px-5 py-3 bg-[#050505] border-b border-[#1a1a1a]">
              <span className="section-tag">// {fmtNum(historial?.total)} registros</span>
              <select className="bg-black border border-[#2a2a2a] text-xs text-white px-2 py-1 font-mono focus:outline-none"
                value={source} onChange={(e) => setSource(e.target.value)}>
                <option value="">Todos los orígenes</option>
                <option value="chat">Chat</option>
                <option value="scheduler">Tareas programadas</option>
              </select>
            </div>
            <div className="grid grid-cols-12 bg-[#050505] border-b border-[#1a1a1a]">
              <div className="col-span-3 th">Fecha</div>
              <div className="col-span-2 th">Usuario</div>
              <div className="col-span-2 th">Modelo</div>
              <div className="col-span-2 th">Tokens</div>
              <div className="col-span-2 th">Costo</div>
              <div className="col-span-1 th">Origen</div>
            </div>
            {loadingHist ? (
              Array(5).fill(0).map((_, i) => <div key={i} className="h-10 border-b border-[#111] animate-pulse" />)
            ) : (historial?.rows.length ?? 0) === 0 ? (
              <p className="px-5 py-10 text-center font-mono text-xs text-white">SIN REGISTROS</p>
            ) : (
              historial!.rows.map((h) => (
                <div key={h.id} className="grid grid-cols-12 border-b border-[#111] hover:bg-[#050505] transition-colors items-center">
                  <div className="col-span-3 td font-mono text-[11px] text-white">{fmtDate(h.created_at)}</div>
                  <div className="col-span-2 td font-mono text-[11px] text-white">{h.username || h.chat_id || "—"}</div>
                  <div className="col-span-2 td font-mono text-[10px] text-white truncate">{h.model || "—"}</div>
                  <div className="col-span-2 td font-mono text-xs text-white">{fmtNum(h.total_tokens)}</div>
                  <div className="col-span-2 td font-mono text-xs text-[#00e5a0]">{fmtUsd(h.cost_usd)}</div>
                  <div className="col-span-1 td">
                    <span className={`badge ${h.source === "scheduler" ? "badge-amber" : "badge-slate"}`}>{h.source}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {tab === "alertas" && (
          <div className="border border-[#1a1a1a]">
            <div className="grid grid-cols-12 bg-[#050505] border-b border-[#1a1a1a]">
              <div className="col-span-3 th">Usuario</div>
              <div className="col-span-2 th">Consumo</div>
              <div className="col-span-2 th">Umbral</div>
              <div className="col-span-2 th">Período</div>
              <div className="col-span-2 th">Estado</div>
              <div className="col-span-1 th" />
            </div>
            {loadingAlerts ? (
              Array(3).fill(0).map((_, i) => <div key={i} className="h-12 border-b border-[#111] animate-pulse" />)
            ) : alertas.length === 0 ? (
              <p className="px-5 py-10 text-center font-mono text-xs text-white">SIN ALERTAS</p>
            ) : (
              alertas.map((a) => (
                <div key={a.id} className="grid grid-cols-12 border-b border-[#111] hover:bg-[#050505] transition-colors items-center">
                  <div className="col-span-3 td">
                    <p className="text-sm text-white">{a.username || "—"}</p>
                    <p className="font-mono text-[10px] text-white">{fmtDate(a.created_at)}</p>
                  </div>
                  <div className="col-span-2 td font-mono text-xs text-red-500">{fmtUsd(a.total_cost_usd)}</div>
                  <div className="col-span-2 td font-mono text-xs text-white">{fmtUsd(a.threshold_usd)}</div>
                  <div className="col-span-2 td font-mono text-[11px] text-white">{a.period_key}</div>
                  <div className="col-span-2 td">
                    <span className={`badge ${a.status === "active" ? "badge-red" : "badge-slate"}`}>{a.status}</span>
                    {a.notified
                      ? <Bell className="w-3 h-3 text-[#00e5a0] inline ml-2" />
                      : <BellOff className="w-3 h-3 text-white inline ml-2" />}
                  </div>
                  <div className="col-span-1 td">
                    {a.status === "active" && (
                      <button
                        onClick={() => reconocer.mutate(a.id)}
                        className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-[#00e5a0] hover:underline"
                      >
                        <Check className="w-3 h-3" /> OK
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        )}

      </div>
    </div>
  );
}

// ── Página ────────────────────────────────────────────────────────────────────

export default function Consumo() {
  const { tenantId, isSuperAdmin, tenants, setActiveTenant } = useTenant();

  if (!tenantId) {
    if (!isSuperAdmin) {
      return (
        <div>
          <PageHeader tag="ADMIN" title="Consumo" description="Sin cliente asignado" />
          <div className="px-8 py-16 text-center">
            <p className="font-mono text-xs text-white uppercase tracking-widest">Selecciona un cliente en el panel izquierdo</p>
          </div>
        </div>
      );
    }
    return (
      <GlobalConsumo
        onSelect={(row) => {
          const t = tenants.find((x) => x.id === row.tenant_id);
          if (t) setActiveTenant(t);
        }}
      />
    );
  }

  return <TenantConsumo tenantId={tenantId} />;
}
