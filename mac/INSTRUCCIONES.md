# 🍎 MIND Recorder para macOS

## 📋 ¿Qué es esto?

Es el asistente de escritorio de **MIND** para macOS. Graba el audio de las reuniones de Zoom/Google Meet/Teams junto con tu micrófono, lo sube al servidor de MIND y allá se transcribe con identificación de hablantes y se genera un resumen automático.

---

## 🧭 Antes de empezar

Necesitas:

1. ✅ Una **Mac** con macOS 12+ (Monterey o superior)
2. ✅ **Conexión a internet**
3. ✅ **Terminal** (app que viene instalada en la Mac)
4. ✅ Ganas de copiar y pegar 5 comandos (yo los escribo aquí, tú solo los pegas)

No necesitas saber programar. Todo está listo para correr.

---

## 🚀 Paso a paso

### Paso 1 — Abrir la Terminal

1. Presiona `⌘ + Espacio` (Command + Barra espaciadora) para abrir **Spotlight**
2. Escribe **Terminal** y presiona Enter
3. Aparece una ventana blanca con texto. Ahí trabajaremos.

---

### Paso 2 — Copiar los archivos en tu Mac

> Tu jefe te pasó una carpeta llamada `mac/` con estos archivos dentro:
> - `mind_desktop.py`
> - `build_macos.sh`
> - `entitlements.plist`
> - `INSTRUCCIONES.md` (este archivo)

1. **Copia la carpeta `mac/` al Escritorio de tu Mac**
   - Con USB, AirDrop, Google Drive, etc.
   - Debe quedar así: `~/Desktop/mac/`

---

### Paso 3 — Instalar las herramientas necesarias

Pega **un comando a la vez** en la Terminal y presiona Enter después de cada uno.

#### 3.1 — Instalar Homebrew (un gestor de instalaciones)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

- Te va a pedir tu **contraseña de la Mac** (la misma que usas para desbloquearla).
- Escribes la contraseña (no se ve mientras escribes, es normal) y presionas Enter.
- Espera ~2-3 minutos a que termine.

#### 3.2 — Instalar BlackHole (para escuchar el audio del sistema)

```bash
brew install blackhole-2ch
```

- Esto permite que el programa capture el audio que sale de las reuniones (Zoom, Meet, Teams).
- Termina en segundos.

#### 3.3 — Instalar Python y las librerías necesarias

```bash
brew install python@3.12
```

```bash
pip3 install soundcard numpy requests sounddevice pyinstaller
```

- Puede tardar un par de minutos.
- Cuando termine, no mostrará errores en rojo.

---

### Paso 4 — Ir a la carpeta del proyecto

```bash
cd ~/Desktop/mac
```

---

### Paso 5 — Dar permisos de ejecución al script

```bash
chmod +x build_macos.sh
```

---

### Paso 6 — Ejecutar el build del programa

```bash
./build_macos.sh
```

Esto **genera el programa**. Verás muchos mensajes en blanco y algunos warnings en amarillo — es normal. Al final (unos 60 segundos) debe aparecer:

```
✅ Build completado: dist/MIND Recorder.app
```

---

## 🎉 Ya tienes la app

El programa está en:

```
~/Desktop/mac/dist/MIND Recorder.app
```

Puedes copiarlo a la carpeta de **Aplicaciones** si quieres.

---

### ▶️ Cómo abrirlo la primera vez (importante)

macOS bloqueará apps de desarrolladores no verificados. Para abrirlo:

1. **Botón derecho** sobre `MIND Recorder.app`
2. Selecciona **Abrir**
3. Te saldrá un mensaje como *"MIND Recorder proviene de un desarrollador no identificado"*
4. Haz clic en **Abrir de todas formas**
5. Te pedirá permiso para usar el **micrófono** — aceptas
6. ¡Listo! La app se abre.

Las siguientes veces bastará con doble clic normal.

---

### 🔧 Cómo preparar una reunión de Zoom/Meet/Teams con BlackHole

Para que el programa pueda escuchar a los participantes remotos:

1. Abre **Audio MIDI Setup** (App nativa de macOS: `⌘+Espacio` → escribe "Audio MIDI")
2. No necesitas hacer nada allí si BlackHole se instaló bien
3. Abre Zoom / Google Meet / Microsoft Teams
4. Ve a **Preferencias** → **Audio**
5. En **Altavoz / Salida** selecciona **BlackHole 2ch**
6. La reunión ahora se escuchará a través de BlackHole, no por los parlantes
7. El MIND Recorder capturará el audio desde BlackHole + tu micrófono
8. Sigue hablando normal tú — tu micrófono sigue activo

> ⚠️ Si seleccionas BlackHole como salida, **no oirás el audio por los parlantes**. Para escuchar, ponte audífonos o configura un Aggregate Device en Audio MIDI (más avanzado).

---

### ✅ Verificar que BlackHole funciona

```bash
python3 -c "
import soundcard as sc
loops = [m.name for m in sc.all_microphones(include_loopback=True) if getattr(m,'isloopback',False)]
print('Loopbacks disponibles:', loops)
if loops:
    print('? BlackHole instalado correctamente.')
else:
    print('? BlackHole NO detectado. Revisa: brew install blackhole-2ch')
"
```

---

## ❓ Problemas comunes

| Problema | Solución |
|---|---|
| **"pyinstaller: command not found"** | Ejecuta `pip3 install pyinstaller` y luego `./build_macos.sh` |
| **"soundcard: no module named"** | Ejecuta `pip3 install soundcard numpy requests` |
| **La app no captura el audio del sistema** | BlackHole no está instalado o no configurado en la app de reunión. Verifica con el comando de arriba. |
| **"desarrollador no identificado"** | Sigue los pasos de "Cómo abrirlo la primera vez" (botón derecho → Abrir) |
| **El programa no graba el mic** | Ve a Preferencias del Sistema → Privacidad → Micrófono → activa MIND Recorder |
| **La app se abre y se cierra inmediatamente** | Abre la Terminal, ejecuta: `open ~/Desktop/mac/dist/MIND\ Recorder.app` y mira qué error muestra |

---

## 📦 Entregables

Después de completar estos pasos, tienes:

- `~/Desktop/mac/dist/MIND Recorder.app` — **el programa** (puedes copiarlo a cualquier Mac)
- `~/Desktop/mac/mind_desktop.py` — el código fuente (no lo borres)

Para actualizar el programa, solo reemplaza `mind_desktop.py` con la versión nueva y vuelve a ejecutar `./build_macos.sh`.
