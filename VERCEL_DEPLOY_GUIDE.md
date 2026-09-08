# 🌐 Guía de Despliegue en Vercel & Conexión Remota

Esta guía te explica paso a paso cómo subir el servidor a **Vercel** para poder usar la herramienta desde cualquier computadora o teléfono fuera de casa, procesando las auditorías en tu PC local.

---

## 🏗️ Estructura del Proyecto

Tu proyecto ahora incluye la carpeta `vercel/` lista para subir:

```text
h1-checker/
├── vercel/                   ← CARPETA A SUBIR EN VERCEL
│   ├── vercel.json           ← Configuración de rutas serverless
│   ├── package.json          ← Configuración Node.js
│   ├── api/                  ← Handler Relay serverless (index.js)
│   └── public/               ← Frontend (index.html, styles.css, script.js)
├── app.py                    ← Backend local de tu PC
├── local_worker.py           ← Worker puente en tu PC
├── start_app.bat             ← Iniciar servidor Flask local
└── start_remote_worker.bat   ← Iniciar worker remoto en tu PC
```

---

## 🚀 Opción 1: Desplegar en Vercel desde GitHub (RECOMENDADO)

### Paso 1: Subir la carpeta a GitHub
1. Crea un repositorio en GitHub (ej: `h1-checker-vercel`).
2. Sube el contenido de la carpeta `vercel/` a la raíz de ese repositorio.

### Paso 2: Importar en Vercel
1. Ve a [https://vercel.com](https://vercel.com) e inicia sesión con tu cuenta.
2. Haz clic en **"Add New Project"** > **"Import Git Repository"**.
3. Selecciona tu repositorio `h1-checker-vercel`.
4. Haz clic en **"Deploy"**.
5. ¡Listo! Vercel te dará una URL pública (ejemplo: `https://mi-h1-checker.vercel.app`).

---

## ⚡ Opción 2: Desplegar en Vercel desde la Terminal (Vercel CLI)

Si prefieres desplegar directamente desde tu PC sin usar GitHub:

1. Abre la terminal en la carpeta `vercel/`:
   ```cmd
   cd vercel
   ```
2. Instala Vercel CLI (si no lo tienes):
   ```cmd
   npm install -g vercel
   ```
3. Ejecuta el comando de despliegue:
   ```cmd
   vercel --prod
   ```
4. Sigue las instrucciones en pantalla. Obtendrás tu URL pública al finalizar.

---

## 💻 Paso 3: Conectar tu PC de Casa (Worker Local)

Para que tu PC de casa escuche las peticiones de Vercel y procese las auditorías:

1. Abre el archivo **`.env`** en la carpeta principal de tu proyecto y añade tu URL de Vercel:
   ```env
   VERCEL_URL=https://mi-h1-checker.vercel.app
   WORKER_SECRET_KEY=h1-checker-secret-key-2026
   ```
2. Inicia el backend de la app en tu PC de casa ejecutando:
   - **`start_app.bat`** (en una ventana de terminal).
3. Inicia el worker remoto ejecutando:
   - **`start_remote_worker.bat`** (en otra ventana de terminal).

---

## 📱 ¿Cómo usar la herramienta desde otra PC o teléfono?

1. Desde **cualquier otra PC o smartphone** en cualquier parte del mundo, abre el navegador e ingresa a tu enlace de Vercel:
   `https://mi-h1-checker.vercel.app`
2. Escribe cualquier URL que desees auditar y haz clic en **"Scan Quality"**.
3. El frontend de Vercel enviará el trabajo a la cola. Tu PC de casa lo recibirá, ejecutará el escaneo completo (Selenium + NLP) y devolverá los resultados a la pantalla de la PC remota.
