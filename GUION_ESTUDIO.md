# AppleVision Chile: guion de estudio y exposición

Guía para estudiar y presentar el proyecto entre dos personas. Está pensada para ~12 minutos de exposición y ~5 de preguntas.
Las cifras salen del [README](README.md) y de [MODELO_NEGOCIO.md](MODELO_NEGOCIO.md). **Si se reentrena el modelo, actualicen la sección 6 antes de presentar.**

**Reparto sugerido**

| Persona | Parte | Tiempo |
|---|---|---|
| **A** | Problema, datos, modelo y resultados | ~6 min |
| **B** | Plataforma web, modelo de negocio, pagos y cierre | ~6 min |

Los dos deben saber **todo** (las preguntas no respetan el reparto). Estudien primero la sección 1 y la 6.

---

## 1. El proyecto en 30 segundos (aprendérselo de memoria)

> AppleVision Chile cuenta y clasifica manzanas en una planta de embalaje con una cámara y un modelo de visión (YOLO).
> El resultado de cada lote queda en un certificado que ven el packing, el productor y la exportadora.
> Es un servicio por suscripción, y el productor entra gratis porque atrae a los otros dos.

Proyecto del ramo **MLY1101 Machine Learning, DUOC UC**. Es un caso hipotético: no hay una empresa real detrás, los datos son públicos y las empresas de la demo son ficticias.

---

## 2. Guion de la Persona A (problema, datos y modelo)

### 2.1 El problema (1 min)
- Chile exporta manzanas con estándares SAG/Asoex. En las plantas de embalaje el conteo y la clasificación son **manuales**, y eso genera errores y cuellos de botella.
- Además hay **asimetría de información**: el productor cobra según la fruta exportable (*packout*), pero ese dato sale solo del informe del packing, sin evidencia por lote. Eso produce desconfianza y reclamos.
- Idea: una cámara sobre la cinta, un modelo que detecta cada manzana, un contador que suma las que cruzan una línea, y una clasificación en un semáforo.

### 2.2 Los datos (1,5 min)
- Dos datasets públicos de **Roboflow Universe**, en formato YOLO:
  - **Cinta transportadora** (Public Domain): 61 imágenes, todas frames de un solo video.
  - **Manzanas apiladas en cajas** (CC BY 4.0): 697 imágenes, con oclusión. Trae la clase `damaged_apple`.
- Total usado: **758 imágenes y 2.978 manzanas** etiquetadas (2.270 sanas y 708 dañadas).
- Se descartó un tercer dataset de huerto con fotos de dron porque no coincidía con el escenario real. Esa decisión es un buen punto para mostrar criterio.
- **Limitaciones que hay que decir** (suman credibilidad): la cinta sale de un solo video; hay pocos ejemplos de cinta frente a montones; las manzanas dañadas vienen de montones, no de la cinta; el set de test tiene solo 10 manzanas dañadas.

### 2.3 El modelo (2 min)
- **YOLO26 nano**, 2 clases: `apple` y `damaged_apple`. Entrenado en CPU: 50 épocas, 416 px, unos 38 min.
- **Por qué dos clases:** con una sola clase, el daño se detectaba con una regla de color (tono, saturación, píxeles oscuros) que confundía sombras con pudrición. Con la clase aprendida, el daño se reconoce mucho mejor.
- **Conteo:** ByteTrack le da un ID a cada manzana y la cuenta **una sola vez** al cruzar la línea. Sin tracking se contaría la misma manzana en varios frames.
- **Semáforo:** Buena / Con detalle / No pasa, según calibre (65 a 80 mm), color y daño. El calibre en mm depende de la calibración de la cámara (`px_por_mm`).
- Un modelo clásico (Random Forest, XGBoost) no sirve para esto: la entrada son imágenes y hay que **localizar** objetos, no solo clasificar una tabla.

### 2.4 Resultados (1,5 min): ver sección 6
Mensaje central: **"El modelo de 2 clases es mejor en todo lo que importa"**, y lo medimos con fotos que el modelo no vio al entrenar.

---

## 3. Guion de la Persona B (plataforma, negocio y pagos)

### 3.1 La plataforma web (2 min)
- Hecha con **Flask + SQLite**, con **5 roles**. Cada uno ve solo lo de su empresa.
  - Operador: sube la foto o el video del lote.
  - Jefe de planta: compara con un conteo manual y aprueba o rechaza el lote.
  - Productor: ve sus lotes con evidencia.
  - Exportadora: ve los lotes certificados de sus proveedores.
  - Administrador: empresas, usuarios, planes y métricas del negocio.
- Flujo de un lote: **Recepción → Análisis con IA → Validación → Certificado**.
- El análisis corre en segundo plano con **el mismo detector** de la app de escritorio.
- El certificado tiene un **código único** (por ejemplo `AV-2026-7KQ3XD`) y se puede **verificar sin cuenta** en `/verificar`.
- Valor para el proyecto: el conteo manual del jefe de planta es la **verdad de terreno** que le faltaba al modelo; así se mide su error real.
- Seguridad: contraseñas con hash, protección CSRF en todos los formularios, y un lote de otra empresa responde 404 sin revelar que existe.

### 3.2 El modelo de negocio (2 min)
SaaS B2B de tres lados (supuestos a validar con un piloto, **no son cifras reales**):

| Cliente | Plan | Precio (CLP + IVA) |
|---|---|---|
| Packing (cliente principal) | Packing | $290.000/mes por línea + $1.500.000 de instalación |
| Productor | Básico / Pro | Gratis (10 análisis al mes) / $9.990/mes |
| Exportadora | Exportadora | $190.000/mes |

- **Efecto de red:** el productor gratis atrae a los packings que lo usan y a las exportadoras que piden certificados.
- Punto de equilibrio: unas 23 líneas. Está detallado en `MODELO_NEGOCIO.md`.

### 3.3 Pagos con Webpay Plus (1 min)
- El productor paga el plan Pro desde **Mi plan**: neto + IVA 19 % ($9.990 + $1.898 = **$11.888**).
- Flujo: creamos la transacción en Transbank → el usuario paga en el banco → al volver **confirmamos con Transbank** y validamos monto y orden → recién ahí se activa el plan por 30 días.
- Está en **ambiente de integración**: no hay cobros reales. Para cobrar de verdad hacen falta credenciales de producción de Transbank, un dominio con HTTPS y la validación del comercio.

### 3.4 Cierre (1 min)
- Qué lograron: detector que cuenta y detecta daño, plataforma con roles, certificados verificables, modelo de negocio y pagos.
- Qué falta (decirlo con honestidad): validar el conteo en un video continuo con conteo manual, más ejemplos de cinta y de daño, reembolsos en Webpay, licencia de YOLO para cobrar.

---

## 4. Demo en vivo (3 pasos, ~2 min)
Antes de presentar: tener `models/best.pt` instalado (`modelo.bat`, opción 5) y abrir la web con `iniciar_web.bat`. **Sin ese archivo los análisis fallan.**

1. **Operador** (entrar desde la portada con "Probar demo"): recibir un lote y subir una foto. Mostrar el conteo y los colores del semáforo.
2. **Jefe de planta:** ingresar un conteo manual, ver el error del modelo y aprobar. Se emite el certificado.
3. **Verificar:** copiar el código en `/verificar` sin iniciar sesión. Si hay tiempo, mostrar **Mi plan** como productor y el botón *Pagar con Webpay*.

Tarjeta de prueba de Webpay: VISA `4051 8856 0044 6623`, CVV `123`. En el banco: RUT `11.111.111-1`, clave `123`.
Plan B si algo falla: tener capturas de cada paso.

---

## 5. Conceptos que hay que dominar
- **mAP50:** promedio de la precisión de detección contando como acierto una caja que se superpone al menos 50 % con la real (IoU ≥ 0,5). **mAP50-95** es lo mismo pero más exigente (IoU de 0,5 a 0,95).
- **Precision:** de lo que el modelo marcó, cuánto era correcto. **Recall:** de lo que existía, cuánto encontró. **F1:** equilibrio de ambos.
- **IoU:** cuánto se superponen la caja predicha y la real.
- **NMS:** elimina cajas duplicadas del mismo objeto.
- **Umbral de confianza:** el mínimo para aceptar una detección. Más alto = menos falsos positivos, pero se escapan manzanas. En foto se usa 0,35; en video, 0,18.
- **Tracking (ByteTrack):** mantiene la identidad de cada objeto entre frames.
- **Overfitting:** el modelo memoriza el entrenamiento. Por eso se separa train, valid y test.
- **Fuga de datos:** hay unas 12 imágenes casi duplicadas entre train y valid. Es una limitación conocida.
- **CRISP-DM:** negocio, datos, preparación, modelado, evaluación y despliegue. El proyecto sigue estas seis etapas.

---

## 6. Números para memorizar
Valores del README, modelo de 2 clases frente al anterior (1 clase más regla de color), sobre las mismas fotos de validación.

| Métrica | Antes | Ahora |
|---|---|---|
| Manzanas encontradas (recall) | 85 % | **90 %** |
| Manzanas dañadas encontradas | 37 % | **94 %** |
| Sanas marcadas como dañadas | 29 % | **8 %** |
| Error de conteo por foto (test) | 0,694 | **0,583** |
| mAP50 (detectar manzanas) | 0,884 | **0,914** |
| F1 de daño | 0,34 (regla de color) | **0,88** |

- Conteo exacto en **21 de 36** fotos de test (el modelo anterior, 20).
- Por clase en validación: `apple` mAP50 0,866 y `damaged_apple` 0,827.
- Dataset: 758 imágenes, 2.978 manzanas (2.270 sanas, 708 dañadas).

---

## 7. Preguntas probables y cómo responder

**¿Por qué YOLO y no otro modelo?**
Detecta y localiza varios objetos en una pasada y es rápido, lo que sirve para video. Un clasificador solo diría "hay manzanas" sin contarlas ni ubicarlas.

**¿Cómo evitan contar dos veces la misma manzana?**
ByteTrack le asigna un ID y se cuenta solo cuando ese ID cruza la línea.

**¿Qué tan confiable es el conteo?**
En fotos, el error medio es de 0,583 manzanas por foto. En video **todavía no está validado** contra un conteo manual continuo; el script `validar_conteo` existe, pero falta ese video. Hay que decirlo directamente.

**¿El modelo funciona en una planta real?**
Aún no probado. Los datos son de una sola cinta y de montones en cajas. Haría falta un piloto con video propio de la planta, con la cámara y la luz reales.

**¿Por qué solo 758 imágenes?**
Es lo disponible en datasets públicos con licencia abierta. Para producción se juntaría video propio y se etiquetaría. Lo mencionamos como siguiente paso.

**¿El certificado tiene validez oficial?**
No. Es un informe de conteo y calidad visual. **No reemplaza** la inspección ni la certificación oficial del SAG.

**¿Pueden cobrar con YOLO?**
YOLO usa licencia AGPL-3.0, válida para uso académico. Para cobrar hace falta la licencia Enterprise de Ultralytics, publicar el código como AGPL o cambiar de detector. Está como riesgo en `MODELO_NEGOCIO.md`.

**¿Los precios son reales?**
Son supuestos del modelo de negocio, para validar con entrevistas y un piloto.

**¿Los pagos funcionan de verdad?**
Funcionan en el ambiente de integración de Transbank, sin cobrar. Para producción faltan credenciales reales, HTTPS y la validación del comercio.

**¿Qué pasa si el usuario cierra el navegador en el banco?**
El pago queda pendiente y se anula solo a los 60 minutos. El plan solo se activa si Transbank confirma el pago.

**¿Cómo protegen los datos de cada empresa?**
Cada página exige el rol correcto y cada consulta filtra por empresa. Un lote ajeno responde 404.

**¿Qué mejorarían primero?**
Validar el conteo en video, sumar datos de cinta y de daño, y probar con una planta piloto.

**¿Por qué 416 px y no 640?**
Menos peso y menos tiempo en CPU, y las fotos del dataset son de 416. Se está probando una receta a 640 px para ver si mejora el conteo.

---

## 8. Lo que NO conviene decir
- "Ya funciona en una planta real": no se ha probado.
- "Los precios están validados": son supuestos.
- "El conteo en video es preciso": no está validado.
- "El certificado es oficial": no lo es.
- Cifras sin fuente: usen solo las de la sección 6.

---

## 9. Plan de estudio (una tarde)
1. Cada uno lee el README completo (30 min) y esta guía (20 min).
2. Ensayen la sección 1 de memoria, por turnos.
3. Cada uno ensaya su parte con cronómetro (6 min).
4. Hagan la demo completa una vez sin mirar la guía.
5. Intercambien roles: uno pregunta con la sección 7 y el otro responde sin leer.
6. Antes de presentar: verificar `models/best.pt`, abrir la web y probar el inicio de sesión de cada rol.

---

## 10. Dónde está cada cosa en el código
| Tema | Archivo |
|---|---|
| Detector y conteo | `src/vision/detector.py` |
| Semáforo y daño | `src/vision/clasificador.py` |
| Medir el conteo en fotos | `src/vision/validar_fotos.py` |
| Medir la detección de daño | `src/vision/validar_danio.py` |
| Entrenar el modelo | `scripts/entrenar_2clases.py` |
| Reglas del negocio (roles, planes, precios) | `src/web/negocio.py` |
| Análisis en segundo plano | `src/web/analisis.py` |
| Pagos con Webpay | `src/web/webpay.py`, `src/web/rutas_pagos.py` |
| Modelo de negocio completo | `MODELO_NEGOCIO.md` |
