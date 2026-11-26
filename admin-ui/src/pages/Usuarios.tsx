import { useEffect, useState } from "react";
import { useQueries, useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, Pencil, Plus, Send, Trash2, UserCheck, UserX, X } from "lucide-react";
import api, { tenantsApi } from "../lib/api";
import PageHeader from "../components/PageHeader";
import { useTenant } from "../contexts/TenantContext";

interface Membership {
  id?: number;
  tenant_id: number;
  tenant_name: string;
  tenant_slug?: string;
  role_id: number;
  role_name: string;
  role_description?: string | null;
  is_active?: boolean;
}

interface TelegramLink {
  chat_id: number;
  tenant_id: number;
}

interface PortalUser {
  id: number;
  username: string;
  full_name: string | null;
  is_active: boolean;
  store_active?: boolean;
  must_change_password: boolean;
  has_temp_password: boolean;
  has_password: boolean;
  created_at: string | null;
  memberships: Membership[];
  telegram_links: TelegramLink[];
}

interface TenantOption {
  id: number;
  name: string;
  slug?: string;
}

interface RoleOption {
  id: number;
  name: string;
  description?: string | null;
}

interface TempInfo {
  username: string;
  password: string;
}

function MembershipRows({
  memberships,
  setMemberships,
  tenants,
  rolesByTenant,
  lockedTenantId,
}: {
  memberships: { tenant_id: number; role_id: number }[];
  setMemberships: (rows: { tenant_id: number; role_id: number }[]) => void;
  tenants: TenantOption[];
  rolesByTenant: Record<number, RoleOption[]>;
  lockedTenantId?: number | null;
}) {
  const update = (index: number, patch: Partial<{ tenant_id: number; role_id: number }>) => {
    const next = memberships.map((row, i) => (i === index ? { ...row, ...patch } : row));
    setMemberships(next);
  };

  const add = () => {
    const used = new Set(memberships.map((m) => m.tenant_id));
    const tenant = tenants.find((t) => !used.has(t.id));
    if (!tenant) return;
    const role = rolesByTenant[tenant.id]?.[0];
    if (!role) return;
    setMemberships([...memberships, { tenant_id: tenant.id, role_id: role.id }]);
  };

  return (
    <div className="space-y-2">
      {memberships.map((row, index) => {
        const roles = rolesByTenant[row.tenant_id] ?? [];
        const locked = lockedTenantId != null;
        return (
          <div key={`${row.tenant_id}-${index}`} className="grid grid-cols-1 gap-2 sm:grid-cols-[1.2fr_1.4fr_auto]">
            <select
              className="input"
              value={row.tenant_id}
              disabled={locked}
              onChange={(e) => {
                const tenantId = Number(e.target.value);
                const role = rolesByTenant[tenantId]?.[0];
                update(index, { tenant_id: tenantId, role_id: role?.id ?? 0 });
              }}
            >
              {tenants.map((t) => (
                <option key={t.id} value={t.id} disabled={memberships.some((m, i) => i !== index && m.tenant_id === t.id)}>
                  {t.name || "Tu tienda"}
                </option>
              ))}
            </select>
            <select
              className="input"
              value={row.role_id || ""}
              onChange={(e) => update(index, { role_id: Number(e.target.value) })}
            >
              <option value="" disabled>Selecciona un rol</option>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>{r.description || r.name}</option>
              ))}
            </select>
            {!locked && memberships.length > 1 ? (
              <button
                type="button"
                className="btn-ghost px-2"
                onClick={() => setMemberships(memberships.filter((_, i) => i !== index))}
                title="Quitar tienda"
              >
                <X className="h-4 w-4" />
              </button>
            ) : <span />}
          </div>
        );
      })}
      {lockedTenantId == null && memberships.length < tenants.length && (
        <button type="button" className="btn-ghost px-0 text-xs" onClick={add}>
          <Plus className="h-3.5 w-3.5" /> Agregar otra tienda
        </button>
      )}
    </div>
  );
}

function PortalUserModal({
  user,
  tenants,
  rolesByTenant,
  isSuperAdmin,
  lockedTenantId,
  onClose,
  onSaved,
}: {
  user: PortalUser | null;
  tenants: TenantOption[];
  rolesByTenant: Record<number, RoleOption[]>;
  isSuperAdmin: boolean;
  lockedTenantId: number | null;
  onClose: () => void;
  onSaved: (temp?: TempInfo) => void;
}) {
  const qc = useQueryClient();
  const isEdit = user !== null;
  const initialTenant = user?.memberships?.[0]?.tenant_id ?? tenants[0]?.id ?? 0;
  const initialRole = user?.memberships?.[0]?.role_id
    ?? rolesByTenant[initialTenant]?.[0]?.id ?? 0;

  const [username, setUsername] = useState(user?.username ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [password, setPassword] = useState("");
  const [generateTemp, setGenerateTemp] = useState(!isEdit);
  const [telegram, setTelegram] = useState(
    user?.telegram_links?.[0]?.chat_id != null ? String(user.telegram_links[0].chat_id) : "",
  );
  const [memberships, setMemberships] = useState<{ tenant_id: number; role_id: number }[]>(
    user?.memberships?.length
      ? user.memberships.map((m) => ({ tenant_id: m.tenant_id, role_id: m.role_id }))
      : [{ tenant_id: initialTenant, role_id: initialRole }],
  );
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isEdit) return;
    setMemberships((prev) => {
      if (!prev.length) return [{ tenant_id: initialTenant, role_id: initialRole }];
      if (prev.length === 1 && prev[0].tenant_id === initialTenant && !prev[0].role_id && initialRole) {
        return [{ ...prev[0], role_id: initialRole }];
      }
      return prev;
    });
  }, [initialTenant, initialRole, isEdit]);

  const submit = async () => {
    setError("");
    if (!memberships.length || memberships.some((m) => !m.tenant_id || !m.role_id)) {
      setError("Selecciona una tienda y un rol.");
      return;
    }
    if (!isEdit && !username.trim()) {
      setError("El usuario es obligatorio.");
      return;
    }
    if (!isEdit && !password && !generateTemp) {
      setError("Define una contraseña o activa la contraseña temporal.");
      return;
    }
    if (telegram && !/^\d+$/.test(telegram)) {
      setError("El ID de Telegram debe ser numérico.");
      return;
    }
    setSaving(true);
    try {
      if (!isEdit) {
        const r = await api.post("/portal-users", {
          username: username.trim(),
          full_name: fullName.trim() || null,
          password: password || null,
          generate_temp_password: !password && generateTemp,
          telegram_chat_id: isSuperAdmin && telegram ? Number(telegram) : null,
          memberships,
        });
        onSaved(r.data.temp_password ? { username: username.trim(), password: r.data.temp_password } : undefined);
      } else {
        await api.patch(`/portal-users/${user.id}`, {
          full_name: fullName.trim() || null,
        });
        await api.put(`/portal-users/${user.id}/memberships`, { memberships });
        if (isSuperAdmin) {
          await api.put(`/portal-users/${user.id}/telegram`, {
            chat_id: telegram ? Number(telegram) : null,
          });
        }
        qc.invalidateQueries({ queryKey: ["portal-users"] });
        onSaved();
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "No se pudo guardar el usuario.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl">
        <div className="flex items-start justify-between border-b border-[var(--color-border-subtle)] px-6 py-4">
          <div>
            <p className="section-tag mb-1">{isEdit ? "EDITAR USUARIO" : "NUEVO USUARIO"}</p>
            <h2 className="text-lg font-semibold tracking-tight text-[var(--color-text)]">
              {isEdit ? user.username : "Crear usuario de portal"}
            </h2>
          </div>
          <button className="vc-icon-btn" onClick={onClose}><X className="h-4 w-4" /></button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          {!isEdit && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="label">Usuario</label>
                <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="juan.perez" />
              </div>
              <div>
                <label className="label">Nombre completo</label>
                <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Opcional" />
              </div>
            </div>
          )}

          {isEdit && (
            <div>
              <label className="label">Nombre completo</label>
              <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Opcional" />
            </div>
          )}

          {!isEdit && (
            <div>
              <label className="label">Contraseña</label>
              <input
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={generateTemp ? "Se generará una temporal" : "Contraseña"}
              />
              <label className="mt-2 flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                <input
                  type="checkbox"
                  checked={generateTemp}
                  onChange={(e) => setGenerateTemp(e.target.checked)}
                />
                Generar contraseña temporal automática
              </label>
            </div>
          )}

          <div>
            <p className="mb-2 text-2xs font-semibold uppercase tracking-[0.08em] text-[var(--color-text-subtle)]">
              Tiendas y roles
            </p>
            <MembershipRows
              memberships={memberships}
              setMemberships={setMemberships}
              tenants={tenants}
              rolesByTenant={rolesByTenant}
              lockedTenantId={lockedTenantId}
            />
          </div>

          {isSuperAdmin && (
            <div>
              <label className="label">ID de chat de Telegram (opcional)</label>
              <input
                className="input"
                value={telegram}
                onChange={(e) => setTelegram(e.target.value)}
                placeholder="Ej: 6899875418"
              />
              <p className="mt-1 text-2xs text-[var(--color-text-subtle)]">
                Si lo vinculas, el usuario también podrá escribir por Telegram.
              </p>
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[var(--color-border-subtle)] px-6 py-4">
          <button className="btn-ghost" onClick={onClose}>CANCELAR</button>
          <button className="btn-primary" onClick={submit} disabled={saving}>
            {saving ? "GUARDANDO..." : isEdit ? "GUARDAR" : "CREAR USUARIO"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Usuarios() {
  const qc = useQueryClient();
  const { tenantId, activeTenant, isSuperAdmin } = useTenant();
  const [modal, setModal] = useState<{ user: PortalUser | null } | null>(null);
  const [tempInfo, setTempInfo] = useState<TempInfo | null>(null);

  const { data: allTenants = [] } = useQuery<TenantOption[]>({
    queryKey: ["tenants"],
    queryFn: tenantsApi.list,
    enabled: isSuperAdmin,
  });

  const tenants: TenantOption[] = isSuperAdmin
    ? allTenants
    : activeTenant
    ? [{ id: activeTenant.id, name: activeTenant.name || "Tu tienda", slug: activeTenant.slug }]
    : [];

  const { data: users = [], isLoading } = useQuery<PortalUser[]>({
    queryKey: ["portal-users", tenantId, isSuperAdmin],
    queryFn: () => api.get("/portal-users", {
      params: isSuperAdmin ? undefined : { tenant_id: tenantId },
    }).then((r) => r.data),
    enabled: isSuperAdmin || tenantId !== null,
  });

  const roleQueries = useQueries({
    queries: tenants.map((t) => ({
      queryKey: ["roles", t.id],
      queryFn: () => api.get<RoleOption[]>("/roles", { params: { tenant_id: t.id } }).then((r) => r.data),
      enabled: !!t.id,
    })),
  });
  const rolesByTenant: Record<number, RoleOption[]> = {};
  tenants.forEach((t, i) => { rolesByTenant[t.id] = roleQueries[i]?.data ?? []; });

  const toggle = useMutation({
    mutationFn: (u: PortalUser) => api.patch(`/portal-users/${u.id}`, { is_active: !(u.store_active ?? u.is_active) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portal-users"] }),
  });

  const remove = useMutation({
    mutationFn: (u: PortalUser) => api.delete(`/portal-users/${u.id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portal-users"] }),
  });

  const revealTemp = async (user: PortalUser) => {
    try {
      const r = await api.get(`/portal-users/${user.id}/temp-password`);
      setTempInfo({ username: user.username, password: r.data.temp_password });
    } catch {
      const r = await api.post(`/portal-users/${user.id}/temp-password`);
      setTempInfo({ username: user.username, password: r.data.temp_password });
      qc.invalidateQueries({ queryKey: ["portal-users"] });
    }
  };

  return (
    <div>
      <PageHeader
        tag="ACCESO"
        title="Usuarios"
        description={isSuperAdmin ? "Usuarios, tiendas y roles del portal" : "Usuarios de tu tienda"}
        action={
          <button className="btn-primary flex items-center gap-2" onClick={() => setModal({ user: null })}>
            <Plus className="h-3.5 w-3.5" /> NUEVO USUARIO
          </button>
        }
      />

      <div className="px-5 py-6 sm:px-8 sm:py-8">
        <div className="overflow-hidden rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface)]">
          <div className="grid grid-cols-12 border-b border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]">
            <div className="col-span-3 th">Usuario</div>
            <div className="col-span-4 th">Tiendas y roles</div>
            <div className="col-span-2 th">Telegram</div>
            <div className="col-span-2 th">Acceso</div>
            <div className="col-span-1 th text-right">Acciones</div>
          </div>

          {isLoading && Array(4).fill(0).map((_, i) => (
            <div key={i} className="h-16 animate-pulse border-b border-[var(--color-border-subtle)]" />
          ))}

          {!isLoading && users.map((u) => (
            <div key={u.id} className="grid grid-cols-12 border-b border-[var(--color-border-subtle)] transition-colors last:border-b-0 hover:bg-[var(--color-bg-elevated)]">
              <div className="col-span-3 td">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border border-[var(--color-accent)] bg-[var(--color-accent)]">
                    <span className="text-xs font-semibold text-[var(--color-accent-contrast)]">
                      {(u.full_name || u.username)[0]?.toUpperCase()}
                    </span>
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-[var(--color-text)]">{u.username}</p>
                    <p className="truncate text-2xs text-[var(--color-text-subtle)]">
                      {u.full_name || "Sin nombre"}
                    </p>
                  </div>
                </div>
              </div>

              <div className="col-span-4 td">
                <div className="flex flex-wrap gap-1">
                  {u.memberships.map((m) => (
                    <span key={`${m.tenant_id}-${m.role_id}`} className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-0.5 text-2xs text-[var(--color-text-muted)]">
                      {m.tenant_name} · {m.role_description || m.role_name}
                    </span>
                  ))}
                  {u.memberships.length === 0 && (
                    <span className="text-2xs text-[var(--color-text-subtle)]">Sin tiendas</span>
                  )}
                </div>
              </div>

              <div className="col-span-2 td">
                {u.telegram_links.length > 0 ? (
                  <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]">
                    <Send className="h-3 w-3" />
                    {u.telegram_links.map((t) => t.chat_id).join(", ")}
                  </div>
                ) : (
                  <span className="text-2xs text-[var(--color-text-subtle)]">Sin Telegram</span>
                )}
              </div>

              <div className="col-span-2 td">
                <div className="flex flex-col gap-1">
                  <span className={`badge w-fit ${(u.store_active ?? u.is_active) ? "badge-green" : "badge-slate"}`}>
                    {(u.store_active ?? u.is_active) ? "Activo" : "Inactivo"}
                  </span>
                  <span className="text-2xs text-[var(--color-text-subtle)]">
                    {u.has_temp_password ? "Contraseña temporal" : u.has_password ? "Con contraseña" : "Sin contraseña"}
                  </span>
                </div>
              </div>

              <div className="col-span-1 td">
                <div className="flex items-center justify-end gap-0.5">
                  <button
                    className="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-accent-strong)]"
                    title="Editar"
                    onClick={() => setModal({ user: u })}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  {(isSuperAdmin || u.memberships.length <= 1) && (
                    <button
                      className="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-accent-strong)]"
                      title="Contraseña temporal"
                      onClick={() => revealTemp(u)}
                    >
                      <KeyRound className="h-3.5 w-3.5" />
                    </button>
                  )}
                  <button
                    className="p-1.5 text-[var(--color-text-muted)] hover:text-amber-700"
                    title={(u.store_active ?? u.is_active) ? "Desactivar" : "Activar"}
                    onClick={() => toggle.mutate(u)}
                  >
                    {(u.store_active ?? u.is_active) ? <UserX className="h-3.5 w-3.5" /> : <UserCheck className="h-3.5 w-3.5" />}
                  </button>
                  {isSuperAdmin && (
                    <button
                      className="p-1.5 text-[var(--color-text-muted)] hover:text-red-700"
                      title="Eliminar"
                      onClick={() => window.confirm(`¿Eliminar a ${u.username}?`) && remove.mutate(u)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}

          {!isLoading && users.length === 0 && (
            <p className="px-5 py-12 text-center text-sm text-[var(--color-text-subtle)]">
              Aún no hay usuarios. Crea el primero.
            </p>
          )}
        </div>
      </div>

      {modal && (
        <PortalUserModal
          user={modal.user}
          tenants={tenants}
          rolesByTenant={rolesByTenant}
          isSuperAdmin={isSuperAdmin}
          lockedTenantId={isSuperAdmin ? null : tenantId}
          onClose={() => setModal(null)}
          onSaved={(temp) => {
            setModal(null);
            qc.invalidateQueries({ queryKey: ["portal-users"] });
            if (temp) setTempInfo(temp);
          }}
        />
      )}

      {tempInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-2xl">
            <p className="section-tag mb-2">CONTRASEÑA TEMPORAL</p>
            <h2 className="text-lg font-semibold tracking-tight text-[var(--color-text)]">
              {tempInfo.username}
            </h2>
            <p className="mt-2 text-sm text-[var(--color-text-muted)]">
              Compártela con el usuario de forma privada.
            </p>
            <div className="mt-4 flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2">
              <code className="flex-1 font-mono text-sm text-[var(--color-text)]">{tempInfo.password}</code>
              <button
                className="vc-icon-btn"
                title="Copiar"
                onClick={() => navigator.clipboard?.writeText(tempInfo.password)}
              >
                <Copy className="h-4 w-4" />
              </button>
            </div>
            <button className="btn-primary mt-5 w-full" onClick={() => setTempInfo(null)}>
              ENTENDIDO
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
