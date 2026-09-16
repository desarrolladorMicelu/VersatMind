"""
Script de configuración inicial de la base de datos.
Crea los roles, permisos y un usuario administrador de prueba.

Uso:
    python scripts/seed_initial_data.py

Variables de entorno requeridas:
    DATABASE_URL_SYNC — URL de PostgreSQL sync (postgresql://user:pass@host:5432/db)
    ADMIN_CHAT_ID     — Tu chat_id de Telegram (obtenlo enviando /start a @userinfobot)
    ADMIN_USER_ID     — Tu user_id de Telegram

Ejemplo:
    DATABASE_URL_SYNC=postgresql://mind:password@localhost:5432/mind_db \
    ADMIN_CHAT_ID=123456789 \
    ADMIN_USER_ID=123456789 \
    python scripts/seed_initial_data.py
"""
from __future__ import annotations

import os
import sys

# Asegurar que el workspace root está en el path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main() -> None:
    database_url = os.environ.get("DATABASE_URL_SYNC")
    if not database_url:
        print("ERROR: Falta la variable de entorno DATABASE_URL_SYNC", file=sys.stderr)
        sys.exit(1)

    admin_chat_id = os.environ.get("ADMIN_CHAT_ID")
    admin_user_id = os.environ.get("ADMIN_USER_ID")
    if not admin_chat_id or not admin_user_id:
        print("ERROR: Faltan ADMIN_CHAT_ID y/o ADMIN_USER_ID", file=sys.stderr)
        sys.exit(1)

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    engine = create_engine(database_url)

    with Session(engine) as session:
        # Verificar que las tablas existen
        try:
            session.execute(text("SELECT 1 FROM roles LIMIT 1"))
        except Exception:
            print("ERROR: Las tablas no existen. Ejecuta primero: alembic upgrade head", file=sys.stderr)
            sys.exit(1)

        # ---- Roles ----
        existing_roles = {
            row[0]: row[1]
            for row in session.execute(text("SELECT name, id FROM roles")).fetchall()
        }

        roles_to_create = [
            ("admin", "Administrador con acceso completo"),
            ("board_member", "Miembro de junta directiva"),
            ("viewer", "Solo lectura de informes"),
        ]

        role_ids: dict[str, int] = dict(existing_roles)
        for role_name, role_desc in roles_to_create:
            if role_name not in existing_roles:
                result = session.execute(
                    text("INSERT INTO roles (name, description) VALUES (:n, :d) RETURNING id"),
                    {"n": role_name, "d": role_desc},
                )
                role_ids[role_name] = result.scalar()
                print(f"  ✓ Rol creado: {role_name}")
            else:
                print(f"  · Rol ya existe: {role_name}")

        # ---- Permisos por rol ----
        all_permissions = [
            "READ_SALES", "READ_KPI", "READ_FINANCE",
            "GENERATE_REPORT", "MANAGE_TASKS",
        ]
        role_permissions = {
            "admin": all_permissions,
            "board_member": all_permissions,
            "viewer": ["READ_SALES", "READ_KPI", "READ_FINANCE", "GENERATE_REPORT"],
        }

        for role_name, perms in role_permissions.items():
            role_id = role_ids.get(role_name)
            if role_id is None:
                continue
            for perm in perms:
                existing = session.execute(
                    text("SELECT 1 FROM role_permissions WHERE role_id=:r AND permission_name=:p"),
                    {"r": role_id, "p": perm},
                ).fetchone()
                if not existing:
                    session.execute(
                        text("INSERT INTO role_permissions (role_id, permission_name) VALUES (:r, :p)"),
                        {"r": role_id, "p": perm},
                    )

        print(f"  ✓ Permisos configurados para todos los roles")

        # ---- Usuario admin inicial ----
        chat_id = int(admin_chat_id)
        user_id = int(admin_user_id)
        admin_role_id = role_ids.get("admin")

        existing_user = session.execute(
            text("SELECT 1 FROM users WHERE chat_id = :c"),
            {"c": chat_id},
        ).fetchone()

        if not existing_user:
            session.execute(
                text("""
                    INSERT INTO users (chat_id, user_id, username, role_id, is_active)
                    VALUES (:chat_id, :user_id, :username, :role_id, true)
                """),
                {
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "username": "admin",
                    "role_id": admin_role_id,
                },
            )
            print(f"  ✓ Usuario admin creado: chat_id={chat_id}")
        else:
            print(f"  · Usuario ya existe: chat_id={chat_id}")

        session.commit()

    print("\n✅ Seed completado. El sistema está listo para usar.")
    print(f"\nPróximos pasos:")
    print(f"  1. Configura tu .env con las variables de entorno")
    print(f"  2. Ejecuta: docker-compose up")
    print(f"  3. Envía un mensaje a tu bot de Telegram")


if __name__ == "__main__":
    main()
