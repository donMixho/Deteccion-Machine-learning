# AppleVision Chile
Sistema inteligente de clasificación y conteo de manzanas para plantas de embalaje frutícola.
Proyecto MLY1101 — Machine Learning | DUOC UC

## Objetivo del primer paso
Construir un modelo de visión (YOLO) que **detecte y cuente manzanas sueltas** que pasan frente a una cámara, como en una cinta transportadora.

En esta etapa **no se califica** (calibre, color, sana/podrida): solo se identifica cada manzana y se cuenta. La calificación queda para la etapa siguiente, sobre recortes de cada manzana detectada.

## Introducción del caso
Chile exporta manzanas bajo estándares SAG/Asoex. En las plantas de embalaje, la clasificación y el conteo manual generan errores y cuellos de botella.

La idea es automatizarlo con cámara y visión por computador. Las manzanas avanzan por una cinta, el modelo detecta cada una, y un contador suma las que cruzan el campo de visión. Después, cada detección se recorta y se califica.

Un primer dataset de huerto (fotos de dron) se descartó porque no coincide con el escenario real: ver [Datos](#datos).

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

**Dataset descartado:** *Apple Detection on split images* (fotos de dron sobre huertos, cortadas en cuadrículas y con casi todo augmentado). Fue eliminado del proyecto.

## Preparación realizada
- Se descargaron ambos datasets con la API de Roboflow.
- Se fusionaron en `images/`. Las imágenes del dataset 2 llevan el prefijo `as_`.
- Se unificaron las clases: `apple_a` y `damaged_apple` pasan a `apple`.
- El dataset 2 original, con sus 2 clases, se conserva en `data/01_raw/apple_sorting_original/`.

Resultado en `images/`: 758 imágenes (train 532 / valid 190 / test 36) y 2.223 manzanas en una clase.

## Estructura del proyecto
```
images/                       dataset actual (YOLO, 1 clase)
  train|valid|test/images     imágenes
  train|valid|test/labels     etiquetas
  data.yaml                   configuración del dataset
data/
  01_raw/                     datasets originales
    apple_sorting_original/   dataset 2 con sus 2 clases
  02_processed/               salida del pipeline (metricas.csv)
  03_features/                features para ML
src/
  app.py                      dashboard de inicio (elegir cámara o video)
  vision/                     detector, panel en vivo, calibrador, clasificador, validar_conteo
  ml/                         features, train, evaluate
  utils/                      config, s3_helper
notebooks/                    01_eda, 02_models, 03_optimization
scripts/                      descargar y comprimir dataset
models/                       pesos entrenados (best.pt)
reports/                      informes, gráficos y videos de prueba
config.yaml                   calibre, HSV, px_por_mm, fuente de video
iniciar.bat                   abre el dashboard con doble clic
```

## Instalación
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env          # solo si se usará S3 o Roboflow
```
Si usas Roboflow, guarda la clave en `.env` (`ROBOFLOW_API_KEY=...`). No la compartas ni la subas a git.

## Uso

### Dashboard (la forma más simple)
Haz doble clic en `iniciar.bat`, o desde la terminal:
```bash
python -m src.app
```

**Desde Git Bash** (abre el panel; ahí eliges el video del computador y se hace el análisis):
```bash
cd /c/Users/rafa/Desktop/apple-vision-chile
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
python -m src.vision.detector --foto ruta/foto.jpg
python -m src.vision.detector --foto ruta/foto.jpg --sin-ventana --guardar salida.jpg
```
Cada detección cuenta como una manzana (no hay tracking en una foto). Las manzanas muy tapadas pueden quedar sin contar. En una foto **no se evalúa el calibre**, porque no se conoce la escala px/mm; la categoría sale solo de color, forma y clase YOLO. El total es siempre la suma de Buena + Con detalle + No pasa.

### Línea de comandos
```bash
python -m src.vision.detector --modelo models/best.pt --video ruta.mp4 --lote "Lote 1"
```
Opciones: `--linea 0.8` (posición de la línea, fracción del ancho), `--conf 0.25`, `--guardar salida.mp4`, `--sin-ventana`, `--foto ruta.jpg` (cuenta una sola foto). Sin `--video` ni `--foto` usa la fuente de `config.yaml`. Genera `data/02_processed/metricas.csv`.

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
Ajustar `config.yaml` (calibre, HSV, `px_por_mm`, fuente de video). **`px_por_mm` hay que calibrarlo** con un objeto de tamaño conocido en cámara: con el valor por defecto las categorías salen casi todas «No pasa», aunque el conteo total es correcto.

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

**Limitaciones**
- Solo 61 imágenes de cinta, todas del mismo video: la prueba es un buen indicio, no una garantía.
- `valid` es en su mayoría de manzanas apiladas (178 de 190 imágenes), por lo que sus métricas reflejan poco la cinta.
- Hay 12 imágenes casi duplicadas entre train y valid (fuga menor de datos).
- El conteo con tracking aún no se valida contra un conteo manual en un video continuo (el script `validar_conteo` ya existe; falta un video continuo con su conteo manual).

**Próximos pasos:** completar las etiquetas faltantes en cinta y re-entrenar, quitar duplicados, sumar video propio de la cinta, calibrar `px_por_mm` y validar el conteo contra un conteo manual.

## Metodología CRISP-DM
1. **Comprensión del negocio:** automatizar el conteo y la clasificación de manzanas en plantas de embalaje. Primer paso: conteo.
2. **Comprensión de los datos:** ver [Datos](#datos). Referencia: MinneApple (Häni et al., 2020). *(Completar con hallazgos de `01_eda.ipynb`.)*
3. **Preparación de datos:** unificación de clases y fusión de datasets (hecho). Pendiente: features y split final.
4. **Modelamiento:** YOLO para detección. Después, Random Forest y XGBoost (supervisado) y K-Means (no supervisado) para calificar.
5. **Evaluación:** mAP, Precision y Recall para detección. F1, AUC, Silhouette y validación cruzada estratificada para calificación.
6. **Despliegue:** demo en vivo, modelos en S3 y tracking con MLflow. *(Pendiente.)*

## Alcance
Ver `proyecto_manzanas_ml.md`. No clasifica variedad, no calcula peso real, no controla actuadores.

## Licencias
YOLO (ultralytics): AGPL-3.0, uso académico.
Datos: Public Domain (dataset 1) y CC BY 4.0 (dataset 2, crédito a su autor en Roboflow).
