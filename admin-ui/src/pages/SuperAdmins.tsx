import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  ShieldCheck, Plus, KeyRound, Power, Trash2, X, Eye, EyeOff,
  Crown, Lock, AlertTriangle, UserCheck, Fingerprint,
} from "lucide-react";
import { superAdminsApi } from "../lib/api";
import type { SuperAdminAccount } from "../lib/api";
import PageHeader from "../components/PageHeader";

type ModalMode = "create" | "password";

interface ModalState {
  mode: ModalMode;
  account?: SuperAdminAccount;
}

function SuperAdminModal({
  state,
  onClose,
  onSubmit,
  saving,
  error,
}: {
  state: ModalState;
  onClose: () => void;
  onSubmit: (data: { username?: string; password: string }) => void;
  saving: boolean;
  error: string;
}) {
  const isCreate = state.mode === "create";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPass, setShowPass] = useState(false);

  const usernameOk = /^[A-Za-z0-9_.-]{3,64}$/.test(username.trim());
  const passOk = password.length >= 8;
  const matches = password === confirm;
  const canSubmit = (isCreate ? usernameOk : true) && passOk && matches;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg bg-[#0d0d0d] border border-[#2a2a2a] flex flex-col max-h-[90vh]">

        <div className="flex items-start justify-between px-6 py-5 border-b border-[#1a1a1a] flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 border border-[#00e5a0]/40 bg-[#00e5a0]/5 flex items-center justify-center">
              {isCreate ? <Fingerprint className="w-4 h-4 text-[#00e5a0]" /> : <KeyRound className="w-4 h-4 text-[#00e5a0]" />}
            </div>
            <div>
              <p className="section-tag mb-1">
                // {isCreate ? "NUEVO ACCESO ROOT" : "RESTABLECER CONTRASEÑA"}
              </p>
              <h2 className="text-lg font-bold text-white tracking-tight leading-none">
                {isCreate ? "Crear super admin" : state.account?.username}
              </h2>
            </div>
          </div>
          <button onClick={onClose} className="text-[#666] hover:text-white transition-colors p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="overflow-y-auto flex-1 px-6 py-6 space-y-5">
          <div className="flex gap-3 border border-amber-500/20 bg-amber-500/[0.04] px-4 py-3">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <p className="font-mono text-[10px] leading-relaxed text-amber-200/80">
              {isCreate
                ? "Un super admin puede ver y gestionar TODOS los clientes, cuentas y configuración del sistema. Crea estas cuentas solo para personal de confianza."
                : "La nueva contraseña reemplaza inmediatamente a la anterior. No se puede recuperar, solo volver a restablecer."}
            </p>
          </div>

          {isCreate && (
            <div>
              <label className="label">Usuario</label>
              <input
                className="input font-mono"
                placeholder="superadmin_ops"
                autoFocus
                autoComplete="off"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
              <p className={`font-mono text-[10px] mt-1.5 ${username && !usernameOk ? "text-red-400" : "text-[#555]"}`}>
                3-64 caracteres · letras, números, punto, guion o guion bajo
              </p>
            </div>
          )}

          <div>
            <label className="label">Contraseña</label>
            <div className="relative">
              <input
                className="input pr-10 font-mono"
                placeholder="Mínimo 8 caracteres"
                type={showPass ? "text" : "password"}
                autoComplete="new-password"
                autoFocus={!isCreate}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPass((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#666] hover:text-white transition-colors"
              >
                {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className={`font-mono text-[10px] mt-1.5 ${password && !passOk ? "text-red-400" : "text-[#555]"}`}>
              Mínimo 8 caracteres
            </p>
          </div>

          <div>
            <label className="label">Confirmar contraseña</label>
            <input
              className="input font-mono"
              placeholder="Repite la contraseña"
              type={showPass ? "text" : "password"}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canSubmit && !saving) {
                  onSubmit({ username: username.trim(), password });
                }
              }}
            />
            {confirm.length > 0 && !matches && (
              <p className="font-mono text-[10px] text-red-400 mt-1.5">Las contraseñas no coinciden</p>
            )}
          </div>

          {error && (
            <div className="border border-red-900 bg-red-950/30 px-4 py-3 font-mono text-[11px] text-red-400">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between px-6 py-4 border-t border-[#1a1a1a] flex-shrink-0">
          <button onClick={onClose} className="btn-ghost">CANCELAR</button>
          <button
            className="btn-primary"
            disabled={!canSubmit || saving}
            onClick={() => onSubmit({ username: username.trim(), password })}
          >
            {saving ? "GUARDANDO..." : isCreate ? "CREAR ACCESO →" : "ACTUALIZAR →"}
          </button>
        </div>

      </div>
    </div>
  );
}

function AccountRow({
  account,
  onResetPassword,
  onToggle,
  onRemove,
}: {
  account: SuperAdminAccount;
  onResetPassword: (a: SuperAdminAccount) => void;
  onToggle: (a: SuperAdminAccount) => void;
  onRemove: (a: SuperAdminAccount) => void;
}) {
  const isEnv = account.source === "env";
  const initials = account.username[0]?.toUpperCase() ?? "?";

  return (
    <div className="grid grid-cols-12 items-center border-b border-[#151515] hover:bg-[#050505] transition-colors">
      {/* Cuenta */}
      <div className="col-span-4 td">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 border flex items-center justify-center flex-shrink-0 ${
            isEnv ? "border-[#00e5a0] bg-[#00e5a0]/10" : "border-[#2a2a2a] bg-[#0a0a0a]"
          }`}>
            {isEnv
              ? <Crown className="w-4 h-4 text-[#00e5a0]" />
              : <span className="font-mono text-[11px] text-[#00e5a0]">{initials}</span>}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <p className="font-mono text-xs font-bold text-white truncate">{account.username}</p>
              {account.is_self && (
                <span className="font-mono text-[9px] px-1.5 py-0.5 border border-[#00e5a0]/30 text-[#00e5a0] uppercase tracking-widest">
                  TÚ
                </span>
              )}
            </div>
            <p className="font-mono text-[10px] text-[#555] mt-0.5">
              {isEnv ? "Cuenta raíz del sistema" : `Creado por ${account.created_by || "—"}`}
            </p>
          </div>
        </div>
      </div>

      {/* Origen */}
      <div className="col-span-2 td">
        <span className={`badge ${isEnv ? "badge-amber" : "badge-green"}`}>
          {isEnv ? "RAÍZ · .ENV" : "PANEL"}
        </span>
      </div>

      {/* Estado */}
      <div className="col-span-2 td">
        <div className="flex items-center gap-2">
          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
            account.is_active ? "bg-[#00e5a0]" : "bg-[#444]"
          }`} />
          <span className="font-mono text-[10px] uppercase tracking-widest text-[#999]">
            {account.is_active ? "Activo" : "Inactivo"}
          </span>
        </div>
      </div>

      {/* Creado */}
      <div className="col-span-2 td">
        <span className="font-mono text-[11px] text-[#555]">
          {account.created_at ? new Date(account.created_at).toLocaleDateString("es-CO") : "Siempre"}
        </span>
      </div>

      {/* Acciones */}
      <div className="col-span-2 td">
        {isEnv ? (
          <div className="flex items-center gap-1.5 justify-end text-[#444]">
            <Lock className="w-3 h-3" />
            <span className="font-mono text-[9px] uppercase tracking-widest">Protegida</span>
          </div>
        ) : (
          <div className="flex items-center gap-1 justify-end">
            <button
              onClick={() => onResetPassword(account)}
              className="p-1.5 text-[#888] hover:text-[#00e5a0] transition-colors"
              title="Restablecer contraseña"
            >
              <KeyRound className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onToggle(account)}
              disabled={account.is_self}
              className={`p-1.5 transition-colors disabled:opacity-25 disabled:cursor-not-allowed ${
                account.is_active ? "text-[#888] hover:text-yellow-500" : "text-[#888] hover:text-[#00e5a0]"
              }`}
              title={account.is_self ? "No puedes desactivar tu propia cuenta" : account.is_active ? "Desactivar" : "Activar"}
            >
              <Power className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onRemove(account)}
              disabled={account.is_self}
              className="p-1.5 text-[#888] hover:text-red-500 transition-colors disabled:opacity-25 disabled:cursor-not-allowed"
              title={account.is_self ? "No puedes eliminar tu propia cuenta" : "Eliminar"}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function SuperAdmins() {
  const qc = useQueryClient();
  const [modal, setModal] = useState<ModalState | null>(null);

  const { data: accounts = [], isLoading } = useQuery<SuperAdminAccount[]>({
    queryKey: ["superadmins"],
    queryFn: superAdminsApi.list,
  });

  const create = useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      superAdminsApi.create(username, password),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["superadmins"] });
      setModal(null);
    },
  });

  const resetPassword = useMutation({
    mutationFn: ({ id, password }: { id: number; password: string }) =>
      superAdminsApi.update(id, { password }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["superadmins"] });
      setModal(null);
    },
  });

  const toggle = useMutation({
    mutationFn: (a: SuperAdminAccount) =>
      superAdminsApi.update(a.id as number, { is_active: !a.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["superadmins"] }),
  });

  const remove = useMutation({
    mutationFn: (a: SuperAdminAccount) => superAdminsApi.remove(a.id as number),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["superadmins"] }),
  });

  const activeModalMutation = modal?.mode === "password" ? resetPassword : create;

  const modalError = (() => {
    const err = activeModalMutation.error as { response?: { data?: { detail?: string } } } | null;
    return err?.response?.data?.detail ?? (activeModalMutation.isError ? "No se pudo guardar la cuenta." : "");
  })();

  const pageError = (() => {
    const err = (toggle.error ?? remove.error) as { response?: { data?: { detail?: string } } } | null;
    return err?.response?.data?.detail ?? (toggle.isError || remove.isError ? "No se pudo completar la operación." : "");
  })();

  const panelAccounts = accounts.filter((a) => a.source === "panel");
  const activeCount = accounts.filter((a) => a.is_active).length;

  const openCreate = () => {
    create.reset();
    setModal({ mode: "create" });
  };

  const openReset = (account: SuperAdminAccount) => {
    resetPassword.reset();
    setModal({ mode: "password", account });
  };

  const handleSubmit = (data: { username?: string; password: string }) => {
    if (!modal) return;
    if (modal.mode === "create") {
      create.mutate({ username: data.username ?? "", password: data.password });
    } else if (modal.account?.id != null) {
      resetPassword.mutate({ id: modal.account.id, password: data.password });
    }
  };

  return (
    <div>
      <PageHeader
        tag="SEGURIDAD · ACCESO TOTAL"
        title="Super Admins"
        description="Cuentas con control absoluto sobre todos los clientes del sistema"
        action={
          <button className="btn-primary flex items-center gap-2" onClick={openCreate}>
            <Plus className="w-3.5 h-3.5" />
            NUEVO SUPER ADMIN
          </button>
        }
      />

      <div className="px-8 py-8 space-y-6">

        {/* Hero de seguridad */}
        <div className="relative overflow-hidden border border-[#00e5a0]/20 bg-[#080b0a]">
          <div
            className="pointer-events-none absolute inset-0 opacity-[0.35]"
            style={{
              backgroundImage:
                "linear-gradient(to right, #00e5a012 1px, transparent 1px), linear-gradient(to bottom, #00e5a012 1px, transparent 1px)",
              backgroundSize: "28px 28px",
              maskImage: "radial-gradient(ellipse at 20% 0%, black 10%, transparent 70%)",
              WebkitMaskImage: "radial-gradient(ellipse at 20% 0%, black 10%, transparent 70%)",
            }}
          />
          <div className="relative flex flex-col lg:flex-row lg:items-center justify-between gap-6 px-6 py-6">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 border border-[#00e5a0]/40 bg-[#00e5a0]/10 flex items-center justify-center flex-shrink-0">
                <ShieldCheck className="w-6 h-6 text-[#00e5a0]" />
              </div>
              <div className="max-w-xl">
                <p className="section-tag mb-1.5">// ZONA RESTRINGIDA</p>
                <h2 className="text-base font-bold text-white tracking-tight">
                  Acceso raíz a todo el sistema
                </h2>
                <p className="text-xs text-[#888] mt-1.5 leading-relaxed">
                  Estas cuentas pueden ver y gestionar todos los clientes, sus admins,
                  el agente y la configuración global. Solo el super admin raíz
                  (<span className="font-mono text-[#00e5a0]">.env</span>) y los super admins
                  de panel pueden entrar aquí.
                </p>
              </div>
            </div>

            <div className="flex gap-2 flex-shrink-0">
              <div className="border border-[#1a1a1a] bg-[#050505] px-4 py-3 min-w-[92px]">
                <p className="font-mono text-[9px] uppercase tracking-widest text-[#555]">Cuentas</p>
                <p className="font-mono text-xl font-bold text-white mt-1">{accounts.length}</p>
              </div>
              <div className="border border-[#1a1a1a] bg-[#050505] px-4 py-3 min-w-[92px]">
                <p className="font-mono text-[9px] uppercase tracking-widest text-[#555]">Activas</p>
                <p className="font-mono text-xl font-bold text-[#00e5a0] mt-1">{activeCount}</p>
              </div>
              <div className="border border-[#1a1a1a] bg-[#050505] px-4 py-3 min-w-[92px]">
                <p className="font-mono text-[9px] uppercase tracking-widest text-[#555]">De panel</p>
                <p className="font-mono text-xl font-bold text-white mt-1">{panelAccounts.length}</p>
              </div>
            </div>
          </div>
        </div>

        {pageError && (
          <div className="px-4 py-3 border border-red-900 bg-red-950/30 font-mono text-xs text-red-400">
            {pageError}
          </div>
        )}

        {/* Tabla */}
        <div className="border border-[#1a1a1a]">
          <div className="grid grid-cols-12 bg-[#050505] border-b border-[#1a1a1a]">
            <div className="col-span-4 th">Cuenta</div>
            <div className="col-span-2 th">Origen</div>
            <div className="col-span-2 th">Estado</div>
            <div className="col-span-2 th">Alta</div>
            <div className="col-span-2 th text-right">Acciones</div>
          </div>

          {isLoading &&
            Array(3).fill(0).map((_, i) => (
              <div key={i} className="h-16 border-b border-[#111] animate-pulse" />
            ))}

          {!isLoading &&
            accounts.map((account) => (
              <AccountRow
                key={`${account.source}-${account.id ?? account.username}`}
                account={account}
                onResetPassword={openReset}
                onToggle={(a) => toggle.mutate(a)}
                onRemove={(a) =>
                  window.confirm(`¿Eliminar el super admin "${a.username}"? Esta acción es irreversible.`) &&
                  remove.mutate(a)
                }
              />
            ))}

          {!isLoading && accounts.length === 0 && (
            <div className="px-5 py-16 text-center">
              <UserCheck className="w-8 h-8 text-[#333] mx-auto mb-3" />
              <p className="font-mono text-xs text-[#888] uppercase tracking-widest">
                Sin cuentas de super admin
              </p>
            </div>
          )}
        </div>

        <p className="font-mono text-[10px] text-[#444] leading-relaxed">
          * La cuenta raíz del sistema vive en las variables de entorno
          (<span className="text-[#666]">ADMIN_USER / ADMIN_PASSWORD</span>) y no se puede
          editar ni eliminar desde el panel.
        </p>

      </div>

      {modal && (
        <SuperAdminModal
          state={modal}
          onClose={() => setModal(null)}
          onSubmit={handleSubmit}
          saving={create.isPending || resetPassword.isPending}
          error={modalError}
        />
      )}
    </div>
  );
}
