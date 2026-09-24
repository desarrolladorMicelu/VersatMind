"""
Tests unitarios para el módulo de Google Sheets.
Cubre: _extract_spreadsheet_id, _validate_conf, filtros, límites,
headers duplicados, consultar_sheet sin config.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mind.data.sheets.google_sheets import (
    ExternalSheetsError,
    _extract_spreadsheet_id,
    _validate_conf,
    MAX_ROWS,
)


class TestExtractSpreadsheetId:
    def test_modern_url(self):
        assert _extract_spreadsheet_id(
            "https://docs.google.com/spreadsheets/d/ABC123def456/edit#gid=0"
        ) == "ABC123def456"

    def test_url_with_gid(self):
        assert _extract_spreadsheet_id(
            "https://docs.google.com/spreadsheets/d/XYZ789/edit?gid=123"
        ) == "XYZ789"

    def test_old_format_with_key(self):
        assert _extract_spreadsheet_id(
            "https://docs.google.com/spreadsheets?key=MyKeyValue"
        ) == "MyKeyValue"

    def test_plain_id(self):
        assert _extract_spreadsheet_id("ABC123def") == "ABC123def"

    def test_invalid_url_raises(self):
        with pytest.raises(ExternalSheetsError, match="No se pudo extraer"):
            _extract_spreadsheet_id("not-a-valid-url!!!")

    def test_empty_raises(self):
        with pytest.raises(ExternalSheetsError, match="vacío"):
            _extract_spreadsheet_id("")


class TestValidateConf:
    def test_empty_conf_raises(self):
        with pytest.raises(ExternalSheetsError, match="No hay Google Sheets configurado"):
            _validate_conf({})

    def test_missing_sid_raises(self):
        with pytest.raises(ExternalSheetsError, match="spreadsheet_id"):
            _validate_conf({"credentials": {"type": "service_account"}})

    def test_missing_credentials_raises(self):
        with pytest.raises(ExternalSheetsError, match="Faltan las credenciales"):
            _validate_conf({"spreadsheet_id": "ABC"})

    def test_incomplete_credentials_raises(self):
        conf = {
            "spreadsheet_id": "ABC",
            "credentials": {"type": "service_account", "project_id": "proj"},
        }
        with pytest.raises(ExternalSheetsError, match="Credenciales de Google incompletas"):
            _validate_conf(conf)

    def test_wrong_type_raises(self):
        conf = {
            "spreadsheet_id": "ABC",
            "credentials": {
                "type": "authorized_user",
                "project_id": "p", "private_key": "k",
                "client_email": "e", "token_uri": "t",
            },
        }
        with pytest.raises(ExternalSheetsError, match="Tipo de credencial inválido"):
            _validate_conf(conf)

    def test_valid_conf(self):
        conf = {
            "spreadsheet_id": "ABC",
            "credentials": {
                "type": "service_account",
                "project_id": "proj",
                "private_key": "-----BEGIN PRIVATE KEY-----\nMII\n-----END PRIVATE KEY-----\n",
                "client_email": "foo@bar.iam.gserviceaccount.com",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        }
        assert _validate_conf(conf) is conf


class TestConsultarSheet:
    """Pruebas de la herramienta consultar_sheet sin conexión real."""

    @pytest.mark.asyncio
    async def test_no_sheets_configured(self):
        from mind.agent.tools.sheets_tool import consultar_sheet

        with patch("mind.tenants.context.get_tenant") as mock_get:
            mock_tenant = MagicMock()
            mock_tenant.external_sheets = None
            mock_get.return_value = mock_tenant

            result = await consultar_sheet(hoja="Clientes")
            assert result["error"] is True
            assert "No hay Google Sheets configurado" in result["mensaje"]

    @pytest.mark.asyncio
    async def test_invalid_limite_type(self):
        from mind.agent.tools.sheets_tool import consultar_sheet

        with patch("mind.tenants.context.get_tenant") as mock_get:
            mock_tenant = MagicMock()
            mock_tenant.external_sheets = {"spreadsheet_id": "ABC"}
            mock_get.return_value = mock_tenant

            result = await consultar_sheet(hoja="Clientes", limite="abc")
            assert result["error"] is True
            assert "debe ser un número entero" in result["mensaje"]

    @pytest.mark.asyncio
    async def test_limite_below_one(self):
        from mind.agent.tools.sheets_tool import consultar_sheet

        with patch("mind.tenants.context.get_tenant") as mock_get:
            mock_tenant = MagicMock()
            mock_tenant.external_sheets = {"spreadsheet_id": "ABC"}
            mock_get.return_value = mock_tenant

            result = await consultar_sheet(hoja="Clientes", limite=0)
            assert result["error"] is True
            assert "mayor o igual a 1" in result["mensaje"]

    @pytest.mark.asyncio
    async def test_invalid_filtros_type(self):
        from mind.agent.tools.sheets_tool import consultar_sheet

        with patch("mind.tenants.context.get_tenant") as mock_get:
            mock_tenant = MagicMock()
            mock_tenant.external_sheets = {"spreadsheet_id": "ABC"}
            mock_get.return_value = mock_tenant

            result = await consultar_sheet(hoja="Clientes", filtros="not_a_dict")
            assert result["error"] is True
            assert "debe ser un diccionario" in result["mensaje"]

    @pytest.mark.asyncio
    async def test_sheet_not_found(self):
        from mind.agent.tools.sheets_tool import consultar_sheet

        with patch("mind.tenants.context.get_tenant") as mock_get, \
             patch("mind.data.sheets.google_sheets.read_sheet") as mock_read:
            mock_tenant = MagicMock()
            mock_tenant.external_sheets = {"spreadsheet_id": "ABC", "credentials": {"type": "service_account"}}
            mock_tenant.slug = "test_tenant"
            mock_get.return_value = mock_tenant
            mock_read.side_effect = ExternalSheetsError("Hoja 'Inexistente' no encontrada.")

            result = await consultar_sheet(hoja="Inexistente")
            assert result["error"] is True
            assert "no encontrada" in result["mensaje"]

    @pytest.mark.asyncio
    async def test_limite_capped_at_max_rows(self):
        from mind.agent.tools.sheets_tool import consultar_sheet

        with patch("mind.tenants.context.get_tenant") as mock_get, \
             patch("mind.data.sheets.google_sheets.read_sheet") as mock_read:
            mock_tenant = MagicMock()
            mock_tenant.external_sheets = {"spreadsheet_id": "ABC", "credentials": {"type": "service_account"}}
            mock_tenant.slug = "test_tenant"
            mock_get.return_value = mock_tenant
            mock_read.return_value = [{"col": "val"}] * MAX_ROWS

            result = await consultar_sheet(hoja="Data", limite=99999)
            assert result["error"] is False
            assert result["row_count"] <= MAX_ROWS


class TestMaxRowsConstant:
    def test_max_rows_is_5000(self):
        assert MAX_ROWS == 5000