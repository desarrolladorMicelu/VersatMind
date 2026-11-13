#!/bin/bash
# build_macos.sh — Build MIND Recorder .app bundle for macOS
# Ejecutar en una Mac con Python 3 instalado.
#
# 1. (opcional) Crear y activar virtualenv
#    python3 -m venv venv && source venv/bin/activate
#
# 2. Instalar dependencias
#    pip install soundcard numpy requests sounddevice pyinstaller

set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="MIND Recorder"
ENTITLEMENTS="entitlements.plist"

# 3. Generar icono básico (cuadrado verde con "M" en ASCII → icns)
#    Si tienes un .icns real, cópialo como icon.icns
if [ ! -f "icon.icns" ]; then
    echo "⚠ No se encontró icon.icns — se generará un icono placeholder."
    # Crear un icono PNG básico con Python (requiere Pillow o se omite)
fi

# 4. Limpiar build anterior
rm -rf build dist __pycache__ *.spec

# 5. Empaquetar con PyInstaller
echo "🔨 Ejecutando PyInstaller..."
pyinstaller --onefile --windowed \
    --name "$APP_NAME" \
    --collect-all soundcard \
    --collect-all numpy \
    --osx-entitlements-file "$ENTITLEMENTS" \
    --target-arch universal2 \
    mind_desktop.py

# 6. Firmar el .app (sin Developer ID se puede omitir, pero macOS mostrará advertencia)
SIGN_IDENTITY=${CODESIGN_IDENTITY:-"-"}
codesign --deep --force --sign "$SIGN_IDENTITY" "dist/$APP_NAME.app" 2>/dev/null || true

echo ""
echo "✅ Build completado: dist/$APP_NAME.app"
echo ""
echo "Para distribuir sin advertencia de desarrollador no identificado, necesitas:"
echo "  1. Apple Developer Program ($99/año)"
echo "  2. Firma: codesign --deep --force --sign \"Developer ID Application: Tu Nombre\" \"dist/$APP_NAME.app\""
echo "  3. Notarización: xcrun notarytool submit ..."
echo ""
echo "Para pruebas locales: Botón derecho sobre el .app → Abrir → Abrir de todas formas."
echo ""
echo "📌 Requisito para loopback en macOS:"
echo "  brew install blackhole-2ch"
echo "  Luego en Zoom/Meet/Teams configura la salida de audio hacia BlackHole."
