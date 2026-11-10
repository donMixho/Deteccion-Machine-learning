# AppleVision Chile — Análisis del proyecto

Documento que combina (1) lo que el proyecto **realmente contiene** (código, datos, reportes) y (2) lo que dicen **todos los README** (principal, de los datasets y de Roboflow). Al final hay una lista de diferencias detectadas entre ambos.

> Proyecto MLY1101 — Machine Learning, DUOC UC. Sistema de clasificación y conteo de manzanas para plantas de embalaje frutícola.

---

## 1. Resumen ejecutivo

- **Qué es:** un detector YOLO (YOLO26 nano) que identifica manzanas en video/foto/cámara, las sigue con ByteTrack y las cuenta una sola vez cuando cruzan una línea. Incluye un dashboard de escritorio y un panel de conteo en vivo.
- **Etapa actual:** *primer paso* = **detectar y contar** (una sola clase: `apple`). La calificación (calibre, color, sana/podrida) existe como regla de semáforo, pero la parte de ML (Random Forest, XGBoost, K-Means) está **sin implementar**.
- **Estado:** la detección funciona bien (mAP50 0,908), pero el **conteo con tracking aún no está validado** y la prueba existente en `reports/validacion_conteo.csv` muestra un resultado malo (ver sección 8).

---

## 2. Contexto del caso (README principal)

Chile exporta manzanas bajo estándares SAG/Asoex. En las plantas de embalaje, la clasificación y el conteo manual generan errores y cuellos de botella. La idea: cámara + visión por computador. Las manzanas avanzan por una cinta, el modelo detecta cada una, un contador suma las que cruzan el campo de visión y, en una etapa posterior, cada detección se recorta y se califica.

Un primer dataset de huerto (fotos de dron, *Apple Detection on split images*) se **descartó** porque no coincide con el escenario real (cinta); fue eliminado del proyecto.

---

## 3. Datos

Dos datasets públicos de Roboflow Universe, formato YOLOv8, unificados en una clase (`apple`).

| | Dataset 1: conveyor_apple_sorting | Dataset 2: apple-sorting |
|---|---|---|
| Autor/workspace | `fruitgradechecking` | Arfiani Nur Sayidah (`arfiani-nur-sayidah-9lizr`) |
| Link | https://universe.roboflow.com/fruitgradechecking/conveyor_apple_sorting | https://universe.roboflow.com/arfiani-nur-sayidah-9lizr/apple-sorting-2bfhk |
| Contenido | Frames de video de manzanas sueltas en cinta industrial | Manzanas apiladas en cajas/montones, con oclusión |
| Imágenes | 61 (43 train / 12 valid / 6 test) | 697 (489 / 178 / 30), versión 2 |
| Anotación | Polígonos | Cajas |
| Clases originales | `apple`, `apple_a` | `apple`, `damaged_apple` |
| Tamaño | 640×300 | 416×416 (bordes blancos) |
| Licencia | Public Domain | CC BY 4.0 (dar crédito al autor) |
| Versión / fecha | v1, exportado 2024-07-12 | v2, 2022-03-26 (exportado 9-abr-2023) |

### Lo que dicen los README de los datasets
- **`README.dataset.txt` (dataset 2):** proyecto creado por Arfiani Nur Sayidah para separar manzanas de manzanas dañadas. Balance original: **apple 2.152 / damaged_apple 708** (2.860 objetos).
- **`README.roboflow.txt` (dataset 2):** exportado desde Roboflow el 9-abr-2023. 697 imágenes en formato YOLOv8. Preprocesado: auto-orientación (EXIF) y *resize* a 416×416 con bordes blancos (*fit*). **Sin aumentación de datos.**
- **`images/README.dataset.txt`:** corresponde al dataset 1 (conveyor_apple_sorting, Public Domain, 2024-07-12).

### Preparación realizada
1. Descarga de ambos con la API de Roboflow (`scripts/descargar_dataset.py`).
2. Fusión en `images/` (las imágenes del dataset 2 llevan prefijo `as_`).
3. Unificación de clases: `apple_a` y `damaged_apple` → `apple`.
4. El dataset 2 original (2 clases) se conserva en `data/01_raw/apple_sorting_original/`; hay además `data/01_raw/labels_respaldo_v1/` (respaldo de etiquetas).

**Resultado en `images/`:** 758 imágenes (train 532 / valid 190 / test 36) y 2.223 manzanas en 1 clase.

### Limitaciones conocidas
- Dataset 1: todos los frames salen de **un solo video** (muy parecidos entre sí), con marca de agua `clideo.com` y desenfoque por movimiento.
- Dataset 2: no es de cinta; sirve para que el modelo aprenda cómo se ve una manzana.
- Desbalance de escenario: 697 imágenes de montones vs 61 de cinta → las métricas de `valid`/`test` reflejan sobre todo montones.

---

## 4. Estructura del proyecto

```
images/                       dataset actual (YOLO, 1 clase) + data.yaml
data/
  01_raw/                     datasets originales (apple_sorting_original, labels_respaldo_v1)
  02_processed/               salida del pipeline (metricas.csv, validacion_tmp.csv)
  03_features/                features para ML (vacío)
src/
  app.py                      dashboard de inicio (269 líneas)
  vision/                     detector, panel, calibrador, clasificador, validar_conteo
  ml/                         features, train, evaluate  (stubs)
  utils/                      config, s3_helper
notebooks/                    01_eda, 02_models, 03_optimization
scripts/                      descargar_dataset.py, comprimir_dataset.py
models/                       best.pt (pesos entrenados)
reports/                      panel_demo.png, prueba_cinta/ (frames), prueba_cinta_con_panel.mp4, validacion_conteo.csv
mlruns/ + mlflow.db           tracking MLflow
entrenamiento.log             log del entrenamiento (~324 KB)
config.yaml                   calibre, HSV, px_por_mm, fuente de video, S3
iniciar.bat                   abre el dashboard con doble clic
yolo26n.pt                    pesos base de YOLO26 nano
```

---

## 5. Cómo funciona (código)

| Módulo | Función |
|---|---|
| `src/app.py` | Dashboard: elegir fuente (cámara / video / foto), nombre del lote, posición de línea, confianza mínima, guardar video; botón *Probar cámara*; muestra el último resultado. |
| `src/vision/detector.py` | Detección + tracking **ByteTrack**; cada manzana recibe un ID y se cuenta una vez al cruzar la línea (por su centro). Calcula HSV medio (con media circular del matiz, sobre una elipse inscrita), área, diámetro estimado, aspecto. Escribe `data/02_processed/metricas.csv` (columnas: `id, frame, area_px, diametro_mm_est, hue, saturacion, valor, aspecto, clase_yolo`). Modo foto sin tracking. |
| `src/vision/panel.py` | Dibuja cajas, línea de conteo (azul punteada) y panel con total, desglose, calibre y fps. |
| `src/vision/clasificador.py` | Semáforo **Buena / Con detalle / No pasa** según calibre, color HSV, aspecto y clase YOLO. |
| `src/vision/calibrador.py` | Conversión px→mm con un objeto de referencia (`px_por_mm`). |
| `src/vision/validar_conteo.py` | Compara conteo automático vs manual; error por video, error absoluto medio y desvío por posición de línea. Escribe `reports/validacion_conteo.csv`. |
| `src/utils/config.py`, `s3_helper.py` | Carga de `config.yaml`/`.env` y ayuda para subir/bajar de S3. |
| `src/ml/*` | **Stubs de 4–6 líneas**: pendientes (E2/E3). |

### Reglas del semáforo (`clasificador.py`)
- Clase YOLO `rotten`/`defect`/`damaged` → **No pasa**.
- Fuera de calibre más de **3 mm** → No pasa.
- Aspecto (lado menor/mayor) < **0,70** → No pasa.
- Si no, se cuentan problemas: fuera de calibre leve, aspecto < **0,85**, color fuera de rango. 0 problemas → **Buena**; ≥1 → **Con detalle**.
- En fotos no se evalúa calibre (no hay escala px/mm).
- Nota de diseño en el código: este semáforo es regla de negocio; la etiqueta `calidad` para entrenar ML debe venir de Roboflow, **no** de esta función (evitar fuga de datos).

### Configuración (`config.yaml`)
| Parámetro | Valor |
|---|---|
| `calibre_min_mm` / `calibre_max_mm` | 65 / 80 |
| `hue_min` / `hue_max` / `saturacion_min` | 0 / 15 / 120 (rojo) |
| `fuente_video` | 0 (webcam) |
| `imgsz` | 416 |
| `px_por_mm` | 3,2 (**sin calibrar**) |
| `s3_bucket` / `s3_prefix` | vacío / `apple-vision/` |

`.env.example` guarda credenciales AWS Learner Lab (key, secret, session token, región `us-east-1`); la clave de Roboflow va como `ROBOFLOW_API_KEY`. Nunca subir el `.env` real.

---

## 6. Instalación y uso (README principal)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env     # solo si se usa S3 o Roboflow
```

Dependencias: ultralytics, opencv-python, pandas, numpy, scikit-learn, xgboost, optuna, mlflow, boto3, matplotlib, seaborn, jupyter, pyyaml, python-dotenv, joblib, pillow, roboflow.

| Acción | Comando |
|---|---|
| Dashboard | doble clic en `iniciar.bat` o `python -m src.app` |
| Contar un video (CLI) | `python -m src.vision.detector --modelo models/best.pt --video ruta.mp4 --lote "Lote 1"` |
| Contar una foto | `python -m src.vision.detector --foto ruta/foto.jpg [--sin-ventana --guardar salida.jpg]` |
| Validar contra conteo manual | `python -m src.vision.validar_conteo --video cinta.mp4 --manual 25 [--lineas 0.3,0.5,0.8]` o `--manifiesto reports/verdad_terreno.csv` |
| Entrenar | `yolo detect train data=images/data.yaml model=yolo26n.pt epochs=50 patience=15 imgsz=416 batch=16 device=cpu project=runs name=apple_v1` y copiar `best.pt` a `models/` |

Opciones del detector: `--linea 0.8`, `--conf 0.25`, `--guardar`, `--sin-ventana`, `--foto`. Con la tecla `Q` se cierra la ventana de video y se vuelve al dashboard.

**Aviso del README:** `px_por_mm` hay que calibrarlo con un objeto de tamaño conocido; con el valor por defecto casi todo sale «No pasa» aunque el conteo total sea correcto. En fotos, el total siempre es Buena + Con detalle + No pasa y las manzanas muy tapadas pueden quedar sin contar.

---

## 7. Resultados

Modelo **YOLO26 nano**, 50 épocas, `imgsz=416`, CPU (≈55 min).

| Métrica (valid, 190 imágenes) | Valor |
|---|---|
| mAP50 | **0,908** |
| mAP50-95 | 0,596 |
| Precision | 0,858 |
| Recall | 0,881 |

**Prueba solo con frames de cinta** (61 fotos, conf 0,25):

| Split | Etiquetadas | Detectadas | Recall |
|---|---|---|---|
| train (43) | 85 | 98 | 0,99 |
| valid (12) | 22 | 28 | 0,95 |
| test (6) | 11 | 15 | 1,00 |

Las detecciones "de más" serían en su mayoría manzanas visibles **sin etiqueta** (p. ej. cortadas por el borde), por lo que la precision real sería mayor que la mostrada.

---

## 8. Metodología CRISP-DM y estado de avance

| Fase | Estado |
|---|---|
| 1. Comprensión del negocio | Hecha: automatizar conteo y clasificación; primer paso = conteo. |
| 2. Comprensión de los datos | Parcial. Referencia: MinneApple (Häni et al., 2020). El notebook `01_eda.ipynb` es una **plantilla con TODO** (16 celdas) que espera `detecciones.csv`. |
| 3. Preparación de datos | Hecha: unificación de clases y fusión. Pendiente: features y split final. |
| 4. Modelamiento | YOLO listo. Random Forest / XGBoost / K-Means: **pendientes** (`02_models.ipynb` y `03_optimization.ipynb` solo tienen un TODO; `src/ml/*` son stubs). |
| 5. Evaluación | mAP/Precision/Recall hechos. F1, AUC, Silhouette y CV estratificada pendientes. |
| 6. Despliegue | Dashboard local listo. Modelos en S3 y tracking MLflow: pendiente/parcial (existen `mlflow.db` y `mlruns/`). |

### Limitaciones declaradas
- Solo 61 imágenes de cinta, todas del mismo video: buen indicio, no garantía.
- `valid` es mayormente montones (178 de 190).
- 12 imágenes casi duplicadas entre train y valid (fuga menor de datos).
- El conteo con tracking no está validado contra un conteo manual en video continuo.

### Próximos pasos (README)
Completar etiquetas faltantes en cinta y re-entrenar, quitar duplicados, sumar video propio de la cinta, calibrar `px_por_mm` y validar el conteo contra uno manual.

### Alcance
No clasifica variedad, no calcula peso real, no controla actuadores. Licencias: YOLO/ultralytics AGPL-3.0 (uso académico); datos Public Domain (dataset 1) y CC BY 4.0 (dataset 2, dar crédito).

---

## 9. Hallazgos del análisis (diferencias y riesgos)

1. **La validación del conteo ya se corrió y salió mal.** `reports/validacion_conteo.csv` (video `prueba_cinta_con_panel.mp4`, conteo manual = 4):

   | Línea | Conteo auto | IDs vistos | Error |
   |---|---|---|---|
   | 0,3 | 1 | 4 | −3 (75 %) |
   | 0,5 | 1 | 4 | −3 (75 %) |
   | 0,8 | 0 | 4 | −4 (100 %) |

   El tracker ve las 4 manzanas (4 IDs) pero **no las cuenta al cruzar la línea**. Además el README dice que esta validación "aún no se hizo". Ojo: ese video ya lleva el panel dibujado (es un video de demo, no el original), lo que puede alterar la detección; y los frames de cinta vienen de un video corto. Conviene revisar la lógica de cruce y repetir con un video limpio.
2. **README apunta a un archivo inexistente:** "Ver `proyecto_manzanas_ml.md`" — no está en el repo.
3. **`metricas.csv` está vacío** y `data/03_features/` también; el notebook EDA y los de modelos dependen de un `detecciones.csv` que el detector actual no genera (escribe `metricas.csv`). Nombre inconsistente entre notebooks/`features.py` y `detector.py`.
4. **`clasificador.py` define `CLASES_DEFECTO` (rotten/defect/damaged)**, pero el modelo tiene una sola clase `apple`; esa regla nunca se activa. Al unificar `damaged_apple` → `apple` se perdió la señal de manzanas dañadas del dataset 2 (708 objetos) que serviría para la etapa de calificación.
5. **`px_por_mm: 3.2` es un valor por defecto, no calibrado**, por lo que el desglose Buena/Con detalle/No pasa no es confiable aún.
6. **Cambios sin commitear:** `README.md`, `src/app.py`, `clasificador.py`, `detector.py` modificados y `validar_conteo.py` sin añadir a git. Los archivos pesados (`yolo26n.pt` 5,5 MB, `mlflow.db`, `entrenamiento.log`) están en la carpeta; revisar que `.gitignore` los cubra.
7. **Posible fuga de datos:** 12 duplicados train/valid (declarado) y, por ser un solo video, el split train/valid/test de la cinta no es independiente.
8. **`.env.example` expone solo plantillas** (sin secretos), correcto; confirmar que `.env` real no esté versionado.
