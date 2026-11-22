# Despliegue de Benter Perú

## Streamlit Community Cloud

1. Crea un repositorio **privado** de GitHub para el despliegue. Sube la rama
   `master` con una copia revisada del código. El repositorio puede seguir
   siendo privado aunque la aplicación se configure como pública.

   ```sh
   git remote add cloud https://github.com/TU_USUARIO/TU_REPOSITORIO.git
   git push cloud master
   ```

2. Prepara una copia de solo lectura de la base SQLite con el esquema migrado
   y los datos que autorizas mostrar. El checkout que recibe Streamlit debe
   contener también el artefacto de ensamble y su CSV de entrenamiento, con
   los hashes originales. En el repositorio privado de despliegue, incluye
   solo las copias autorizadas en las rutas de la tabla. Las reglas de Git del
   repositorio de trabajo mantienen fuera los datos locales. Antes de agregar
   cada archivo a la copia de despliegue, confirma que puedes compartirlo con
   el proveedor de alojamiento. El CSV táctico es opcional.
3. En [Streamlit Community Cloud](https://share.streamlit.io/), conecta
   GitHub, concede acceso al repositorio y selecciona **Create app**. Usa
   `master` y el archivo principal `src/benter_peru/ui/app.py`. Elige
   **Python 3.12** en **Advanced settings**. Streamlit instala
   `requirements.txt` y `packages.txt` desde la raíz. [Guía oficial de despliegue](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
4. Prueba **Carreras**, **Predicciones** y **Simulación de Ritmo** en la URL
   asignada. Cuando hayas revisado los datos visibles, cambia **Settings →
   Sharing → This app is public and searchable** y abre la URL en una ventana
   privada para verificar que se puede entrar sin iniciar sesión. [Guía oficial de acceso público](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)

| Archivo | Ruta predeterminada desde la raíz | Variable opcional |
|---|---|---|
| SQLite de solo lectura | `var/benter.sqlite3` | `BENTER_DATABASE_PATH` |
| Ensamble validado | `var/ml/real-model/ensemble_model_v1.pkl` | `BENTER_ENSEMBLE_MODEL_PATH` |
| Dataset del ensamble | `var/ml/real-model/dataset_oficial_resultados.csv` | `BENTER_REAL_DATASET_PATH` |
| Estilos y biomecánica (opcional) | `estilos_domingo_2026.csv` | `BENTER_PACE_STYLES_PATH` |

Las rutas relativas de estas variables se resuelven desde la raíz. Si la
base o el ensamble faltan, la app indica qué archivo debe provisionarse.
Si falta el CSV táctico, permite seleccionar estilos manualmente. Provisiona
solo un modelo de confianza que coincida con el SHA-256 validado por el
proyecto. Al actualizar datos, vuelve a desplegar o reinicia la app para que
recargue sus recursos en memoria.

El dashboard es de solo lectura. Las cuotas se introducen en la interfaz y
se usan en memoria. Las tareas de scraping y las migraciones se ejecutan
fuera de Streamlit Cloud. La instalación de la app no requiere descargar
Chromium.

## Túnel temporal desde Windows

Desde la raíz del proyecto, inicia Streamlit con los archivos del fin de semana.

```powershell
$env:BENTER_DATABASE_PATH = 'var/official-2026-11-21.sqlite3'
$env:BENTER_PACE_STYLES_PATH = 'estilos_domingo_2026.csv'
python -m streamlit run src/benter_peru/ui/app.py --server.address 127.0.0.1 --server.port 8501
```

En otra terminal, ejecuta `cloudflared tunnel --url http://localhost:8501`.
Abre la URL `trycloudflare.com` de la salida. Quien tenga el enlace puede
entrar. Para cerrarlo, pulsa **Ctrl+C** en la terminal de `cloudflared`, o
ejecuta `Stop-Process -Id <PID-de-cloudflared>` si se inició en segundo
plano. [Documentación de Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
