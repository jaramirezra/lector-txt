# Lector TXT

Aplicación web local para abrir **PDF** y **DOCX**, revisar su contenido en un
visualizador y quitar lo que no quieres antes de descargar un **TXT**.

El documento original nunca se modifica. Cada bloque de contenido (título,
párrafo, lista, tabla, encabezado o pie) se puede incluir o excluir con un clic,
desde el documento o desde la lista lateral.

## Funciones

- PDF con texto, PDF solo con contraseña de propietario y **PDF protegido con
  contraseña de apertura** (se pide en una ventana y se usa solo en memoria).
- DOCX normal y **DOCX cifrado con contraseña**.
- Visualizador de las páginas reales del PDF con zonas clicables.
- Vista de lectura del DOCX generada desde los mismos bloques.
- Lista sincronizada con casillas, búsqueda y edición por bloque.
- Sugerencias de exclusión para encabezados repetidos, pies y números de página.
- Deshacer y rehacer.
- TXT final editable a mano antes de descargarlo.
- Opciones de exportación: separación de párrafos, prefijo de listas, formato de
  tablas, estilo de encabezados, codificación UTF-8/BOM y fin de línea LF/CRLF.
- Todo se procesa en el equipo. No hay servicios externos ni telemetría.

## Arranque rápido con Docker

```bash
cp .env.example .env
docker compose up --build -d
```

Abre <http://127.0.0.1:8000>.

```bash
docker compose logs -f      # ver registros
docker compose down         # detener
docker compose down -v      # detener y borrar documentos temporales
```

El puerto se cambia en `.env`:

```env
LECTOR_PORT=8001
```

o directamente:

```bash
LECTOR_PORT=8001 docker compose up -d
```

El contenedor publica el puerto solo en `127.0.0.1`, así que la aplicación no
queda expuesta a la red local.

## Arranque local (sin Docker)

Requiere Python 3.12 o superior y `python3-venv`.

```bash
./setup.sh
./run.sh
```

Si el puerto está ocupado:

```bash
LECTOR_PORT=8001 ./run.sh
```

## Uso

1. Arrastra un PDF o DOCX, o haz clic en la zona de subida.
2. Si el documento está cifrado, introduce la contraseña en la ventana. La
   contraseña no se guarda en disco ni en los registros.
3. Revisa el documento:
   - Haz clic en un párrafo del documento para excluirlo del TXT.
   - O usa la lista **Bloques** y sus casillas.
   - El botón **Aplicar sugerencias** excluye encabezados y números de página
     detectados.
4. Opcionalmente edita el **Resultado TXT** a mano o edita un bloque con el
   lápiz.
5. Ajusta las opciones de exportación y pulsa **Exportar TXT**.

Los bloques sugeridos se marcan en ámbar; no se excluyen automáticamente.

## Contraseñas y seguridad

- La contraseña viaja en el cuerpo de un `POST` a la propia aplicación.
- Se mantiene **solo en memoria** mientras dura el trabajo; nunca se escribe en
  el directorio temporal ni en variables de entorno.
- No se genera una copia descifrada del documento en disco.
- Se permiten 5 intentos por documento. Al agotarlos, el archivo temporal se
  borra y hay que subirlo de nuevo.
- Los documentos temporales caducan a la hora y se pueden borrar con
  **Nuevo documento** o al cerrar el contenedor.
- En Docker, Gunicorn usa **un worker con varios hilos** para que el estado del
  desbloqueo viva en un único proceso.

> La extracción se hace en tu equipo. Aun así, respeta los permisos del autor
> del documento cuando reutilices su contenido.

## Configuración

| Variable | Por defecto | Descripción |
|---|---|---|
| `LECTOR_PORT` | `8000` | Puerto del host (Docker y modo local) |
| `LECTOR_HOST` | `127.0.0.1` | Interfaz de escucha en modo local |
| `LECTOR_MAX_FILE_MB` | `30` | Tamaño máximo por archivo |
| `LECTOR_MAX_PAGES` | `300` | Páginas máximas de un PDF |
| `LECTOR_JOB_TTL` | `3600` | Segundos que se conserva un trabajo |
| `LECTOR_MAX_PASSWORD_ATTEMPTS` | `5` | Intentos de contraseña por documento |
| `LECTOR_RENDER_DPI` | `120` | Resolución de las páginas renderizadas |
| `LECTOR_JOBS_DIR` | `/tmp/lector-txt-jobs` | Directorio de trabajos temporales |

## Pruebas

```bash
.venv/bin/python -m pytest -q
```

O dentro de Docker:

```bash
docker build --target test -t lector-txt:test .
docker run --rm lector-txt:test
```

La suite genera sus propios PDF y DOCX de prueba, incluidos archivos cifrados,
por lo que no hay binarios opacos en el repositorio.

## Estructura

```
app.py                 Rutas Flask y API
lector/
  extract.py           Detección de tipo y despacho
  pdf.py               Texto, coordenadas, render y rotación
  docx.py              Párrafos, estilos, listas, tablas y vista previa
  security.py          Cifrado, contraseñas e intentos
  filters.py           Sugerencias de encabezados, pies y páginas
  export.py            Bloques → TXT
  jobs.py              Trabajos temporales con TTL
  models.py            Modelos compartidos
templates/index.html   Interfaz
static/style.css       Estilos (claro/oscuro, responsive)
static/app.js          Estado, overlays, historial y exportación
tests/                 Pruebas y fixtures generadas
```

## Limitaciones conocidas

- Los **PDF escaneados** no tienen capa de texto. La app lo avisa; haría falta
  OCR (por ejemplo Tesseract) para convertirlos.
- Los `.doc` antiguos, `.odt` y `.rtf` no están soportados. Convierte el archivo
  a DOCX o PDF desde tu editor.
- En DOCX, el número de página no existe como bloque porque Word lo calcula al
  maquetar; no se incluye en el TXT.
- Los PDF con varias columnas pueden ordenar algún bloque de forma imperfecta;
  se puede corregir editando el bloque o el resultado.
- Las imágenes y los formatos visuales no forman parte del TXT.
