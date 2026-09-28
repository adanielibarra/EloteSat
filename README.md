# EloteSat Tamaulipas

Antes se llamaba **FenoSat** (versiones 0.1.0 a 0.4.0).

Versión 0.4.1 (experimental). Herramienta para distinguir el maíz del sorgo y de otros cultivos en Tamaulipas, en dos pasos: 1) maíz + sorgo frente a otros; 2) maíz frente a sorgo (por separado o a la vez). Descarga Sentinel-2 L2A y Landsat 8/9 Collection 2 Level-2 recortados a una zona de estudio, los ordena por etapa según un calendario editable, calcula variables en ventanas relativas a la curva de NDVI de cada píxel (su propio arranque y su propio máximo, no fechas fijas), y ofrece exploración sin etiquetas, separabilidad con umbrales y Random Forest con validación por parcela. Ocho pestañas: Inicio, 1 · Calendario, 2 · Descarga, 3 · Variables, 4 · Grupos, 5 · Muestras, 6 · Clasificación, 7 · Mapas SIAP. Interfaz en español e inglés. QGIS 3.28 o superior. Sin dependencias obligatorias (GDAL y numpy, que ya trae QGIS; scikit-learn opcional).

## Instalar

QGIS → Complementos → Administrar e instalar → Instalar a partir de ZIP → `elotesat_v0.4.3.zip`. Sale en tres sitios: el menú **EloteSat** de la barra de menús (junto a Ayuda, con acceso directo a cada pestaña), su propia barra de herramientas (icono de la mazorca) y **Ráster → EloteSat Tamaulipas**.

## Novedades 0.4.3

- Arranca siempre en español, sea cual sea el idioma de QGIS. El inglés se elige en Inicio y se recuerda.
- Pestaña final **Ayuda** (también en el menú EloteSat) con el manual en PDF: botón para guardarlo donde quieras y otro para abrirlo. El PDF va en `docs/`.

## Novedades 0.4.2

- Menú propio **EloteSat** en la barra de menús, con una entrada por pestaña, y barra de herramientas propia. Antes solo estaba en Ráster y en la barra de Ráster, que muchas veces está oculta.

## Novedades 0.4.1

- **Pestaña 7 · Mapas SIAP**, traída de la variante 0.4.0 de Claudia y Daniel: mapas por municipio de cualquier variable del Avance (sembrada, cosechada, siniestrada, producción, rendimiento, % siniestrado, fecha de la mitad de la siembra o de la cosecha), por ciclo, año, modalidad, cultivo y corte, con estilo graduado o por meses, etiquetas y composición de impresión A4 (título, leyenda, escala, norte, logo y fuentes). Exporta CSV.
- **Las descargas del SIAP se guardan en la carpeta del perfil de QGIS** (`EloteSat/siap/`), también idea de esa variante: sobreviven a las actualizaciones del plugin, los datos incluidos no se tocan y tanto los perfiles como los mapas las leen solas (un corte descargado sustituye al incluido).
- **Nuevo nombre: EloteSat Tamaulipas** (antes FenoSat). Al abrirlo por primera vez copia la configuración de FenoSat (perfiles, idioma, carpetas) y lee las descargas del SIAP que se hicieran con el nombre antiguo. Es un complemento distinto para QGIS: conviene desinstalar FenoSat.
- Pruebas: `tests/test_maps.py` (20 comprobaciones con los datos reales) `tests/test_migrate.py` (3) y `tests/test_plugin.py` (12).

## Novedades 0.4.0

- **Perfiles desde el SIAP** (pestaña 1, *Crear perfiles desde el SIAP*): uno por municipio y modalidad (riego o temporal), sin cultivo, sumando maíz y sorgo. De cada ciclo salen las fechas en que la siembra acumulada pasa del 10, 50 y 90 % y la cosecha del 50 y 90 %, con la mediana de los años disponibles. Las etapas: `00` de la siembra al 10 % a la siembra al 90 % + 10 días; `03` de 30 días antes de la cosecha al 50 % a la cosecha al 90 %; `01` y `02`, mitad y mitad de lo de en medio. **Los 10 días, los 30 días y el reparto a partes iguales son supuestos.** La tabla de etapas tiene una columna **Origen** (siap, estimada o manual; al editar una etapa pasa a manual).
- **Avisos del SIAP** en cada perfil: ciclos sin arranque en la exportación, un corte que cierra la serie con más del 50 % de la siembra (posible cierre administrativo) y ciclos de siembra a cosecha de menos de 90 días (REVISAR: la fecha del Avance puede ser la de registro, no la de siembra). Hoy salen así El Mante, González y Llera en riego OI y Altamira en temporal PV.
- **Año del SIAP frente al de EloteSat**: en el SIAP, el OI 2025 se siembra de octubre de 2024 a marzo de 2025 (año del final); en EloteSat el año es el de la primera etapa. La pestaña 2 muestra la equivalencia junto al año.
- **Asignar por zona** (pestaña 2): el perfil del municipio que más ocupa la zona de estudio; riego si al menos la mitad cae en distritos de riego, si no temporal. Avisa si pilla varios municipios, si mezcla dentro y fuera de distrito o si cae fuera de Tamaulipas.
- **Referencias por cultivo desde el SIAP**, ahora por ciclo: arranque y máximo = [siembra al 10 % de ese cultivo + desfase mínimo, siembra al 90 % + desfase máximo]. Los desfases son **supuestos, vacíos por defecto**; sin ellos no se rellena nada.
- **`zonas.tif`** con el `cvegeo` y el distrito de riego de cada píxel.
- **Superficie del mapa frente a la sembrada del SIAP** (pestaña 6), por municipio y modalidad, mismo ciclo y año del SIAP: tabla en el informe y `<esquema>_superficies_siap.csv`. Es una comprobación de coherencia, no una validación; el cociente solo se da si el mapa cubre al menos el 90 % del municipio.
- **Actualizar desde el SIAP** (pestaña 1): el `descarga_siap.py` de Claudia y Daniel convertido en módulo. Pide los años agrícolas, planifica las consultas de los dos años que hacen falta por ciclo, guarda cada respuesta en `siap_crudos/`, casa los municipios por nombre y rehace los perfiles juntando lo descargado con los datos del plugin. La web parece responder solo desde México: hay que usar una VPN con salida en México. **No se ha podido probar contra el servidor**; se ha probado con una respuesta sintética que imita la estructura que espera el lector.
- Logo nuevo (maíz cohete), correo de la UAT en metadata.txt.

## Novedades 0.3.0

- **Ventanas relativas a la curva de cada píxel** (pestaña 3, por defecto): las medianas de bandas e índices se toman alrededor del arranque, del máximo, de 20 a 40 días después del máximo y de la bajada de cada píxel. Cada parcela se compara en la misma fase aunque se sembrara otro día. Las etapas fijas de las carpetas quedan como opción, solo para comparar.
- **Métricas de forma** de la curva: amplitud, velocidad de subida y de bajada, días del arranque al máximo, duración, NDVI máximo y medio. Las fechas absolutas (día de arranque, máximo y bajada) pasan a ser opcionales.
- **Perfiles de calendario por región**, guardables (duplicar, renombrar, borrar, importar, exportar) y elegibles en las pestañas 1 y 2. Cada descarga guarda el perfil usado (`perfil.json`).
- **Referencias por cultivo** en cada perfil (ventanas esperadas de arranque y máximo del maíz y del sorgo), **solo para interpretar**: `referencia.tif` y una columna en la pestaña 4. No ordenan imágenes ni entran en ningún modelo. Vienen vacías.
- Clasificación: los huecos se marcan con un valor fuera de rango (−9999) en lugar de la mediana, porque ahora "sin dato" suele ser información (p. ej. sin arranque dentro de la temporada). Mínimo de variables con dato por defecto: 50 %.

## Datos incluidos

`data/tamaulipas_elotesat.gpkg` (1,1 MB):

- `municipios`: los 43 municipios de Tamaulipas de **Who's On First** (geometría de **Quattroshapes**, CC-BY), con la clave INEGI en `cvegeo` y el nombre con tildes. Simplificados a 30 m como cobertura (sin huecos ni solapes entre vecinos; la superficie cambia menos de un 0,02 %). Es obligatorio enlazar la licencia de Who's On First: https://whosonfirst.org/docs/licenses/.
- `siap_avance`: el Avance de Siembras y Cosechas del SIAP por municipio para maíz grano y sorgo grano, riego y temporal, cortes mensuales de 2023 a 2025 (4.478 filas, 38 municipios con datos), con `cvegeo`. Descargado por Daniel Ibarra-Marinas el 28/09/2026. Licencia y forma de citar del SIAP: [VERIFICAR].
- `distritos_riego`: los 7 distritos de riego de **CONAGUA**, vía el servicio INFOTECA de SEMARNAT, año agrícola 2016-2017, sin recortar y simplificados a 30 m.

Al calcular variables (pestaña 3) se escribe además `variables/zonas.tif`: banda 1, `cvegeo` del municipio de cada píxel; banda 2, distrito de riego (código en `zonas.csv`); 0 fuera. Un píxel va al polígono que contiene su centro.

Ojo con los distritos como indicador de riego: el perímetro incluye tierra sin derecho a riego, deja fuera los cascos urbanos (Río Bravo cae en un hueco entre el 025 y el 026) y hay riego fuera de los distritos (unidades de riego).

## Pestaña 1 · Calendario

- **Perfiles**: cada perfil es el calendario de una región (los dos ciclos) más sus referencias por cultivo. Viene uno, `generico_VERIFICAR`; duplícalo para cada región (p. ej. `norte_riego`, `centro_sur_temporal`) y ajusta las fechas. Se elige aquí o en la pestaña 2, según la zona de estudio. Un calendario guardado con la 0.1 o la 0.2 se conserva como perfil `mi_calendario`. Exportar/Importar guarda o carga un perfil en JSON; también se puede importar el `calendario.json` de un ciclo descargado.
- **Referencias por cultivo** (tabla maíz/sorgo: arranque desde/hasta, máximo desde/hasta, MM-DD). Se rellena o las dos fechas o ninguna. Sirven para ver si la curva de un píxel o de un grupo encaja con lo esperado. No sirven para ordenar imágenes (habría que saber ya el cultivo) ni entran en la clasificación.

- Dos ciclos, **OI** y **PV**, cada uno con cuatro etapas (una carpeta por etapa): `00_siembra_emergencia`, `01_vegetativo`, `02_floracion_espigamiento`, `03_madurez_senescencia`.
- Cada etapa es una ventana MM-DD. Un ciclo puede cruzar el año: lo que cae antes del inicio de la primera etapa va al año siguiente. No se admiten solapes (una fecha, una carpeta); los huecos sí, y esas fechas van a `fuera_de_etapa`.
- Se guarda solo en la configuración de QGIS; se puede exportar e importar en JSON. Una edición que no valida no se guarda y se avisa en rojo.
- **Reordenar carpeta**: si cambias las ventanas después de descargar, mueve los ficheros del ciclo y año elegidos a sus nuevas carpetas. Nunca sobrescribe (si el destino existe, lo deja y lo avisa), actualiza `manifest.csv` y `calendario.json`, rehace los mosaicos y borra las carpetas que quedan vacías.

### Calendario de fábrica: SIN VERIFICAR

| Ciclo | 00 siembra-emergencia | 01 vegetativo | 02 floración-espigamiento | 03 madurez-senescencia |
|---|---|---|---|---|
| OI (riego, norte) | 01-15 a 02-28 | 03-01 a 04-10 | 04-11 a 05-15 | 05-16 a 07-15 |
| PV (temporal, centro-sur) | 06-15 a 07-31 | 08-01 a 09-10 | 09-11 a 10-15 | 10-16 a 12-15 |

Lo he escrito de memoria a partir de lo que sé en general del calendario agrícola de Tamaulipas, **no sale de ninguna fuente comprobada** [VERIFICAR con el SIAP, SADER o el calendario de los DR 025/026]. Además, maíz y sorgo no llevan exactamente el mismo ritmo, y el calendario es uno solo para la zona.

## Pestaña 2 · Descarga

Las ventanas de las etapas se ven y **se editan también aquí** (tabla con fecha de inicio y fin). Es el mismo calendario de la pestaña 1: se guarda solo, se valida igual (sin solapes) y, si cambias el inicio de la primera etapa o el fin de la última, las fechas de búsqueda se ajustan. Se guarda día y mes: vale para todos los años.

1. **Zona de estudio**: capa de polígonos (todas o las seleccionadas), en cualquier SRC. Se recorta al rectángulo de la unión de polígonos más el margen, pero la cobertura y las nubes se miden dentro del polígono.
2. **Ciclo y año**: las fechas de búsqueda salen del calendario (se pueden cambiar). La tabla dice a qué etapa va cada escena.
3. **Fuentes**:

| Sensor | Fuente | Colección | Acceso |
|---|---|---|---|
| Sentinel-2 L2A | Earth Search (Element 84) | `sentinel-2-c1-l2a` | anónimo |
| Sentinel-2 L2A | Planetary Computer (Microsoft) | `sentinel-2-l2a` | token SAS anónimo, lo pide el plugin |
| Landsat 8/9 C2 L2 | Planetary Computer | `landsat-c2-l2` | token SAS anónimo |
| Landsat 8/9 C2 L2 | Earth Search + bucket `usgs-landsat` | `landsat-c2-l2` | **requester pays**: claves de AWS, la transferencia se cobra a tu cuenta |

   Landsat 7 y anteriores se descartan (en el filtro de la búsqueda y otra vez en el cliente).

4. **Filtros**:
   - Nubes máx. de tesela (60 %): filtro grueso del catálogo.
   - **Cobertura** mín. de la zona (10 %): píxeles con datos / tamaño del polígono entero (también la parte fuera de la tesela). Evita bajar esquinas sueltas.
   - **Despejado** mín. (60 %): de lo cubierto, cuánto está libre. S2: SCL 4, 5, 6, 7. Landsat: QA_PIXEL con los bits 0 (relleno), 1 (nube dilatada), 2 (cirro), 3 (nube), 4 (sombra) y 5 (nieve) a cero.
5. Por escena, primero baja **solo la máscara** del recorte. Si no pasa los filtros, no baja nada más.
6. Tamaño: la etiqueta da una cota superior sin comprimir de todo lo listado. Úsala antes de lanzar Tamaulipas entero.

## Qué sale

```
carpeta/
  OI_2026/
    manifest.csv  calendario.json  parametros.txt
    00_siembra_emergencia/
      S2/        S2_20260210_14RPP_S2A_10m.tif, S2_..._20m.tif, MOS_S2_20260210_10m.vrt
      LANDSAT/   LS_20260212_026042_L9_30m.tif
    01_vegetativo/ ...
    fuera_de_etapa/ ...
```

- S2: 10 m (B02 B03 B04 B08) y 20 m (B05 B06 B07 B8A B11 B12 SCL), en la malla nativa, sin remuestrear; la ventana se ajusta a 20 m desde el origen de la tesela, así 10 y 20 m encajan.
- Landsat: 30 m (SR_B2 a SR_B7 por defecto, SR_B1 opcional, y QA_PIXEL siempre). Ventana ajustada a la malla de 30 m.
- UInt16 con **scale y offset en cada banda**: reflectancia = DN × scale + offset. Se leen del catálogo (`raster:bands`); si no vienen: S2, convención ESA (offset −0,1 desde baseline 04.00; si no hay baseline, el offset queda vacío y se avisa); Landsat, 0,0000275 y −0,2 (constantes de la USGS para C2 L2 [VERIFICAR con la guía]).
- **Nodata**: GeoTIFF solo guarda uno por fichero, así que es 0 para todas las bandas. En QA_PIXEL el relleno vale 1 (bit 0); hay que tratarlo con los bits, no con el nodata del fichero. Los mosaicos sí llevan nodata por banda (0, y 1 para QA_PIXEL).
- **Mosaicos**: si una fecha necesita varias teselas del mismo SRC, un `MOS_<sensor>_<fecha>_<res>.vrt` con rutas relativas (se puede mover la carpeta). Con SRC distintos no se hace y se avisa. Tamaulipas cae entero en UTM 14 si no me equivoco (≈ 100 a 97 °O) [VERIFICAR con los datos reales: alguna tesela de borde podría venir en otra zona].
- `manifest.csv` (por ciclo): escena, sensor, fuente, fecha, tesela o path/row, etapa, nubes de tesela, % cubierto y % despejado en la zona, estado y motivo de descarte, SRC, límites, ficheros, scale/offset, histograma de la máscara.
- `parametros.txt`: todos los parámetros de cada descarga (se añaden, no se pisan). `calendario.json`: el calendario usado.

## Decisiones por defecto (cámbialas si no te convencen)

| Parámetro | Valor | Dónde |
|---|---|---|
| Nubes máx. de tesela | 60 % | pestaña 2 |
| Cobertura mín. de la zona | 10 % | pestaña 2 |
| Despejado mín. | 60 % | pestaña 2 |
| Margen | 0 m | pestaña 2 |
| Clases SCL despejadas | 4, 5, 6, 7 | `core/sensors.py` |
| Bits QA_PIXEL que descartan | 0 a 5 | `core/sensors.py` |
| Malla de ajuste | 20 m (S2), 30 m (Landsat) | `core/sensors.py` |
| Añadir al mapa | no (con una zona grande serían muchas capas) | pestaña 2 |

## Lo que hay que tener claro

- **Las carpetas agrupan por fecha; la fenología va por parcela.** Con siembras escalonadas, una misma imagen pilla parcelas en etapas distintas. Por eso, desde la 0.3.0, la pestaña 3 trabaja por defecto con ventanas relativas a la curva de cada píxel y las carpetas solo ordenan la descarga.
- **Hay un calendario por perfil, no por cultivo.** El calendario decide carpetas y fechas de búsqueda; el cultivo no se conoce al descargar. Lo específico de cada cultivo va en las referencias, solo para interpretar.
- **S2 y Landsat no están armonizados.** Bandas y respuestas espectrales distintas, y Landsat a 30 m. No mezcles sus valores en un mismo análisis sin corregirlos (por ejemplo con los coeficientes de HLS). Por eso van en subcarpetas separadas.
- En Planetary Computer, S2 L2A a partir de la baseline 04.00 lleva el offset de −1000 en los DN. El plugin lo aplica con la convención ESA porque ese catálogo no declara `raster:bands`. [VERIFICAR en la primera prueba real.]


# Pestaña 3 · Variables

Pasa un ciclo descargado a una malla común (20 m por defecto; lo más fino se promedia, Landsat se interpola bilineal) y calcula, **por sensor y sin mezclarlos** (prefijos `S2_` y `LS_`). Observaciones despejadas: S2, SCL 4 y 5; Landsat, bits 0-5 de QA_PIXEL a cero. Varias teselas de una fecha cuentan como una observación.

**1. Curva de NDVI de cada píxel** (base de todo lo demás). Se quitan caídas de más de 0,10 frente a las dos fechas vecinas (nube no detectada), se interpola cada 5 días sin extrapolar y se suaviza con media de 3. Hacen falta al menos 4 fechas limpias. Momentos de la curva: arranque (`DIAsube50`, cuando sube del 50 % de la amplitud), máximo (`DIAmax`) y bajada (`DIAbaja50`). Días contados desde el inicio de la primera etapa del ciclo.

**2. Ventanas relativas** (por defecto). Mediana de cada banda e índice (NDVI, GCVI, NDMI, NDTI y, solo S2, NDRE y CIre) en las fechas que caen dentro de la ventana, medida desde el momento propio de cada píxel:

| Ventana | Desde | Días |
|---|---|---|
| `REL1_arranque` | arranque | −10 a +10 |
| `REL2_maximo` | máximo | −10 a +10 |
| `REL3_postmax` (espigamiento, llenado) | máximo | +20 a +40 |
| `REL4_bajada` | bajada | −10 a +10 |

Los días se cambian en la pestaña. En Landsat las ventanas se ensanchan 8 días por cada lado, porque pasa cada 8 a 16 días. Un píxel sin ese momento (curva plana, o que arranca antes de empezar el ciclo) queda sin dato en esa ventana. `nobs.tif` dice cuántas fechas limpias entraron en cada ventana.

**3. Forma de la curva** (por defecto): `NDVImax`, `AMPLITUD` (máximo menos la base antes del máximo), `VELsube` y `VELbaja` (máxima subida y bajada, NDVI por día), `DIASsubemax` (días del arranque al máximo), `DUR50` (días por encima del 50 %) y `NDVImedio`. No dependen de la fecha de siembra.

**4. Opcionales**: fechas absolutas (`DIAsube50`, `DIAmax`, `DIAbaja50`) como variables, que a escala local pueden ayudar pero mezclan siembra y cultivo y no se trasladan bien a otra región; y las etapas fijas del calendario (lo de la 0.2), solo para comparar.

**5. Referencias** (si el perfil las tiene): `referencia.tif`, por píxel: 1 encaja con maíz, 2 con sorgo, 3 con los dos, 4 con ninguno, 5 curva incompleta (sin arranque y no encaja por el máximo), 0 sin curva. Usa las del perfil guardado con la descarga (`perfil.json`) o, si no hay, las del perfil actual, y la pestaña dice cuáles.

Salida en `<ciclo>/variables/`: `variables.tif` (Float32, una banda por variable, nodata NaN), `variables.csv`, `nobs.tif`, `referencia.tif` y `parametros.txt`. Se procesa por bloques de filas; con ventanas relativas los bloques son más pequeños porque hay que tener todas las fechas a la vez.

# Pestaña 4 · Grupos (sin datos de campo)

k-means (numpy) sobre las variables que elijas, tipificadas; por defecto NDVI por etapa y curva de S2. Mapa `grupos/grupos_kN.tif` con estilo; tabla con superficie, NDVI máximo, duración, días del arranque al máximo y, si hay `referencia.tif`, la referencia dominante del grupo con su porcentaje; perfil medio por ventana (relativas o fijas); CSV con las medias de todas las variables y el recuento de referencias. **Los grupos no son cultivos.** En las pruebas sintéticas los grupos de maíz y sorgo se separaban por fecha de siembra, no por cultivo: es justo lo que hay que esperar.

# Pestaña 5 · Muestras y separabilidad

- Capa de polígonos o puntos con el cultivo. Cada valor se asigna a maíz, sorgo, otros o ignorar (propone por el nombre). Campo de parcela para validar por parcela. Margen interior (10 m), radio de puntos y tope de píxeles por parcela. Guarda `muestras/muestras.csv`.
- Separabilidad para el paso 1 o el paso 2, por píxel o por parcela (mediana): distancia de Jeffries-Matusita (0 a 2, supuesto gaussiano) y mejor umbral por acierto equilibrado. Histogramas por clase, umbral movible con recuento de aciertos y confusiones, y **Regla al mapa**.
- **Mejor combinación**: selección paso a paso por JM multivariante (salta variables con r > 0,95 con una ya elegida); se puede mandar a la pestaña 6.
- Ojo: por píxel, los píxeles de una parcela no son independientes y la separabilidad sale optimista. JM engaña con clases bimodales (p. ej. "otros" mezclando cultivos).

# Pestaña 6 · Clasificación

- Random Forest: scikit-learn si está instalado (clases equilibradas, hilos, no procesos); si no, uno propio en numpy, más lento.
- Jerárquica (paso 1: maíz+sorgo frente a otros; paso 2: maíz frente a sorgo, entrenado solo con maíz y sorgo; P(maíz) = P1 × P2) y/o plana (3 clases).
- Validación cruzada **por parcela**, estratificada (cada parcela entera en un pliegue). Matriz por píxel y por parcela (voto), exactitud del paso 1 y del paso 2, productor y usuario por clase. Importancia por permutación en los pliegues de validación, separada para el paso 1 y el 2 (con variables muy correlacionadas se reparte y puede salir cerca de 0).
- Mapa `clasificacion/<esquema>_clases.tif` (1 maíz, 2 sorgo, 3 otros, 0 sin dato) con estilo, `_prob.tif` (0-100 por clase), filtro 3x3 opcional, informe JSON, confusión e importancia en CSV. Un píxel sin al menos el 50 % de las variables queda sin clase; el resto de huecos se marca con −9999 para que los árboles traten «sin dato» como información.
- La superficie contada en el mapa arrastra los errores de clasificación; para estimar áreas hay que corregirla con una muestra independiente (Olofsson et al. 2014 [VERIFICAR la cita]).

## Probado y no probado

**Probado** (QGIS 3.34 / GDAL 3.8, Linux, sin red): 264 comprobaciones en 9 ficheros: `tests/test_core.py` (56), `tests/test_gui.py` (42), `tests/test_analysis.py` (61), `tests/test_gui2.py` (25), `tests/test_zones.py` (12), `tests/test_siap.py` (33), `tests/test_maps.py` (20) `tests/test_migrate.py` (3) y `tests/test_plugin.py` (12). Las de SIAP y zonas usan los **datos reales** del plugin (Avance 2023-2025 y capas de municipios y distritos); el resto, datos sintéticos. Los datos sintéticos (`tests/synth.py`) son un banco de pruebas de fontanería, con curvas y espectros inventados: que ahí acierte casi el 100 % no dice nada de cómo irá con parcelas reales.

- Fase 1: calendario, catálogo, token de PC, recorte, máscaras, mosaicos, reordenar, descarga con el gestor de tareas, y edición de las fechas de etapa desde la pestaña 2 (con rechazo de solapes).
- Fase 2: métricas de la curva sobre una curva conocida (con nube, con fechas perdidas y con pocas fechas), JM contra su fórmula, umbrales en los dos sentidos, pliegues sin fuga de parcelas, filtro 3x3, bosque numpy y paso automático a numpy sin scikit-learn. Métricas de forma: velocidad de subida contra la fórmula de la doble logística, y las mismas métricas con una siembra 30 días más tarde (la forma no cambia, las fechas se mueven 30 días). Referencias: conversión a días del ciclo (también cruzando el año), códigos de coherencia y rechazo de referencias a medias. Con siembras escalonadas (desviación de 20 días) el CIre por ventana relativa separa maíz y sorgo con JM 2,00, y por etapa fija 0,16: justo lo que se busca, aunque en datos inventados para eso. Perfiles: duplicar, cambiar desde la pestaña 2, ediciones solo en el perfil actual, renombrar, borrar, migración del calendario antiguo y `perfil.json` con la descarga. Con un caso sintético "difícil" (maíz y sorgo con la misma curva de NDVI, distintos solo en red-edge) la tabla de JM y la importancia del paso 2 señalan el red-edge, como deben. Muestras de polígonos, puntos y margen, mapa de clases y probabilidades, píxeles sin datos, grupos y la cadena completa desde las pestañas.

- 0.4.0: las 320 series del SIAP son acumuladas; el CSV casado por nombre da las mismas filas que la tabla con `cvegeo`; ancla del arranque y cortes a cero; interpolación del 10 y 90 %; aviso solo para saltos que cierran la serie; ciclos cortos marcados; año SIAP frente a EloteSat (OI de enero y de octubre); referencias vacías sin desfases y bien calculadas con ellos; asignación por zona (Matamoros riego en el DR 025, Soto la Marina temporal, el mar sin perfil); Río Bravo ciudad cae entre el 025 y el 026, fuera de ambos; plan de consultas, meses futuros saltados, lectura de la respuesta y reconstrucción desde `siap_crudos/`; superficies por municipio y modalidad y cociente omitido con poca cobertura; en QGIS, importar, asignar, columna de origen, rellenar referencias y el CSV de superficies.

**No probado**: ninguna conexión real (Earth Search, Planetary Computer y el bucket de la USGS estaban bloqueados desde mi entorno), Windows, rendimiento con zonas grandes y muchas escenas.

## Pendiente de verificar en la primera prueba real

- Nombres de assets y `raster:bands` en Planetary Computer (S2 y Landsat) y en `landsat-c2-l2` de Earth Search. Hay alternativas por `eo:bands`, pero conviene mirarlo.
- Que Planetary Computer acepte el filtro `query` de plataforma y nubes. Si lo ignora, el cliente vuelve a filtrar igual.
- Que GDAL abra las URL firmadas de PC con `/vsicurl/` sin problemas con la cadena del token.
- Proxy: la búsqueda y el token usan la red de QGIS, pero la lectura de los COG va por GDAL y **no hereda el proxy de QGIS**. En la UAT, si hay proxy, habría que definir `GDAL_HTTP_PROXY`.
- Calendario de fábrica: ver arriba.
- La descarga del SIAP contra el servidor real (solo responde desde México). Con la carpeta `siap_crudos/` de una descarga real se puede comprobar el lector sin red (`siap_download.parse_raw_dir`).
- Licencia y forma de citar del SIAP.
- Desfases siembra → arranque y siembra → máximo para maíz y sorgo en Tamaulipas (por eso van vacíos).
