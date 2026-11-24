# AppleVision Chile
Sistema inteligente de clasificación y conteo de manzanas para plantas de embalaje frutícola.
Proyecto MLY1101 — Machine Learning | DUOC UC

El proyecto tiene tres partes:
- **Modelo de visión:** detector YOLO entrenado que cuenta y clasifica manzanas en foto, video o cámara.
- **App de escritorio** para la estación de la línea (`iniciar.bat`).
- **Plataforma web con roles** que implementa el [modelo de negocio](MODELO_NEGOCIO.md): el packing analiza cada lote, el jefe de planta lo certifica, y el productor y la exportadora ven el resultado (`iniciar_web.bat`).

## Inicio rápido
Con el entorno ya instalado (ver [Instalación](#instalación)):

| Quiero… | Cómo |
|---|---|
| Usar la app de escritorio | Doble clic en `iniciar.bat` |
| Abrir la plataforma web | Doble clic en `iniciar_web.bat` y entrar a http://127.0.0.1:5000 |
| Contar las manzanas de una foto | `python -m src.vision.detector --modelo models/best.pt --foto ruta/foto.jpg` |
| Medir el conteo del modelo | `python -m src.vision.validar_fotos --split test` |
| Correr las pruebas | `python -m unittest discover -s tests -v` |

Los comandos `python -m …` suponen el entorno activado (`.venv\Scripts\activate`). Sin activarlo, usa `.venv\Scripts\python.exe` en lugar de `python`.

## Novedades (noviembre 2026)
- **Modelo de negocio** en [MODELO_NEGOCIO.md](MODELO_NEGOCIO.md): servicio por suscripción para packings, productores y exportadoras.
- **Plataforma web con 5 roles** en `src/web/`: recepción de lotes, análisis en segundo plano con el mismo detector, validación con conteo manual, certificados verificables, planes y cuotas. Ver [Plataforma web con roles](#plataforma-web-con-roles).
- **Detector:** `procesar()` acepta `al_frame` (avance por frame) y guarda en WebM cuando `--guardar` termina en `.webm`, para ver el video en el navegador. El conteo no cambia y la app de escritorio funciona igual.
- **`validar_fotos`:** omite las fotos sin etiqueta en vez de fallar (ver [Datos](#datos)).
- **Video de prueba:** `python -m src.web.demo` arma `reports/cinta_demo.mp4` con los frames de cinta del dataset.
- **Pruebas:** 23 nuevas en `tests/test_web.py` y `tests/test_validar_fotos.py` (29 en total).

## Objetivo del primer paso
Construir un modelo de visión (YOLO) que **detecte y cuente manzanas sueltas** que pasan frente a una cámara, como en una cinta transportadora.

En esta etapa **no se califica** (calibre, color, sana/podrida): solo se identifica cada manzana y se cuenta. La calificación queda para la etapa siguiente, sobre recortes de cada manzana detectada.

## Introducción del caso
Chile exporta manzanas bajo estándares SAG/Asoex. En las plantas de embalaje, la clasificación y el conteo manual generan errores y cuellos de botella.

La idea es automatizarlo con cámara y visión por computador. Las manzanas avanzan por una cinta, el modelo detecta cada una, y un contador suma las que cruzan el campo de visión. Después, cada detección se recorta y se califica.

Un primer dataset de huerto (fotos de dron) se descartó porque no coincide con el escenario real: ver [Datos](#datos).

## Modelo de negocio
AppleVision se ofrece como un **servicio de conteo y calidad certificada, lote por lote**: una suscripción (SaaS) con tres tipos de cliente.

| Cliente | Plan | Precio (supuesto, CLP + IVA) |
|---|---|---|
| Planta de embalaje (cliente principal) | Packing | $290.000 al mes por línea, más instalación de $1.500.000 por línea |
| Productor | Básico / Pro | Gratis (10 análisis de foto al mes) / $9.990 al mes |
| Exportadora | Exportadora | $190.000 al mes |

El productor entra gratis porque atrae a los otros dos: ve con evidencia cómo salió cada lote que entregó. El documento completo tiene el lienzo del modelo de negocio, el punto de equilibrio (unas 23 líneas), los riesgos (entre ellos la licencia AGPL-3.0 de YOLO) y los próximos pasos.

## Datos
Se usan dos datasets públicos de Roboflow Universe, en formato **YOLOv8** (una línea por objeto: `clase x y ancho alto`, o polígono). Ambos se unificaron en una sola clase: `apple`.

| | Dataset 1: conveyor_apple_sorting | Dataset 2: apple-sorting |
|---|---|---|
| Link | https://universe.roboflow.com/fruitgradechecking/conveyor_apple_sorting | https://universe.roboflow.com/arfiani-nur-sayidah-9lizr/apple-sorting-2bfhk |
| Tipo de fotos | Frames de un video de manzanas sueltas sobre una cinta industrial | Manzanas apiladas en cajas o montones, con oclusión |
| Imágenes | 61 (43 train / 12 valid / 6 test) | 697 (489 / 178 / 30), versión 2 |
| Anotación | Polígonos | Cajas |
| Clases originales | `apple`, `apple_a` | `apple`, `damaged_apple` |
| Tamaño | 640×300 | 416×416 (con bordes blancos) |
| Licencia | Public Domain | CC BY 4.0 (dar crédito al autor) |

**Limitaciones conocidas**
- Dataset 1: todos los frames salen de un solo video, así que son muy parecidos entre sí. Tiene marca de agua (`clideo.com`) y desenfoque por movimiento.
- Dataset 2: no es de cinta; sirve para que el modelo aprenda cómo se ve una manzana.
- Hay muchas más imágenes de montones (697) que de cinta (61). Las métricas de `valid` y `test` reflejan sobre todo montones, no la cinta.

**Fotos sin etiqueta en `images/test`.** El commit `2ed0d44` agregó 58 fotos de Pexels sin etiquetas (8 `prueba_*` y 50 `extra_pexels_*`; créditos en `FUENTES.md` y `FUENTES_ADICIONALES.md`). Sirven para probar el modelo con fotos nuevas, pero no para medirlo:
- `validar_fotos` las omite y avisa cuántas fueron.
- `yolo val split=test` las toma como fotos **sin manzanas**. Las 892 detecciones que el modelo hace en ellas (confianza 0,25) contarían como falsos positivos, frente a solo 168 manzanas etiquetadas en ese split. Conviene moverlas a una carpeta aparte (por ejemplo `images/externas/`) antes de evaluar con YOLO.

**Dataset descartado:** *Apple Detection on split images* (fotos de dron sobre huertos, cortadas en cuadrículas y con casi todo augmentado). Fue eliminado del proyecto.

## Preparación realizada
- Se descargaron ambos datasets con la API de Roboflow.
- Se fusionaron en `images/`. Las imágenes del dataset 2 llevan el prefijo `as_`.
- Se unificaron las clases: `apple_a` y `damaged_apple` pasan a `apple`.
- El dataset 2 original, con sus 2 clases, se conserva en `data/01_raw/apple_sorting_original/`.

Resultado en `images/`: 758 imágenes etiquetadas (train 532 / valid 190 / test 36) y 2.223 manzanas en una clase.

## Estructura del proyecto
```
images/                       dataset actual (YOLO, 1 clase)
  train|valid|test/images     imágenes (test incluye además 58 fotos de Pexels sin etiqueta)
  train|valid|test/labels     etiquetas
  data.yaml                   configuración del dataset
data/
  01_raw/                     datasets originales
    apple_sorting_original/   dataset 2 con sus 2 clases
  02_processed/               salida del pipeline (metricas.csv)
  03_features/                features para ML
src/
  app.py                      app de escritorio (elegir cámara, video o foto)
  vision/                     detector, panel en vivo, calibrador, clasificador, validar_conteo, validar_fotos
  ml/                         features, train, evaluate, optimize
  utils/                      config, s3_helper
  web/                        plataforma web con roles (Flask + SQLite)
    templates/  static/       páginas HTML, estilos y JavaScript
tests/                        pruebas (unittest)
notebooks/                    01_eda, 02_models, 03_optimization
scripts/                      descargar y comprimir dataset
models/                       pesos entrenados (best.pt)
config/bytetrack_apple.yaml   ajustes del tracker
reports/                      informes, gráficos y videos de prueba (no va a git)
web_data/                     base de datos y archivos de la web (se crea al iniciarla; no va a git)
config.yaml                   calibre, HSV, px_por_mm, fuente de video
iniciar.bat                   abre la app de escritorio con doble clic
iniciar_web.bat               abre la plataforma web con doble clic
MODELO_NEGOCIO.md             modelo de negocio que implementa la plataforma web
VALIDACION_FOTOS.md           evaluación del conteo en fotos
ANALISIS_PROYECTO.md          análisis del estado del proyecto
```

## Instalación
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env          # solo si se usará S3 o Roboflow
```
Si usas Roboflow, guarda la clave en `.env` (`ROBOFLOW_API_KEY=...`). No la compartas ni la subas a git.

La plataforma web solo necesita Flask (incluido en `requirements.txt`). La base de datos es SQLite, que viene con Python.

## Uso: app de escritorio y terminal

### App de escritorio (la forma más simple)
Haz doble clic en `iniciar.bat`, o desde la terminal:
```bash
python -m src.app
```

**Desde Git Bash** (abre el panel; ahí eliges el video del computador y se hace el análisis):
```bash
cd ruta/del/proyecto
.venv/Scripts/python.exe -m src.app
```
En el panel: *Video del equipo* → *Elegir archivo…* → *Iniciar conteo*. El modelo analiza el video, cuenta las manzanas y guarda las métricas en `data/02_processed/metricas.csv`.

La pantalla de inicio permite:
1. **Elegir la fuente:** *Cámara conectada* (con número de cámara y botón «Probar cámara»), *Video del equipo* («Elegir archivo…», acepta mp4, avi, mov, mkv y wmv) o *Foto del equipo* («Elegir foto…», acepta jpg, png, bmp y webp).
2. **Ajustar** el nombre del lote, la posición de la línea de conteo, la confianza mínima y si se guarda el video con el panel.
3. **Iniciar conteo:** abre la ventana de video con el panel en vivo. Con la tecla `Q` se termina y se vuelve al dashboard, que muestra el último resultado.

En el video, cada manzana lleva un ID y se **cuenta una sola vez** cuando su centro cruza la línea de conteo (azul, punteada). El panel muestra el total, el desglose por categoría (Buena / Con detalle / No pasa), el calibre configurado y los fps.

Con cámara no hace falta ningún archivo. Con video, el archivo puede estar en cualquier carpeta del equipo.

### Contar las manzanas de una foto
En el dashboard elige *Foto del equipo* → *Elegir foto…* → *Iniciar conteo*. Se abre la foto con una caja por manzana y el panel de conteo (cualquier tecla la cierra). El total y el desglose quedan en *Último resultado*. Si marcas *Guardar el video con el panel*, la imagen queda en `reports/foto_contada.jpg`.

Desde la terminal:
```bash
python -m src.vision.detector --modelo models/best.pt --foto ruta/foto.jpg
python -m src.vision.detector --modelo models/best.pt --foto ruta/foto.jpg --sin-ventana --guardar salida.jpg
```
Cada detección cuenta como una manzana (no hay tracking en una foto). Las manzanas muy tapadas pueden quedar sin contar. En una foto **no se evalúa el calibre**, porque no se conoce la escala px/mm; la categoría sale solo de color, forma y clase YOLO. El total es siempre la suma de Buena + Con detalle + No pasa.

Para probar con fotos que el modelo no vio al entrenar, usa las de Pexels en `images/test/images/` (`prueba_*` y `extra_pexels_*`).

### Línea de comandos
```bash
python -m src.vision.detector --modelo models/best.pt --video ruta.mp4 --lote "Lote 1"
```
Opciones: `--linea 0.8` (posición de la línea, fracción del ancho), `--conf 0.25`, `--guardar salida.mp4`, `--sin-ventana`, `--foto ruta.jpg` (cuenta una sola foto). Sin `--video` ni `--foto` usa la fuente de `config.yaml`. Genera `data/02_processed/metricas.csv`.

- **Usa siempre `--modelo models/best.pt`.** Sin esa opción el detector carga `yolo26n.pt`, el YOLO base que no fue entrenado con nuestras manzanas.
- Si `--guardar` termina en `.webm`, el video se guarda en VP8 y se puede ver en el navegador. Con `.mp4` se usa mp4v, que solo abren los reproductores de escritorio.

### Video de prueba
```bash
python -m src.web.demo                      # crea reports/cinta_demo.mp4
python -m src.vision.detector --modelo models/best.pt --video reports/cinta_demo.mp4 --linea 0.5
```
Arma un video de 61 frames (8 fps) con los frames consecutivos de cinta del dataset 1 (dominio público). Es corto: sirve para ver el tracking funcionando, no para validar el conteo.

### Validar el conteo en fotos
El modo foto usa una sensibilidad inicial de 65 % y NMS IoU 0.35; la sensibilidad se ajusta desde el panel. Para comparar el conteo del modelo con las etiquetas:
```bash
python -m src.vision.validar_fotos --split test --salida reports/validacion_fotos_test.csv
```
Resultado actual en las 36 fotos etiquetadas de test: error absoluto medio de 0,694 manzanas por foto y 20 conteos exactos. Las fotos sin etiqueta se omiten con un aviso. Ver [VALIDACION_FOTOS.md](VALIDACION_FOTOS.md) para resultados, limitaciones, créditos de fotos externas y comandos reproducibles.

La opción **Buscar manzanas pequeñas (solo fotos; tarda más)** analiza zonas solapadas y fusiona las cajas. Se activa manualmente: recupera algunas manzanas omitidas, pero puede aumentar el exceso de conteo. Ver las métricas y el caso de prueba en VALIDACION_FOTOS.md.

### Validar el conteo contra un conteo manual
```bash
python -m src.vision.validar_conteo --video cinta.mp4 --manual 25
python -m src.vision.validar_conteo --video cinta.mp4 --manual 25 --lineas 0.3,0.5,0.8
python -m src.vision.validar_conteo --manifiesto reports/verdad_terreno.csv   # columnas: video,conteo_manual
```
Compara el conteo automático con el manual y muestra el error por video, el error absoluto medio y el desvío global por posición de línea. Escribe `reports/validacion_conteo.csv` y no toca `metricas.csv`. Hay que usar un **video continuo**: una carpeta de frames sueltos no sirve para validar el tracking.

### Entrenar el detector
```bash
yolo detect train data=images/data.yaml model=yolo26n.pt epochs=50 patience=15 imgsz=416 batch=16 device=cpu project=runs name=apple_v1
```
Copiar `weights/best.pt` resultante a `models/best.pt`.

### Configuración
Ajustar `config.yaml` (calibre, HSV, `px_por_mm`, fuente de video, `max_pct_defecto`). **`px_por_mm` hay que calibrarlo** con un objeto de tamaño conocido en cámara: con el valor por defecto las categorías salen casi todas «No pasa», aunque el conteo total es correcto. El semáforo de color está ajustado para manzanas rojas, y la regla de pudrición (`max_pct_defecto`) es exigente con fotos de fruta apilada.

## Plataforma web con roles
Implementa el [modelo de negocio](MODELO_NEGOCIO.md). El packing recibe lotes y los analiza con el mismo detector de la app de escritorio. El jefe de planta los valida y emite un certificado. El productor y la exportadora ven el resultado.

### Iniciar
Haz doble clic en `iniciar_web.bat` (abre el navegador cuando el servidor está listo), o desde la terminal:
```bash
python -m src.web                   # http://127.0.0.1:5000
python -m src.web --reiniciar-demo  # borra los datos de la web y crea la demo de nuevo
python -m src.web --host 0.0.0.0    # para entrar desde un celular en la misma red: http://IP-del-computador:5000
python -m src.web --sin-demo        # sin cuentas ni accesos de demostración
```
Otras opciones: `--port 8000` y `--abrir` (abre el navegador; lo usa `iniciar_web.bat`).

### Roles y cuentas de demostración
En la pantalla de ingreso hay un botón para entrar con cada rol. La contraseña de todas las cuentas es `demo1234`.

| Rol | Cuenta | Qué hace |
|---|---|---|
| Administrador | admin@applevision.demo | Empresas, planes, usuarios, solicitudes de cambio de plan e ingreso mensual recurrente (MRR) |
| Jefe de planta | jefe@losrobles.demo | Panel de planta, valida con conteo manual, aprueba o rechaza lotes, emite certificados y crea cuentas de operadores |
| Operador de línea | operador@losrobles.demo | Recibe lotes y sube la foto o el video de la línea |
| Productor | productor@elmanzano.demo | Ve sus lotes con evidencia y hace análisis rápidos de fotos, con cuota según su plan |
| Exportadora | comercial@andesfruit.demo | Ve los lotes certificados a su nombre, consolidados por variedad y por packing |
| Público (sin cuenta) | — | Verifica un certificado por su código en `/verificar` |

Cada usuario ve solo los datos de su empresa: un productor no ve los lotes de otro, y la exportadora solo ve lotes aprobados a su nombre.

### Flujo de un lote
```
Operador recibe el lote  ->  YOLO lo analiza          ->  Jefe de planta valida   ->  Certificado AV-2026-XXXXXX
y sube foto o video          en segundo plano             y aprueba (conteo           lo ven el productor y la exportadora;
                             (cuenta y clasifica)         manual opcional)            cualquiera lo verifica en /verificar
```
Si el jefe de planta rechaza el lote (con un motivo obligatorio), el operador sube un nuevo análisis y el lote vuelve a revisión.

### Qué incluye
- Recepción de lotes con productor, exportadora, variedad, bins y línea.
- Análisis de foto o video en segundo plano, con barra de avance. El video anotado se ve en el navegador (WebM).
- Evidencia por lote: foto o video anotado, conteo por categoría y porcentajes de Buena / Con detalle / No pasa.
- Validación: el jefe de planta ingresa un conteo manual y la plataforma registra el error del modelo, que es la verdad de terreno que le falta al proyecto.
- Certificado con código único, verificable sin cuenta e imprimible.
- Planes y cuotas: el plan Básico permite 10 análisis rápidos al mes (un análisis fallido no se cuenta). El productor puede pedir el plan Pro y el administrador lo aprueba desde su panel.
- Paneles por rol con gráficos, descarga CSV (según el plan), modo claro u oscuro y diseño para celular.
- Funciona sin internet: no usa librerías externas en el navegador.

### Datos de demostración
La primera vez se crean 8 empresas, una cuenta por rol, 9 lotes en todos los estados, 19 análisis y una solicitud de cambio de plan. Las fotos salen de `images/test` y **se analizan con el modelo real**, así que la preparación tarda un poco en CPU. El conteo manual de los lotes aprobados es el número de manzanas etiquetadas en esas fotos: el error de conteo que muestra la plataforma (8,7 % en la demo) es un error real del modelo. Los nombres de empresas y personas son ficticios.

### Cómo funciona por dentro
| Archivo | Qué hace |
|---|---|
| `src/web/negocio.py` | Reglas del negocio: roles, planes, precios, cuotas y códigos de lote y certificado |
| `src/web/app.py` | Crea la app Flask: configuración, menú por rol, protección CSRF y formatos chilenos |
| `src/web/auth.py` | Ingreso, salida, accesos de demostración y control de acceso por rol |
| `src/web/db.py` | Esquema SQLite: empresas, usuarios, lotes, análisis y solicitudes |
| `src/web/analisis.py` | Cola en segundo plano que llama a `src.vision.detector` (un análisis a la vez) |
| `src/web/rutas_*.py` | Páginas de cada rol, lotes compartidos y páginas públicas |
| `src/web/graficos.py`, `iconos.py` | Gráficos e íconos en HTML y SVG |
| `src/web/demo.py` | Datos de demostración y video de prueba |
| `src/web/templates/`, `static/` | Plantillas HTML, estilos y JavaScript |

Los datos quedan en `web_data/`: la base `applevision.db` y una carpeta por análisis en `web_data/analisis/` con el archivo original, el resultado anotado y una miniatura (más `metricas.csv` en los videos).

### Seguridad
- Las contraseñas se guardan con hash, nunca en texto plano.
- Todos los formularios tienen protección CSRF.
- Cada página exige el rol correcto. Un lote de otra empresa responde 404, sin revelar que existe.
- Las fotos y los videos solo se entregan a quien puede ver el lote.
- El servidor incluido es de desarrollo. Para producción hace falta un servidor WSGI (por ejemplo, waitress), HTTPS y `--sin-demo`.

### Variables de entorno
| Variable | Para qué |
|---|---|
| `APPLEVISION_DATOS` | Carpeta de datos de la web (por defecto `web_data/`) |
| `APPLEVISION_DEMO=0` | Desactiva las cuentas y los accesos de demostración |
| `APPLEVISION_SECRET` | Clave de sesión fija (si no se define, se crea una en `web_data/.clave_secreta`) |

## Pruebas
```bash
python -m unittest discover -s tests -v
```
| Archivo | Pruebas | Qué cubre |
|---|---:|---|
| `tests/test_foto_detalle.py` | 6 | Coordenadas y fusión de cajas del análisis de fotos por zonas |
| `tests/test_web.py` | 22 | Roles y permisos, aislamiento entre empresas, CSRF, flujo de lote a certificado, cuotas, cambio de plan, CSV y manejo de errores |
| `tests/test_validar_fotos.py` | 1 | El validador omite las fotos sin etiqueta |

Las pruebas de la web usan un analizador simulado (no cargan YOLO) y una carpeta temporal, así que no tocan `web_data/`.

## Resultados
Modelo YOLO26 nano, 50 épocas, `imgsz=416`, CPU (≈55 min).

| Métrica (valid, 190 imágenes) | Valor |
|---|---|
| mAP50 | 0.908 |
| mAP50-95 | 0.596 |
| Precision | 0.858 |
| Recall | 0.881 |

**Prueba solo con frames de cinta** (61 fotos, umbral de confianza 0.25):

| Split | Manzanas etiquetadas | Detectadas | Recall |
|---|---|---|---|
| train (43) | 85 | 98 | 0.99 |
| valid (12) | 22 | 28 | 0.95 |
| test (6) | 11 | 15 | 1.00 |

Las detecciones de más corresponden en su mayoría a **manzanas visibles que no tienen etiqueta** (por ejemplo, parcialmente cortadas por el borde), por lo que la precision real es mayor que la que reflejan estas cifras.

**Conteo en fotos** (36 fotos etiquetadas de test, perfil por defecto): error absoluto medio de 0,694 manzanas por foto y 20 conteos exactos. Ver [VALIDACION_FOTOS.md](VALIDACION_FOTOS.md).

**Limitaciones**
- Solo 61 imágenes de cinta, todas del mismo video: la prueba es un buen indicio, no una garantía.
- `valid` es en su mayoría de manzanas apiladas (178 de 190 imágenes), por lo que sus métricas reflejan poco la cinta.
- Hay 12 imágenes casi duplicadas entre train y valid (fuga menor de datos).
- El conteo con tracking aún no se valida contra un conteo manual en un video continuo (el script `validar_conteo` ya existe; falta un video continuo con su conteo manual).
- `images/test` mezcla 58 fotos sin etiqueta: no usar `yolo val split=test` hasta moverlas (ver [Datos](#datos)).

**Próximos pasos:** completar las etiquetas faltantes en cinta y re-entrenar, quitar duplicados, mover las fotos sin etiqueta fuera de `images/test`, sumar video propio de la cinta, calibrar `px_por_mm` y validar el conteo contra un conteo manual (en un piloto, la plataforma web ya registra ese error en cada lote validado).

## Metodología CRISP-DM
1. **Comprensión del negocio:** automatizar el conteo y la clasificación de manzanas en plantas de embalaje. Primer paso: conteo. El modelo de negocio está en [MODELO_NEGOCIO.md](MODELO_NEGOCIO.md).
2. **Comprensión de los datos:** ver [Datos](#datos). Referencia: MinneApple (Häni et al., 2020). *(Completar con hallazgos de `01_eda.ipynb`.)*
3. **Preparación de datos:** unificación de clases y fusión de datasets (hecho). Pendiente: features y split final.
4. **Modelamiento:** YOLO para detección. Después, Random Forest y XGBoost (supervisado) y K-Means (no supervisado) para calificar.
5. **Evaluación:** mAP, Precision y Recall para detección; error de conteo en fotos con `validar_fotos`. F1, AUC, Silhouette y validación cruzada estratificada para calificación.
6. **Despliegue:** app de escritorio y plataforma web con roles (hecho). Modelos en S3 y tracking con MLflow: pendiente.

## Alcance
No clasifica variedad, no calcula peso real, no controla actuadores. El certificado de la plataforma web es un informe de conteo y calidad visual: no reemplaza la inspección ni la certificación oficial del SAG.

## Licencias
YOLO (ultralytics): AGPL-3.0, uso académico. Para cobrar por el servicio (ver [MODELO_NEGOCIO.md](MODELO_NEGOCIO.md)) hace falta la licencia Enterprise de Ultralytics, publicar el código bajo AGPL o cambiar de detector.
Datos: Public Domain (dataset 1) y CC BY 4.0 (dataset 2, crédito a su autor en Roboflow). Fotos de prueba de Pexels: licencia de Pexels, con créditos en `images/test/images/FUENTES.md` y `FUENTES_ADICIONALES.md`.
