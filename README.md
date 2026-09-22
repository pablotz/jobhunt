# JobHunt MX

Buscador de vacantes en **Indeed, LinkedIn y Google Jobs (México)** que ordena los resultados poniendo **primero las vacantes que publican sueldo** y califica qué tan bien encajan con tu CV usando **Jev** (TypeSafe AI).

## Instalación

```bash
git clone https://github.com/pablotz/jobhunt.git
cd jobhunt
python3 -m venv .venv      # Ubuntu/Debian: si falla, primero `sudo apt install python3-venv`
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

```bash
export TYPESAFE_API_KEY=tu_key   # gratis en https://console.typesafe.ai
streamlit run app.py
```
(o también crea un archivo `.env` en la raíz con `TYPESAFE_API_KEY=tu_key`; la app lo carga sola).

1. **Sube tu CV (PDF)** en la barra lateral — crea tu perfil automáticamente.
2. Pulsa **🔄 Actualizar vacantes** — busca y puntúa (tarda unos minutos).

Sin `TYPESAFE_API_KEY` la app funciona igual, pero el ranking usa solo palabras clave
(con la key, Jev califica fit de skills y seniority por vacante).

Cada persona que use la app sube su propio CV; los puntajes se guardan por perfil.

## Configuración (`config.py`)

| Opción | Qué hace |
|---|---|
| `CITY` | Ciudad para vacantes presenciales/híbridas (además de remotas) |
| `SEARCH_TERMS` | Puestos a buscar |
| `JEV_MAX_JOBS` | Vacantes que Jev califica por corrida (controla costo) |
| `VOCAB` | Vocabulario técnico para el pre-filtro de palabras clave |

## Datos

Todo queda local: `jobs.db` (vacantes) y `profiles/` (CVs en texto) están en `.gitignore`.
