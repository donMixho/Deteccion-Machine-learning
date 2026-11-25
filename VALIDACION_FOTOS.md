# Evaluación del conteo en fotografías

Fecha: 16 de noviembre de 2026.

## Cambio aplicado

Se ajustó la inferencia del modelo existente; no se reentrenó ni se modificaron
los pesos. En fotos, la confianza mínima pasa de 0.18 a 0.35 y el umbral IoU
de NMS pasa de 0.45 a 0.35. Un IoU menor elimina más cajas solapadas; puede
también eliminar manzanas distintas muy juntas. La sensibilidad inicial del
panel para fotos es 65 % (100 - confianza * 100), y sigue siendo ajustable.

El panel recuerda la sensibilidad elegida para cada fuente. Video y cámara
conservan sus valores iniciales. Se comprobó el cambio entre fuentes y la
conservación de un valor personalizado para fotos.

## Método

Modelo: models/best.pt, una clase apple. Tamaño de inferencia: config.yaml,
actualmente 416. Validación con las 190 fotos de images/valid, usada para elegir
los umbrales. Comparación adicional en las 36 fotos de images/test.
El conteo de referencia es el número de objetos etiquetados en cada archivo
YOLO: admite tanto cajas como polígonos, una línea por objeto.

El validador ejecuta ambos perfiles con la misma imagen y descarta recortes
vacíos como el analizador de fotos. No modifica las etiquetas ni los pesos.

## Resultados reproducibles

| Conjunto | Perfil | Fotos | Error absoluto medio | Exceso acumulado | Omisiones acumuladas | Conteos exactos |
|---|---|---:|---:|---:|---:|---:|
| valid | anterior | 190 | 1.353 | 224 | 33 | 100 |
| valid | ajustado | 190 | 0.947 | 109 | 71 | 124 |
| test | anterior | 36 | 1.111 | 37 | 3 | 18 |
| test | ajustado | 36 | 0.694 | 13 | 12 | 20 |

El error absoluto medio en test disminuye un 37.5 %. La reducción del exceso
tiene un costo: aumentan las omisiones. Un conteo exacto no garantiza que
cada objeto está bien detectado: los falsos positivos y negativos pueden
compensarse.

Estas métricas comparan conteos con etiquetas, no prueban que todo exceso
sea duplicación. Existen etiquetas incompletas y posibles imágenes similares
entre los splits, documentadas en README.md. Las cajas sobre una misma
manzana deben revisarse visualmente para confirmar duplicados.

## Fotos externas

Se descargaron dos originales de Wikimedia Commons en reports/pruebas_fotos:

- mesa.jpg: manzanas agrupadas en una mesa; el perfil ajustado detectó 16.
- plato.jpg: manzanas apiladas en un plato; el perfil ajustado detectó 7.

Las versiones con detecciones están en mesa_contada.jpg y plato_contada.jpg.
Estas cifras son salidas del detector, no conteos manuales ni métricas de
exactitud. Hay manzanas pequeñas, parcialmente ocultas y cortadas: es necesario
revisar manualmente los objetos visibles antes de calcular el error externo.
No se usaron estas fotos para entrenar ni para elegir los umbrales.

Créditos de los originales, sin modificar:
- [Apples on a Table.JPG](https://commons.wikimedia.org/wiki/File:Apples_on_a_Table.JPG),
  Joshjrowe, [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
- [Polish apples on a plate.jpg](https://commons.wikimedia.org/wiki/File:Polish_apples_on_a_plate.jpg),
  Abraham, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

Las visualizaciones derivadas conservan la licencia correspondiente al original.
Los créditos también se guardan en reports/pruebas_fotos/FUENTES.md.

## Repetir desde Git Bash

```bash
./.venv/Scripts/python.exe -m src.vision.validar_fotos --split valid --salida reports/validacion_fotos_valid.csv
./.venv/Scripts/python.exe -m src.vision.validar_fotos --split test --salida reports/validacion_fotos_test.csv
./.venv/Scripts/python.exe -m src.app
```

En el panel: Foto del equipo, elegir imagen, Iniciar análisis. Si faltan
manzanas, subir progresivamente la sensibilidad y revisar las cajas.

También se puede analizar una foto sin abrir ventanas:

```bash
./.venv/Scripts/python.exe -m src.vision.detector --modelo models/best.pt --foto reports/pruebas_fotos/plato.jpg --sin-ventana --guardar reports/pruebas_fotos/plato_contada.jpg
```

Para fotos propias, crear un CSV con columnas imagen,conteo_manual y números
enteros no negativos. Las rutas relativas se resuelven desde la carpeta del CSV:

```csv
imagen,conteo_manual
foto_propia.jpg,5
```

```bash
./.venv/Scripts/python.exe -m src.vision.validar_fotos --manifiesto reports/pruebas_fotos/manual.csv --salida reports/validacion_fotos_externas.csv
```

Los valores --conf y --iou permiten evaluar otros umbrales. No elegir ajustes
con test: usar valid o un conjunto dedicado y evaluar al final con fotos nuevas.
Los informes y fotos en reports/ están ignorados por Git; este documento y el
validador sí pueden versionarse.

## Trabajo pendiente

Para mejorar la detección en mesas y platos, reunir más ejemplos etiquetados
de esos escenarios, revisar etiquetas incompletas y entrenar un modelo nuevo.
El ajuste actual reduce el error de conteo del conjunto evaluado, pero no
resuelve todos los casos de oclusión ni garantiza ausencia de duplicados.

## Manzanas omitidas a la izquierda: análisis por zonas (17/11/2026)

Se añadió la opción **Buscar manzanas pequeñas (solo fotos; tarda más)**,
desactivada al inicio. Examina la foto completa y nueve zonas solapadas.
Las cajas se trasladan a coordenadas absolutas y se fusionan con NMS por
clase. Se descartan detecciones cortadas por bordes internos de los recortes.

Caso: images/test/images/as_apple--156-_jpg.rf.4bd72945d39eb89a8c18bb8801624617.jpg.

| Modo | Detecciones | Etiquetas | Coincidencias uno a uno, IoU >= 0.5 |
|---|---:|---:|---:|
| Foto normal | 15 | 17 | 13 |
| Buscar pequeñas | 21 | 17 | 15 |

El análisis por zonas recupera objetos del grupo inferior izquierdo. Todavía
omite dos etiquetas y genera cajas sin correspondencia con las etiquetas.
No demuestra que haya 21 manzanas reales. Ver las imágenes izquierda_antes.jpg
e izquierda_detalle.jpg en reports/pruebas_fotos/.

| Conjunto | Modo | MAE | Exceso acumulado | Omisiones acumuladas |
|---|---|---:|---:|---:|
| valid (190) | normal ajustado | 0.947 | 109 | 71 |
| valid (190) | buscar pequeñas | 1.489 | 226 | 57 |
| test (36) | normal ajustado | 0.694 | 13 | 12 |
| test (36) | buscar pequeñas | 1.083 | 34 | 5 |

Este modo reduce omisiones pero aumenta el exceso y el error medio: se ofrece
como opción de revisión, sin reemplazar el perfil normal ni reentrenar pesos.
Subir la resolución global también se probó y no mejoró el resultado agregado.

Para usarlo: cerrar la aplicación anterior, abrir src.app, seleccionar Foto
del equipo y marcar Buscar manzanas pequeñas antes de iniciar el análisis.

```bash
./.venv/Scripts/python.exe -m src.app
./.venv/Scripts/python.exe -m src.vision.validar_fotos --split test --detalle-foto --salida reports/validacion_fotos_zonas_test.csv
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

En la CLI del detector, añadir --detalle-foto junto a --foto. Pasaron seis
pruebas de fusión de cajas, coordenadas, objetos distintos, bordes internos y
reales, salida vacía y modo normal. Se comprobó también la opción en la interfaz.

## Modelo de 2 clases (24/11/2026)

Se reentrenó YOLO26n con dos clases, apple y damaged_apple, con la misma receta y
el mismo perfil de inferencia en fotos (confianza 0.35, IoU 0.35). Ahora es
models/best.pt; el anterior quedó en models/best_1clase.pt.

| Conjunto | Modelo | MAE | Exceso acumulado | Omisiones acumuladas | Conteos exactos |
|---|---|---:|---:|---:|---:|
| valid (190) | 1 clase | 0.947 | 109 | 71 | 124 |
| valid (190) | 2 clases | 0.816 | 89 | 66 | 121 |
| test (36) | 1 clase | 0.694 | 13 | 12 | 20 |
| test (36) | 2 clases | 0.583 | 15 | 6 | 21 |

El modelo nuevo reduce el error medio en ambos conjuntos. validar_fotos omite
ahora, con un aviso, las 58 fotos de Pexels sin etiqueta de images/test. La
detección de daño se evalúa aparte con python -m src.vision.validar_danio
(ver README.md, sección Resultados).

```bash
./.venv/Scripts/python.exe -m src.vision.validar_fotos --split test --modelo models/best_1clase.pt
./.venv/Scripts/python.exe -m src.vision.validar_fotos --split test --modelo models/best.pt
```
