# AppleVision Chile — Modelo de negocio

> Propuesta para llevar a un producto lo que ya construimos: el detector YOLO que cuenta y clasifica manzanas (Buena / Con detalle / No pasa).
> La plataforma web con roles (`python -m src.web`) implementa este modelo. Los precios y las cifras son **supuestos que hay que validar** con entrevistas y un piloto.

## 1. Resumen

**AppleVision es un servicio de conteo y calidad certificada de manzanas, lote por lote.**
Cobramos a la planta de embalaje (packing) una suscripción mensual por línea. A cambio recibe conteo automático y una clasificación de calidad con evidencia (foto o video anotado) para cada lote. El resultado queda en un **certificado verificable** que ven el productor que entregó la fruta y la exportadora que la compra.

Es un modelo **SaaS B2B de tres lados**:

| Lado | Paga | Por qué entra |
|---|---|---|
| Packing (cliente principal) | Suscripción por línea + instalación | Ahorra conteo manual, controla calidad en línea y reduce reclamos |
| Productor | Gratis (plan Básico) o plan Pro | Ve con evidencia cómo salió su fruta |
| Exportadora | Suscripción | Recibe la calidad certificada de sus proveedores antes de embarcar |

El productor entra gratis porque **atrae a los otros dos lados**. Un productor que ya ve sus lotes con evidencia va a preferir packings que usen AppleVision. Y una exportadora que verifica certificados va a pedírselos a más packings.

## 2. Problema

1. **Conteo y clasificación manual.** En las plantas de embalaje el conteo y la clasificación manual generan errores y cuellos de botella (ver README).
2. **Asimetría de información.** El productor cobra según la fruta que resulta exportable (*packout*), pero ese dato sale solo del informe del packing, sin evidencia por lote. Eso produce desconfianza y reclamos.
3. **Poca visibilidad para la exportadora.** Conoce la calidad del lote tarde y sin una forma independiente de verificarla.

## 3. Solución (lo que ya tenemos y lo que agrega la plataforma)

| Pieza | Estado |
|---|---|
| Detector YOLO26n entrenado (mAP50 0,908, recall 0,88 en `valid`) | Hecho |
| Tracking ByteTrack y conteo por línea (cada manzana se cuenta una vez) | Hecho, falta validar en video continuo |
| Detección de manzanas dañadas con el modelo (clase `damaged_apple`, F1 0,88 en validación) | Hecho |
| Semáforo de calidad: calibre 65–80 mm, color y forma | Hecho (reglas de negocio) |
| App de escritorio para la estación de la línea (`iniciar.bat`) | Hecho |
| **Plataforma web multi-rol**: lotes, validación, certificados y planes | **Nuevo** (`src/web/`) |

## 4. Lienzo del modelo de negocio (Business Model Canvas)

| Bloque | Contenido |
|---|---|
| **Segmentos** | Plantas de embalaje de manzanas (Maule y O'Higgins, principales zonas manzaneras); productores que les entregan fruta; exportadoras |
| **Propuesta de valor** | Packing: conteo automático, calidad en tiempo real y un informe por lote. Productor: transparencia y evidencia de cada lote. Exportadora: certificados verificables y un consolidado por proveedor y variedad |
| **Canales** | Venta directa a packings, piloto gratuito de 4 semanas, gremios del sector, ferias agrícolas. Los productores llegan invitados por su packing |
| **Relación** | Instalación y calibración en terreno, capacitación de operadores, panel de autoservicio, soporte |
| **Ingresos** | Suscripción por línea, instalación (pago único), plan Pro para productores, suscripción para exportadoras |
| **Recursos clave** | Modelo entrenado y pipeline de visión, datos propios etiquetados (crecen con cada lote validado), plataforma web, equipo técnico |
| **Actividades clave** | Instalar y calibrar (`px_por_mm`), operar la plataforma, validar y reentrenar el modelo, vender |
| **Socios clave** | Proveedores de cámaras e iluminación, nube (AWS S3 ya integrado en `s3_helper.py`), Ultralytics (licencia), DUOC UC (piloto) |
| **Costos** | Equipo, kits de hardware, nube, licencia del modelo, etiquetado de datos, ventas |

## 5. Planes y precios (supuestos, CLP + IVA)

| Plan | Para | Precio | Incluye |
|---|---|---|---|
| Productor Básico | Productor | Gratis | Reportes de sus lotes y 10 análisis rápidos de foto al mes |
| Productor Pro | Productor | $9.990 / mes | 300 análisis de foto al mes y descarga de reportes CSV |
| Packing | Planta de embalaje | $290.000 / mes **por línea** + instalación $1.500.000 por línea | Análisis de video y foto ilimitado, panel de planta, validación, certificados, usuarios ilimitados |
| Exportadora | Exportadora | $190.000 / mes | Lotes certificados de sus proveedores, consolidado por variedad, verificación y descarga CSV |

La instalación cubre cámara industrial, iluminación, mini PC en la línea, calibración y capacitación.

## 6. Roles en la plataforma

Cada actor del negocio es un rol con permisos propios:

| Rol | Quién es | Qué hace | Plan |
|---|---|---|---|
| **Administrador** | Equipo AppleVision | Crea empresas y usuarios, asigna planes, aprueba solicitudes de cambio de plan y ve las métricas del negocio (ingreso mensual, uso) | Interno |
| **Jefe de planta** | Supervisor de calidad del packing | Ve el panel de su planta, **valida el conteo** con un conteo manual, aprueba o rechaza lotes (al aprobar se emite el certificado) y administra a sus operadores | Packing |
| **Operador de línea** | Trabajador del packing | Recibe el lote, sube la foto o el video de la línea y ve el resultado del modelo | Packing |
| **Productor** | Agricultor que entrega fruta | Ve sus lotes con la evidencia y hace análisis rápidos de fotos, con cuota según su plan | Básico / Pro |
| **Exportadora** | Comprador o exportador | Ve los lotes certificados que van a su nombre, verifica certificados y descarga reportes | Exportadora |
| Público | Cualquier persona | Verifica un certificado con su código, sin cuenta | — |

**Flujo de un lote:**

```
Productor entrega   ->  Operador recibe y      ->  Jefe de planta valida    ->  Certificado AV-2026-XXXXXX
la fruta                analiza (YOLO)             (conteo manual) y aprueba     visible para productor y exportadora
                                                                                 verificable por cualquiera
```

## 7. Ventaja competitiva

- **Ciclo de datos.** Cada vez que un jefe de planta ingresa un conteo manual, se genera la verdad de terreno que hoy le falta al proyecto (README: "falta un video continuo con su conteo manual"). Con más clientes llegan más datos, el modelo mejora y el servicio vale más.
- **Efecto de red.** El certificado conecta packing, productor y exportadora. Mientras más actores lo usan, más vale estar dentro.
- **Costo de entrada bajo.** Una cámara y un mini PC por línea, en vez de una máquina calibradora completa.

## 8. Números del negocio (ejemplo con supuestos)

**Por línea:** precio $290.000 / mes. Costo variable estimado $70.000 / mes (nube, soporte y hardware amortizado). Margen de contribución $220.000 (≈ 76 %).

**Punto de equilibrio:** con costos fijos estimados en $5.000.000 / mes (equipo de 3 personas, herramientas y licencia prorrateada), se necesitan 5.000.000 / 220.000 ≈ **23 líneas**, unas 10 plantas de 2 a 3 líneas.

| Escenario | Líneas | Exportadoras | Productores Pro | Ingreso mensual | Ingreso anual |
|---|---:|---:|---:|---:|---:|
| Año 1 | 10 | 2 | 40 | $3.679.600 | ≈ $44,2 M |
| Año 2 | 30 | 6 | 150 | $11.338.500 | ≈ $136,1 M |

El año 1 queda bajo el punto de equilibrio. Se financia con fondos de emprendimiento (por ejemplo, CORFO Semilla Inicia o Start-Up Chile) y con los ingresos por instalación.

## 9. Indicadores (KPI)

Los que muestra la plataforma: ingreso mensual recurrente (MRR), empresas y usuarios activos, análisis por día, lotes certificados, % Buena / % No pasa por planta y error del conteo automático contra el manual.

Los que hay que medir aparte: tasa de abandono (*churn*), paso de plan Básico a Pro, tiempo de instalación y satisfacción (NPS).

## 10. Riesgos y cómo mitigarlos

| Riesgo | Mitigación |
|---|---|
| **Licencia AGPL-3.0 de Ultralytics YOLO.** Ofrecerlo como servicio cerrado obliga a publicar el código bajo AGPL | Antes de cobrar: comprar la licencia Enterprise de Ultralytics, publicar el código bajo AGPL, o migrar a un detector con licencia permisiva y reentrenar |
| **Precisión no validada en la línea.** El conteo con tracking aún no se comparó con un conteo manual en video continuo | Piloto con conteo manual. La plataforma ya registra el error de cada lote validado |
| **Calibración por línea.** Si la cámara se mueve, el calibre (mm) deja de ser confiable | Calibrar en la instalación y recalibrar en cada mantención (botón «Calibrar» de la app de escritorio) |
| **El daño se aprendió con fotos de montones, no de la cinta** | El modelo de 2 clases ya detecta el daño (F1 0,88 en validación, contra 0,34 de la regla de color). Falta etiquetar manzanas dañadas en video propio de la cinta. Mientras tanto, presentarlo como apoyo a la inspección |
| **El certificado no es oficial** | Indicar siempre que es un informe de conteo y calidad visual que **no reemplaza la inspección del SAG** |
| Estacionalidad de la cosecha | Planes anuales con descuento. La fruta guardada en frío se embala durante varios meses |
| Licencias de datos | Dataset 1: dominio público. Dataset 2: CC BY 4.0, uso comercial permitido dando crédito al autor |

## 11. Próximos pasos

1. **Piloto** en una planta (1 línea, 4 semanas): grabar video propio, ingresar conteos manuales y medir el error con `validar_conteo` y con la validación del jefe de planta.
2. **Decidir la licencia** del detector (Enterprise, AGPL o migrar).
3. **Producto:** conteo en vivo con cámara desde la web (equipo en la línea), certificado en PDF con código QR e integración con el sistema de gestión del packing.
4. **Modelo:** el daño ya lo detecta el modelo de 2 clases. Falta reentrenar con video de la planta y entrenar el resto de la calidad (calibre y color) con etiquetas reales, por ejemplo con Random Forest o XGBoost.
5. **Validar precios** con al menos 10 entrevistas a packings, productores y exportadoras.
