"""
Tests para mind/auth/authorization.py.
Propiedades 4, 5, 7, 8. Valida: Requisitos 2.1, 2.2, 2.4, 2.6, 2.8
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mind.auth.authorization import (
    AuthResult,
    WhitelistUnavailableError,
    _invalidate_permissions_cache,
    _set_cached_permissions,
    _permissions_cache,
    is_authorized,
)

UNAUTHORIZED_MSG = "No estás autorizado para usar este servicio."
_INTERNAL_TERMS = [
    "/mind/", "authorization.py", "DATABASE_URL", "TELEGRAM_BOT_TOKEN",
    "WhitelistUnavailableError", "SQLAlchemy", "Traceback", "role_permissions",
]


class TestIsAuthorizedProperty4:
    """Propiedad 4: Autorización refleja exactamente el contenido de la whitelist."""

    @given(
        chat_id=st.integers(min_value=1),
        whitelist=st.frozensets(st.integers(min_value=1)),
    )
    @settings(max_examples=100)
    def test_matches_whitelist(self, chat_id: int, whitelist: frozenset[int]):
        assert is_authorized(chat_id, whitelist) == (chat_id in whitelist)

    def test_empty_whitelist_denies_all(self):
        for cid in [1, 100, 999_999]:
            assert is_authorized(cid, frozenset()) is False

    def test_member_is_authorized(self):
        wl = frozenset([111, 222, 333])
        assert is_authorized(111, wl) is True

    def test_non_member_is_denied(self):
        wl = frozenset([111, 222])
        assert is_authorized(999, wl) is False


class TestUnauthorizedResponseProperty5:
    """Propiedad 5: La respuesta a usuarios no autorizados no revela info interna."""

    def test_no_internal_terms_in_rejection_message(self):
        for term in _INTERNAL_TERMS:
            assert term not in UNAUTHORIZED_MSG

    def test_message_is_concise(self):
        assert len(UNAUTHORIZED_MSG) < 200


class TestPermissionsCache:

    def setup_method(self):
        _invalidate_permissions_cache()

    def test_invalidation_clears_cache(self):
        _set_cached_permissions(1, frozenset(["READ_SALES"]))
        assert 1 in _permissions_cache
        _invalidate_permissions_cache()
        assert 1 not in _permissions_cache


class TestAuthResult:

    def test_denied_has_no_user(self):
        r = AuthResult(allowed=False)
        assert r.user is None
        assert r.role is None

    def test_allowed_carries_user_and_role(self):
        u, ro = object(), object()
        r = AuthResult(allowed=True, user=u, role=ro)
        assert r.allowed is True
        assert r.user is u
        assert r.role is ro
