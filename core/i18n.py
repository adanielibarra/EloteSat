"""Minimal ES/EN translation table for EloteSat (no Qt Linguist needed).

tr(key, *args) returns the text in the current language, formatted with
args. Unknown keys are returned as they are, so a missing entry is visible
but never breaks the plugin.
"""

LANGS = {"es": "Español", "en": "English"}
_lang = "es"


def set_lang(code):
    global _lang
    _lang = code if code in LANGS else "en"


def lang():
    return _lang


def tr(key, *args):
    entry = STRINGS.get(key)
    text = key if entry is None else entry[0 if _lang == "es" else 1]
    return text % args if args else text


def default_lang():
    """Spanish unless English was chosen in the Home tab (whatever the
    language of QGIS)."""
    try:
        from qgis.core import QgsSettings
        saved = QgsSettings().value("EloteSat/lang", "")
        return saved if saved in LANGS else "es"
    except Exception:
        return "es"


def save_lang(code):
    from qgis.core import QgsSettings
    QgsSettings().setValue("EloteSat/lang", code)


# key: (español, english)
STRINGS = {
    "win.title": ("EloteSat Tamaulipas", "EloteSat Tamaulipas"),
    "tab.home": ("Inicio", "Home"),
    "tab.calendar": ("1 · Calendario", "1 · Calendar"),
    "tab.download": ("2 · Descarga", "2 · Download"),
    "home.subtitle": ("Sentinel-2 y Landsat por etapa del cultivo",
                      "Sentinel-2 and Landsat by crop stage"),
    "home.version": ("Versión %s (experimental)", "Version %s (experimental)"),
    "home.language": ("Idioma", "Language"),
    "cancel": ("Cancelar", "Cancel"),
    "error": ("Error: %s", "Error: %s"),
    "sensor.S2": ("Sentinel-2 L2A", "Sentinel-2 L2A"),
    "sensor.LANDSAT": ("Landsat 8/9 C2 L2", "Landsat 8/9 C2 L2"),
    "src.es.s2": ("Earth Search (AWS), sin cuenta",
                  "Earth Search (AWS), no account"),
    "src.pc.s2": ("Planetary Computer (Microsoft), sin cuenta",
                  "Planetary Computer (Microsoft), no account"),
    "src.pc.ls": ("Planetary Computer (Microsoft), sin cuenta",
                  "Planetary Computer (Microsoft), no account"),
    "src.es.ls": ("Earth Search + bucket USGS (AWS, paga quien descarga)",
                  "Earth Search + USGS bucket (AWS, requester pays)"),

    # ---- calendar
    "cal.intro": (
        "Cada etapa es una ventana de fechas (MM-DD) y una carpeta. Las "
        "fechas de fábrica son un punto de partida sin verificar: "
        "ajústalas a tu zona.",
        "Each stage is a date window (MM-DD) and a folder. The default "
        "dates are an unverified starting point: adjust them to your "
        "area."),
    "cal.cycle": ("Ciclo", "Cycle"),
    "cal.year": ("Año del ciclo", "Cycle year"),
    "cal.col.stage": ("Etapa (carpeta)", "Stage (folder)"),
    "cal.col.start": ("Inicio MM-DD", "Start MM-DD"),
    "cal.col.end": ("Fin MM-DD", "End MM-DD"),
    "cal.add": ("Añadir etapa", "Add stage"),
    "cal.del": ("Quitar etapa", "Remove stage"),
    "cal.reset": ("Valores de fábrica", "Defaults"),
    "cal.reset.ask": ("¿Volver al calendario de fábrica? Se pierden tus "
                      "cambios.", "Go back to the default calendar? Your "
                      "changes will be lost."),
    "cal.import": ("Importar JSON", "Import JSON"),
    "cal.export": ("Exportar JSON", "Export JSON"),
    "cal.invalid": ("Calendario no válido (no se guarda): %s",
                    "Invalid calendar (not saved): %s"),
    "cal.preview": ("Ventanas de %s en %d:", "%s windows in %d:"),
    "cal.reorg.group": ("Reordenar una carpeta ya descargada",
                        "Reorganize a downloaded folder"),
    "cal.reorg.note": (
        "Mueve los ficheros del ciclo y año de arriba a las carpetas del "
        "calendario actual. Nunca sobrescribe. Actualiza manifest.csv y "
        "rehace los mosaicos.",
        "Moves the files of the cycle and year above to the folders of the "
        "current calendar. Never overwrites. Updates manifest.csv and "
        "rebuilds the mosaics."),
    "cal.reorg.dir": ("Carpeta de descarga", "Download folder"),
    "cal.reorg.run": ("Reordenar carpeta", "Reorganize folder"),
    "cal.reorg.done": ("Hecho: %d escenas movidas, %d ya estaban bien, "
                       "%d con problemas.", "Done: %d scenes moved, %d "
                       "already in place, %d with problems."),

    # ---- download
    "dl.aoi": ("Zona de estudio", "Study area"),
    "dl.layer": ("Capa de polígonos", "Polygon layer"),
    "dl.selected": ("Solo entidades seleccionadas", "Selected features only"),
    "dl.buffer": ("Margen", "Buffer"),
    "dl.buffer.tip": ("Margen alrededor de la zona para el recorte.",
                      "Margin around the area for the clip."),
    "dl.area": ("Superficie: %.0f km²", "Area: %.0f km²"),
    "dl.cycle.group": ("Ciclo", "Cycle"),
    "dl.cycle": ("Ciclo", "Cycle"),
    "dl.year": ("Año", "Year"),
    "dl.dates": ("Fechas", "Dates"),
    "dl.dates.to": ("a", "to"),
    "dl.search.group": ("Sensores y filtros", "Sensors and filters"),
    "dl.keys": ("Claves de AWS (solo Landsat en bucket de la USGS)",
                "AWS keys (Landsat in the USGS bucket only)"),
    "dl.key": ("Access key", "Access key"),
    "dl.secret": ("Secret key", "Secret key"),
    "dl.keys.note": (
        "No se guardan. Si las dejas vacías se usan AWS_ACCESS_KEY_ID y "
        "AWS_SECRET_ACCESS_KEY o ~/.aws/credentials. Ojo: la transferencia "
        "se cobra a esa cuenta.",
        "Not stored. If empty, AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY "
        "or ~/.aws/credentials are used. Note: the transfer is billed to "
        "that account."),
    "dl.cloud": ("Nubes máx. de tesela", "Max tile cloud"),
    "dl.cloud.tip": ("Filtro grueso del catálogo, sobre la tesela entera.",
                     "Coarse catalogue filter over the whole tile."),
    "dl.cover": ("Cobertura mín. de la zona", "Min cover of the area"),
    "dl.cover.tip": ("Parte de la zona con datos en esa tesela. Evita "
                     "bajar esquinas sueltas.", "Share of the area with "
                     "data in that tile. Avoids downloading slivers."),
    "dl.clear": ("Despejado mín. (de lo cubierto)",
                 "Min clear (of covered part)"),
    "dl.clear.tip": ("Píxeles sin nube, sombra ni nieve dentro del polígono "
                     "(SCL 4-7; QA_PIXEL bits 0-5 a cero).",
                     "Pixels free of cloud, shadow and snow inside the "
                     "polygon (SCL 4-7; QA_PIXEL bits 0-5 unset)."),
    "dl.search": ("Buscar escenas", "Search scenes"),
    "dl.col.sensor": ("Sensor", "Sensor"),
    "dl.col.date": ("Fecha", "Date"),
    "dl.col.tile": ("Tesela / path-row", "Tile / path-row"),
    "dl.col.sat": ("Satélite", "Satellite"),
    "dl.col.cloud": ("Nubes %", "Cloud %"),
    "dl.col.stage": ("Etapa", "Stage"),
    "dl.col.warn": ("Aviso", "Warning"),
    "dl.check.all": ("Marcar todas", "Check all"),
    "dl.check.none": ("Desmarcar todas", "Uncheck all"),
    "dl.count": ("%d escenas.", "%d scenes."),
    "dl.size": (" · Tamaño máx. sin comprimir: %.1f GB",
                " · Max uncompressed size: %.1f GB"),
    "dl.warn.dup": ("misma pasada que %s", "same pass as %s"),
    "dl.warn.missing": ("faltan %s", "missing %s"),
    "dl.warn.offset": ("offset desconocido", "unknown offset"),
    "dl.warn.nostage": ("fuera de las etapas", "outside the stages"),
    "dl.out.group": ("Bandas y salida", "Bands and output"),
    "dl.mosaic": ("Mosaico virtual por fecha", "Virtual mosaic per date"),
    "dl.mosaic.tip": ("Un VRT por fecha cuando la zona necesita varias "
                      "teselas del mismo SRC.", "One VRT per date when the "
                      "area needs several tiles in the same CRS."),
    "dl.addmap": ("Añadir al mapa", "Add to map"),
    "dl.outdir": ("Carpeta de salida", "Output folder"),
    "dl.run": ("Descargar seleccionadas", "Download checked"),
    "dl.msg.found": ("%d escenas de %s en %s.", "%d %s scenes in %s."),
    "dl.msg.searchfail": ("Falló la búsqueda de %s: %s",
                          "%s search failed: %s"),
    "dl.msg.dupfail": ("No se pudieron comprobar pasadas repetidas: %s",
                       "Could not check repeated passes: %s"),
    "dl.msg.start": ("Descargando %d escenas en %s", "Downloading %d scenes "
                     "into %s"),
    "dl.msg.end": ("Fin: %d guardadas, %d descartadas, %d con error.",
                   "End: %d saved, %d skipped, %d with errors."),
    "dl.msg.manifest": ("Manifiesto: %s", "Manifest: %s"),

    # ---- errors
    "err.nolayer": ("Elige una capa de polígonos.",
                    "Choose a polygon layer."),
    "err.nogeom": ("No hay geometrías (¿nada seleccionado?).",
                   "No geometries (nothing selected?)."),
    "err.notpoly": ("La zona no es un polígono.",
                    "The area is not a polygon."),
    "err.dates": ("La fecha inicial es posterior a la final.",
                  "Start date is after end date."),
    "err.nosensor": ("Marca al menos un sensor.",
                     "Check at least one sensor."),
    "err.noscenes": ("No hay escenas marcadas.", "No scenes checked."),
    "err.nodir": ("Elige una carpeta.", "Choose a folder."),
    "err.nobands": ("Marca al menos una banda de cada sensor que vayas a "
                    "descargar.", "Check at least one band of each sensor "
                    "you will download."),

    # ---- core
    "stac.net": ("Error de red: %s", "Network error: %s"),
    "stac.json": ("Respuesta no JSON: %s", "Non-JSON response: %s"),
    "stac.fail": ("Falló la búsqueda STAC: %s", "STAC search failed: %s"),
    "stac.unexpected": ("Respuesta inesperada: %s",
                        "Unexpected response: %s"),
    "stac.token": ("No se pudo obtener el token de Planetary Computer: %s",
                   "Could not get the Planetary Computer token: %s"),
    "core.outside": ("la zona cae fuera de la tesela",
                     "the area is outside the tile"),
    "core.nomask": ("falta la banda de máscara %s", "mask band %s missing"),
    "core.nosigner": ("falta el firmador de Planetary Computer",
                      "Planetary Computer signer missing"),
    "core.clear": ("%s: cubierto %.1f %%, despejado %.1f %%",
                   "%s: covered %.1f %%, clear %.1f %%"),
    "core.cover": ("cobertura %.1f %% < %.0f %%", "cover %.1f %% < %.0f %%"),
    "core.cloudy": ("despejado %.1f %% < %.0f %%",
                    "clear %.1f %% < %.0f %%"),
    "core.skipped": ("Descartada %s: %s", "Skipped %s: %s"),
    "core.error": ("Error en %s: %s", "Error in %s: %s"),
    "core.manifest": ("No se pudo escribir el manifiesto: %s",
                      "Could not write the manifest: %s"),
    "core.mos": ("Mosaico %s (%d teselas)", "Mosaic %s (%d tiles)"),
    "core.mos.crs": ("%s: teselas en SRC distintos (%s), sin mosaico",
                     "%s: tiles in different CRS (%s), no mosaic"),

    # ---- phase 2: common
    "tab.features": ("3 · Variables", "3 · Variables"),
    "tab.cluster": ("4 · Grupos", "4 · Groups"),
    "tab.samples": ("5 · Muestras", "5 · Samples"),
    "tab.classify": ("6 · Clasificación", "6 · Classification"),
    "cancelled": ("Cancelado.", "Cancelled."),
    "seed": ("Semilla", "Seed"),
    "cls.maiz": ("maíz", "maize"),
    "cls.sorgo": ("sorgo", "sorghum"),
    "cls.otros": ("otros", "other"),
    "cls.ignore": ("(ignorar)", "(ignore)"),
    "vl.all": ("Todas", "All"),
    "vl.none": ("Ninguna", "None"),
    "vl.indices": ("+ índices", "+ indices"),
    "vl.phen": ("+ curva NDVI", "+ NDVI curve"),
    "vl.s2": ("+ Sentinel-2", "+ Sentinel-2"),
    "vl.filter": ("filtrar…", "filter…"),

    # ---- tab 3
    "ft.intro": ('Pasa las imágenes de un ciclo a una malla común y calcula variables por píxel, por sensor y sin mezclarlos. Por defecto, en ventanas relativas a la curva de NDVI de cada píxel (su propio arranque y su propio máximo), así cada parcela se compara en la misma fase aunque se sembrara otro día. Las carpetas por fecha quedan solo para ordenar la descarga.',
        "Moves the images of one cycle onto a common grid and computes per-pixel variables, per sensor and never mixed. By default in windows relative to each pixel's NDVI curve (its own green-up and peak), so every field is compared at the same phase whatever its sowing date. Date folders only organize the download."),
    "ft.input": ("Ciclo descargado", "Downloaded cycle"),
    "ft.cycle": ("Carpeta del ciclo", "Cycle folder"),
    "ft.cycle.tip": ("La carpeta OI_2026 (o la que toque), con su "
                     "manifest.csv.", "The OI_2026 folder (or whichever), "
                     "with its manifest.csv."),
    "ft.info": ("Ciclo %s %d. Fechas con datos por etapa:",
                "Cycle %s %d. Dates with data per stage:"),
    "ft.noinfo": ("No se puede leer: %s", "Cannot read: %s"),
    "ft.opts": ("Qué calcular", "What to compute"),
    "ft.res": ("Malla", "Grid"),
    "ft.res.tip": ("20 m: la de las bandas red-edge de S2. Lo más fino se "
                   "promedia; lo más grueso (Landsat) se interpola "
                   "bilineal.", "20 m: the S2 red-edge grid. Finer bands "
                   "are averaged; coarser ones (Landsat) interpolated "
                   "bilinearly."),
    "ft.sensors": ("Sensores", "Sensors"),
    "ft.bands": ("Bandas (reflectancia)", "Bands (reflectance)"),
    "ft.phen": ('Forma de la curva NDVI',
        'NDVI curve shape'),
    "ft.phen.tip": ('Por píxel, con todas las fechas despejadas: NDVI máximo, amplitud, velocidad máxima de subida y de bajada (NDVI por día), días del arranque al máximo, duración por encima del 50 % y NDVI medio. No dependen de la fecha de siembra. Antes se quitan las caídas bruscas (nube no detectada).',
        'Per pixel, with every clear date: max NDVI, amplitude, steepest rise and fall (NDVI per day), days from green-up to peak, duration above 50 % and mean NDVI. They do not depend on the sowing date. Sudden drops (undetected cloud) are removed first.'),
    "ft.indices": ("Índices", "Indices"),
    "ft.scl": ("Clases SCL válidas", "Valid SCL classes"),
    "ft.scl.tip": ("4 vegetación, 5 suelo. Landsat: QA_PIXEL bits 0-5 a "
                   "cero.", "4 vegetation, 5 bare soil. Landsat: QA_PIXEL "
                   "bits 0-5 unset."),
    "ft.stages": ("Etapas", "Stages"),
    "ft.run": ("Calcular variables", "Compute variables"),
    "ft.done": ("%d variables en %s", "%d variables in %s"),
    "ft.err.cycle": ("Elige la carpeta de un ciclo descargado (con "
                     "manifest.csv).", "Choose a downloaded cycle folder "
                     "(with manifest.csv)."),
    "ft.err.scl": ("Clases SCL: números separados por comas.",
                   "SCL classes: comma-separated numbers."),
    "ft.err.empty": ("Marca al menos un sensor y una etapa.",
                     "Check at least one sensor and one stage."),

    # ---- tab 4
    "cl.intro": (
        "Sin datos de campo: agrupa píxeles parecidos (k-means). "
        "<b>Los grupos no son cultivos.</b> Sirven para ver cuántos "
        "calendarios distintos hay y decidir dónde ir a muestrear.",
        "No field data: groups similar pixels (k-means). <b>Groups are "
        "not crops.</b> They show how many different calendars there are "
        "and help decide where to sample."),
    "cl.vars": ("Variables", "Variables"),
    "cl.k": ("Número de grupos", "Number of groups"),
    "cl.n": ("Píxeles de muestra", "Sample pixels"),
    "cl.pick": ('Variables para agrupar (por defecto: NDVI por ventana y forma de la curva, S2)',
        'Variables to group on (default: NDVI per window and curve shape, S2)'),
    "cl.run": ("Agrupar", "Group"),
    "cl.col.g": ("Grupo", "Group"),
    "cl.col.km2": ("km²", "km²"),
    "cl.col.dmax": ("Día máx.", "Peak day"),
    "cl.col.up": ("Día sube 50 %", "Green-up day"),
    "cl.profile": ("Perfil:", "Profile:"),
    "cl.empty": ("Sin resultados todavía", "No results yet"),
    "cl.err": ("Elige el fichero de variables y al menos una variable.",
               "Choose the variables file and at least one variable."),
    "cl.done": ("Mapa: %s (%d píxeles sin todas las variables, sin grupo)",
                "Map: %s (%d pixels lacking some variable, no group)"),

    # ---- tab 5
    "sm.group": ("Muestras de campo", "Field samples"),
    "sm.layer": ("Capa (polígonos o puntos)", "Layer (polygons or points)"),
    "sm.field": ("Campo del cultivo", "Crop field"),
    "sm.gid": ("Campo de parcela", "Field id"),
    "sm.gid.tip": ("Identifica la parcela. Vacío: cada entidad es una "
                   "parcela. La validación deja fuera parcelas enteras.",
                   "Identifies the field. Empty: each feature is a field. "
                   "Validation holds out whole fields."),
    "sm.value": ("Valor", "Value"),
    "sm.class": ("Clase", "Class"),
    "sm.buf": ("Margen interior", "Inner buffer"),
    "sm.buf.tip": ("Quita el borde de la parcela (píxeles mezclados).",
                   "Removes the field edge (mixed pixels)."),
    "sm.rad": ("Radio puntos", "Point radius"),
    "sm.rad.tip": ("0: solo el píxel bajo el punto.",
                   "0: only the pixel under the point."),
    "sm.max": ("Máx. px/parcela", "Max px/field"),
    "sm.max.tip": ("0 = todos. Limita el peso de las parcelas grandes.",
                   "0 = all. Limits the weight of large fields."),
    "sm.extract": ("Extraer muestras", "Extract samples"),
    "sm.load": ("Cargar CSV", "Load CSV"),
    "sm.summary": ("maíz %d px (%d parcelas) · sorgo %d px (%d) · otros %d "
                   "px (%d).", "maize %d px (%d fields) · sorghum %d px "
                   "(%d) · other %d px (%d)."),
    "sm.rep": ("Ignoradas: %d sin clase, %d vacías tras el margen, %d "
               "fuera de la malla.", "Ignored: %d without class, %d empty "
               "after the buffer, %d outside the grid."),
    "sm.few": ("Pocas parcelas de %s (menos de 10): cualquier medida será "
               "muy inestable.", "Few fields of %s (fewer than 10): any "
               "measure will be very unstable."),
    "sm.err.input": ("Falta el fichero de variables, la capa o el campo.",
                     "Missing variables file, layer or field."),
    "sm.sep": ("Separabilidad", "Separability"),
    "sm.comp.c4": ("Paso 1: maíz + sorgo frente a otros",
                   "Step 1: maize + sorghum vs other"),
    "sm.comp.ms": ("Paso 2: maíz frente a sorgo",
                   "Step 2: maize vs sorghum"),
    "sm.unit.px": ("por píxel", "per pixel"),
    "sm.unit.field": ("por parcela (mediana)", "per field (median)"),
    "sm.a.c4": ("maíz+sorgo", "maize+sorghum"),
    "sm.b.c4": ("otros", "other"),
    "sm.col.var": ("Variable", "Variable"),
    "sm.col.rule": ("Umbral", "Threshold"),
    "sm.col.bal": ("Acierto equil.", "Balanced acc."),
    "sm.k": ("Variables:", "Variables:"),
    "sm.fwd": ("Mejor combinación", "Best combination"),
    "sm.fwd.res": ("Selección paso a paso (JM multivariante; salta "
                   "variables con r > 0,95 con una ya elegida):",
                   "Step-wise selection (multivariate JM; skips variables "
                   "with r > 0.95 to one already chosen):"),
    "sm.use": ("Usar en la clasificación", "Use in classification"),
    "sm.use.tip": ("Marca esas variables en la pestaña 6.",
                   "Checks those variables in tab 6."),
    "sm.thr": ("Regla:", "Rule:"),
    "sm.rule": ("Regla al mapa", "Rule to map"),
    "sm.rule.done": ("Mapa de la regla: %.2f km² la cumplen.",
                     "Rule map: %.2f km² meet it."),
    "sm.conf": ("Regla «%s si %s %s %.4g»: %s bien %d de %d (%.1f %%); "
                "%s confundidos %d de %d (%.1f %%).",
                "Rule '%s if %s %s %.4g': %s right %d of %d (%.1f %%); %s "
                "confused %d of %d (%.1f %%)."),
    "sm.empty": ("Sin muestras todavía", "No samples yet"),

    # ---- tab 6
    "cf.intro": (
        "Random Forest con las muestras de la pestaña 5. La validación "
        "deja fuera parcelas enteras (k pliegues por parcela), así que no "
        "se infla con píxeles vecinos de la misma parcela.",
        "Random Forest with the samples of tab 5. Validation holds out "
        "whole fields (k folds by field), so it is not inflated by "
        "neighbouring pixels of the same field."),
    "cf.samples": ("Muestras", "Samples"),
    "cf.nosamples": ("ninguna (pestaña 5)", "none (tab 5)"),
    "cf.modes": ("Esquema", "Scheme"),
    "cf.hier": ("Jerárquica", "Hierarchical"),
    "cf.hier.tip": ("Paso 1 maíz+sorgo frente a otros; paso 2 maíz frente "
                    "a sorgo, entrenado solo con maíz y sorgo.",
                    "Step 1 maize+sorghum vs other; step 2 maize vs "
                    "sorghum, trained only on maize and sorghum."),
    "cf.flat": ("Plana (3 clases)", "Flat (3 classes)"),
    "cf.engine": ("Motor", "Engine"),
    "cf.eng.auto": ("Automático (%s)", "Automatic (%s)"),
    "cf.eng.missing": (" (no instalado)", " (not installed)"),
    "cf.eng.numpy": ("numpy (propio, más lento)", "numpy (own, slower)"),
    "cf.trees": ("Árboles", "Trees"),
    "cf.k": ("Pliegues", "Folds"),
    "cf.cap": ("Máx. px/clase", "Max px/class"),
    "cf.cap.tip": ("Submuestra para entrenar (0 = todos).",
                   "Training subsample (0 = all)."),
    "cf.imp": ("Importancia", "Importance"),
    "cf.imp.tip": (
        "Por permutación en los pliegues de validación: cuánto baja el "
        "acierto equilibrado al barajar cada variable. Con variables muy "
        "correlacionadas se reparte y puede salir casi 0 en todas.",
        "Permutation on the validation folds: drop in balanced accuracy "
        "when each variable is shuffled. With highly correlated variables "
        "it is shared out and may be near 0 for all."),
    "cf.maj": ("Filtro 3x3", "3x3 filter"),
    "cf.valid": ("Mín. variables con dato", "Min variables with data"),
    "cf.valid.tip": ("Por debajo, el píxel queda sin clase. Los huecos que "
                     "quedan se marcan con un valor fuera de rango para que "
                     "los árboles traten «sin dato» como información (p. ej. "
                     "sin arranque dentro de la temporada).",
                     "Below this, the pixel gets no class. Remaining gaps "
                     "get an out-of-range value so the trees treat 'no "
                     "value' as information (e.g. no green-up within the "
                     "season)."),
    "cf.pick": ("Variables del modelo", "Model variables"),
    "cf.run": ("Validar y clasificar", "Validate and classify"),
    "cf.err": ("Faltan muestras, variables o esquema.",
               "Missing samples, variables or scheme."),
    "cf.err.vars": ("Las muestras no tienen estas variables (¿otro fichero "
                    "de variables?): %s", "The samples lack these variables "
                    "(another variables file?): %s"),
    "cf.nocv": ("Sin validación: %s", "No validation: %s"),
    "cf.cvinfo": ("Validación cruzada por parcela, %d pliegues, %s.",
                  "Cross-validation by field, %d folds, %s."),
    "cf.level.pixel": ("Por píxel", "Per pixel"),
    "cf.level.field": ("Por parcela (voto de sus píxeles)",
                       "Per field (vote of its pixels)"),
    "cf.balanced": ("equilibrado", "balanced"),
    "cf.step1": ("Paso 1: maíz+sorgo frente a otros (píxel)",
                 "Step 1: maize+sorghum vs other (pixel)"),
    "cf.step2": ("Paso 2: maíz frente a sorgo (píxeles reales de maíz o "
                 "sorgo que no se fueron a otros)", "Step 2: maize vs "
                 "sorghum (true maize or sorghum pixels not sent to "
                 "other)"),
    "cf.real": ("real \\ predicho", "true \\ predicted"),
    "cf.pa": ("Productor", "Producer"),
    "cf.ua": ("Usuario", "User"),
    "cf.area": ("Superficie en el mapa:", "Mapped area:"),
    "cf.caveat": (
        "La superficie contada en el mapa arrastra los errores de "
        "clasificación. Para estimar áreas hay que corregirla con una "
        "muestra de validación independiente (buenas prácticas tipo "
        "Olofsson et al. 2014 [VERIFICAR la cita]).",
        "Mapped area carries the classification errors. Area estimates "
        "need correction with an independent validation sample (good "
        "practice as in Olofsson et al. 2014 [VERIFY the reference])."),
    "cf.map": ("Clases", "Classes"),
    "cf.imp1": ("Paso 1", "Step 1"),
    "cf.imp2": ("Paso 2", "Step 2"),
    "dl.stage.start": ("Inicio", "Start"),
    "dl.stage.end": ("Fin", "End"),
    "dl.stages.note": (
        "Editables aquí o en la pestaña 1 (mismo calendario, se guarda "
        "solo; día y mes, vale para todos los años).",
        "Editable here or in tab 1 (same calendar, saved automatically; "
        "day and month, valid for every year)."),
    "dl.stages.tip": ("Las ventanas no pueden solaparse. Si cambias el "
                      "inicio de la primera o el fin de la última, las "
                      "fechas de búsqueda se ajustan.",
                      "Windows cannot overlap. Changing the first start "
                      "or the last end updates the search dates."),
    "dl.stage.year": ("%s: con este ciclo esa fecha cae en %d",
                      "%s: in this cycle that date falls in %d"),
    "ft.abs": ('Fechas absolutas (opcional)',
        'Absolute dates (optional)'),
    "ft.abs.tip": ('Día de arranque, de máximo y de bajada contados desde el inicio del ciclo, como variables. A escala local pueden ayudar (si un cultivo se siembra antes), pero mezclan fecha de siembra y cultivo y no se trasladan bien a otra región.',
        'Green-up, peak and senescence days from the cycle start, as variables. Locally they may help (if one crop is sown earlier), but they mix sowing date and crop and do not transfer well to another region.'),
    "ft.rel": ('Ventanas relativas a la curva',
        'Windows relative to the curve'),
    "ft.rel.tip": ('Mediana de cada banda e índice en las fechas que caen dentro de la ventana, medida desde el momento propio de cada píxel. Un píxel sin ese momento (curva plana o incompleta) queda sin dato en esa ventana.',
        "Median of each band and index over the dates inside the window, measured from each pixel's own moment. A pixel without that moment (flat or incomplete curve) gets no value in that window."),
    "ft.rel.anchor": ('desde',
        'from'),
    "ft.fixed": ('Etapas fijas del calendario (opcional)',
        'Fixed calendar stages (optional)'),
    "ft.fixed.tip": ('Las medianas por carpeta de la 0.2. Con siembras escalonadas mezclan fases distintas: úsalas solo para comparar.',
        'The per-folder medians of 0.2. With staggered sowing they mix phases: use them only to compare.'),
    "ft.ref": ('Comparar con las referencias por cultivo',
        'Compare with crop references'),
    "ft.ref.tip": ('Escribe referencia.tif: si el arranque y el máximo de cada píxel caen en las ventanas esperadas del maíz, del sorgo, de los dos o de ninguno. Solo para interpretar: no entra en ningún modelo.',
        "Writes referencia.tif: whether each pixel's green-up and peak fall in the expected windows of maize, sorghum, both or neither. Interpretation only: never enters a model."),
    "ft.ref.none": ('El perfil «%s» no tiene referencias rellenas (pestaña 1).',
        "Profile '%s' has no references filled in (tab 1)."),
    "ft.ref.src.cycle": ('Referencias del perfil «%s», guardado con la descarga.',
        "References of profile '%s', saved with the download."),
    "ft.ref.src.current": ('Referencias del perfil actual «%s» (la descarga no guardó perfil).',
        "References of the current profile '%s' (the download saved no profile)."),
    "ft.err.rel": ('Ventana %s: el final va antes que el inicio.',
        'Window %s: end before start.'),
    "ft.ref.done": ('Referencias: encaja con maíz %d px, con sorgo %d, con los dos %d, con ninguno %d, curva incompleta %d.',
        'References: fits maize %d px, sorghum %d, both %d, neither %d, incomplete curve %d.'),
    "ft.ref.layer": ('coherencia con referencias',
        'reference coherence'),
    "kind.rel": ('ventanas relativas',
        'relative windows'),
    "kind.fixed": ('etapas fijas',
        'fixed stages'),
    "vl.rel": ('+ ventanas relativas',
        '+ relative windows'),
    "cl.col.dur": ('Duración',
        'Duration'),
    "cl.col.upmax": ('Arranque→máx.',
        'Green-up→peak'),
    "cl.col.ref": ('Referencia',
        'Reference'),
    "ref.k0": ('sin curva',
        'no curve'),
    "ref.k1": ('encaja maíz',
        'fits maize'),
    "ref.k2": ('encaja sorgo',
        'fits sorghum'),
    "ref.k3": ('encaja los dos',
        'fits both'),
    "ref.k4": ('no encaja',
        'fits neither'),
    "ref.k5": ('curva incompleta',
        'incomplete curve'),
    "pf.profile": ('Perfil',
        'Profile'),
    "pf.tip": ('Calendario de una región (p. ej. norte con riego, centro-sur de temporal). Elígelo según la zona de estudio.',
        'Calendar of one region (e.g. irrigated north, rain-fed centre-south). Pick it for the study area.'),
    "pf.dup": ('Duplicar',
        'Duplicate'),
    "pf.rename": ('Renombrar',
        'Rename'),
    "pf.del": ('Borrar',
        'Delete'),
    "pf.note": ('Nota del perfil (región, fuente de las fechas…)',
        'Profile note (region, source of the dates…)'),
    "pf.exists": ('Ya hay un perfil «%s».',
        "Profile '%s' already exists."),
    "pf.new.ask": ('Nombre del perfil nuevo:',
        'New profile name:'),
    "pf.rename.ask": ('Nuevo nombre:',
        'New name:'),
    "pf.last": ('No se puede borrar el único perfil.',
        'Cannot delete the only profile.'),
    "pf.del.ask": ('¿Borrar el perfil «%s»?',
        "Delete profile '%s'?"),
    "pf.refs": ('Referencias por cultivo (solo para interpretar)',
        'Crop references (interpretation only)'),
    "pf.refs.note": ('Ventanas en las que se espera el arranque y el máximo de cada cultivo en esta región (MM-DD). No sirven para ordenar imágenes ni entran en la clasificación: solo para ver si la curva de un píxel o de un grupo encaja con lo esperado. Vienen vacías: rellénalas con datos de campo o con una fuente verificada.',
        "Windows in which each crop's green-up and peak are expected in this region (MM-DD). They do not file images nor enter the classification: only to see whether a pixel's or group's curve fits expectations. They ship empty: fill them from field data or a verified source."),
    "pf.col.up0": ('Arranque desde',
        'Green-up from'),
    "pf.col.up1": ('Arranque hasta',
        'Green-up to'),
    "pf.col.pk0": ('Máximo desde',
        'Peak from'),
    "pf.col.pk1": ('Máximo hasta',
        'Peak to'),
    "cal.col.origin": ('Origen',
        'Origin'),
    "sp.group": ('SIAP: Avance de Siembras y Cosechas',
        'SIAP: sowing and harvest progress'),
    "sp.import": ('Crear perfiles desde el SIAP',
        'Create profiles from SIAP'),
    "sp.import.tip": ('Un perfil por municipio y modalidad (riego o temporal), sumando maíz y sorgo, con los datos del plugin y lo descargado. Reemplaza los perfiles siap_ anteriores.',
        'One profile per municipality and regime (irrigated or rain-fed), adding up maize and sorghum, from the plugin data and your downloads. Replaces previous siap_ profiles.'),
    "sp.update": ('Actualizar desde el SIAP…',
        'Update from SIAP…'),
    "sp.update.tip": ('Descarga del Avance por municipio los años agrícolas que elijas. Parece que la web solo responde desde México: si estás fuera, usa una VPN con salida en México.',
        'Downloads the Avance by municipality for the agricultural years you choose. The site seems to answer only from Mexico: from abroad, use a VPN with a Mexican exit.'),
    "sp.years.ask": ('Años agrícolas del SIAP a descargar (p. ej. 2022 2026):',
        'SIAP agricultural years to download (e.g. 2022 2026):'),
    "sp.years.bad": ('Escribe años separados por espacios.',
        'Type years separated by spaces.'),
    "sp.folder": ('Carpeta donde guardar la descarga',
        'Folder for the download'),
    "sp.vpn": ('Se harán unas %d consultas al SIAP, con una pausa entre ellas (varios minutos). La web parece responder solo desde México: si estás fuera, activa una VPN con salida en México. ¿Seguir?',
        'About %d requests to SIAP will be made, with a pause between them (several minutes). The site seems to answer only from Mexico: from abroad, turn on a VPN with a Mexican exit. Continue?'),
    "sp.dl.done": ('SIAP: %d filas de %d consultas, %d errores -> %s',
        'SIAP: %d rows from %d requests, %d errors -> %s'),
    "sp.unmatched": ('Municipios del SIAP que no casan con la capa (se ignoran): %s',
        'SIAP municipalities not matching the layer (ignored): %s'),
    "sp.replace": ('Hay %d perfiles siap_ que se van a sustituir (se pierden sus cambios a mano). ¿Seguir?',
        '%d siap_ profiles will be replaced (their manual edits are lost). Continue?'),
    "sp.done": ('SIAP: %d perfiles; %d ciclos creados, %d omitidos.',
        'SIAP: %d profiles; %d cycles created, %d left out.'),
    "sp.extra": ('(con %d descargas propias)',
        '(with %d own downloads)'),
    "sp.noinfo": ('Este perfil no viene del SIAP.',
        'This profile does not come from SIAP.'),
    "sp.info.dates": ('%s, mediana de los años: siembra 10 %% %s, 50 %% %s, 90 %% %s; cosecha 50 %% %s, 90 %% %s.',
        '%s, median over years: sowing 10 %% %s, 50 %% %s, 90 %% %s; harvest 50 %% %s, 90 %% %s.'),
    "sp.info.years": ('Años usados: %s.',
        'Years used: %s.'),
    "sp.info.area": ('Sembrada (mediana): %.0f ha.',
        'Sown (median): %.0f ha.'),
    "sp.info.nocycle": ('Sin datos del SIAP para %s en este perfil.',
        'No SIAP data for %s in this profile.'),
    "sp.info.assumed": ('SUPUESTOS: emergencia = siembra al 90 %% + %s días; madurez empieza %s días antes de la cosecha al 50 %%; vegetativo y floración a partes iguales; ritmo constante dentro de cada mes.',
        'ASSUMPTIONS: emergence = 90 %% sowing + %s days; maturity starts %s days before 50 %% harvest; vegetative and flowering split evenly; constant pace within each month.'),
    "sp.off.up0": ('Arranque desde (días)',
        'Green-up from (days)'),
    "sp.off.up1": ('Arranque hasta (días)',
        'Green-up to (days)'),
    "sp.off.pk0": ('Máximo desde (días)',
        'Peak from (days)'),
    "sp.off.pk1": ('Máximo hasta (días)',
        'Peak to (days)'),
    "sp.off.note": ('Desfases desde la siembra, SUPUESTOS, para este ciclo. Referencia = [siembra al 10 % + desde, siembra al 90 % + hasta]. Vacíos por defecto: no hay valores verificados para Tamaulipas. Como orientación, para maíz en Brasil se han medido 18 a 29 días de siembra a inicio de temporada con HLS (Caldas et al. 2025), que es antes que nuestro arranque al 50 %. La cosecha no es la bajada del NDVI.',
        'Offsets from sowing, ASSUMED, for this cycle. Reference = [10 % sowing + from, 90 % sowing + to]. Empty by default: no verified values for Tamaulipas. As a hint, 18 to 29 days from sowing to start of season were measured for maize in Brazil with HLS (Caldas et al. 2025), earlier than our 50 % green-up. Harvest is not the NDVI fall.'),
    "sp.fill": ('Rellenar desde el SIAP',
        'Fill from SIAP'),
    "sp.fill.tip": ('Calcula las referencias de este ciclo con la ventana de siembra de cada cultivo en el SIAP y los desfases de la tabla.',
        "Computes this cycle's references from each crop's SIAP sowing window and the offsets in the table."),
    "sp.fill.origin": ('SIAP (siembra 10-90 %%) + desfases supuestos %s',
        'SIAP (sowing 10-90 %%) + assumed offsets %s'),
    "sp.fill.done": ('Referencias rellenadas desde el SIAP. Pendiente: %s',
        'References filled from SIAP. Missing: %s'),
    "za.assign": ('Asignar por zona',
        'Assign from area'),
    "za.assign.tip": ('Elige el perfil del SIAP del municipio que más ocupa la zona de estudio; riego si al menos la mitad cae en distritos de riego (CONAGUA), si no, temporal.',
        'Picks the SIAP profile of the municipality covering most of the study area; irrigated if at least half lies in irrigation districts (CONAGUA), otherwise rain-fed.'),
    "za.result": ('Zona: %s; en distrito de riego %.0f %%.',
        'Area: %s; in irrigation district %.0f %%.'),
    "za.chosen": ('Perfil: %s.',
        'Profile: %s.'),
    "za.siapyear": ('= %s %d del SIAP',
        '= SIAP %s %d'),
    "cf.siap.log": ('Superficies frente al SIAP: %s %d, %d filas',
        'Areas vs SIAP: %s %d, %d rows'),
    "cf.siap.fail": ('Sin comparación con el SIAP: %s',
        'No comparison with SIAP: %s'),
    "cf.siap.title": ('Superficie del mapa frente a la sembrada del SIAP (%s %d, maíz + sorgo, ha)',
        'Mapped area vs SIAP sown area (%s %d, maize + sorghum, ha)'),
    "cf.siap.mun": ('Municipio',
        'Municipality'),
    "cf.siap.mod": ('Modalidad',
        'Regime'),
    "cf.siap.cov": ('Cubierto',
        'Covered'),
    "cf.siap.map": ('Mapa',
        'Map'),
    "cf.siap.siap": ('SIAP',
        'SIAP'),
    "cf.siap.ratio": ('Mapa/SIAP',
        'Map/SIAP'),
    "cf.siap.caveat": ('Comprobación de coherencia, no validación: el SIAP es dato declarado, el mapa arrastra sus errores y los píxeles mezclados de los bordes, y la modalidad del mapa sale de los distritos de riego (aproximado). El cociente solo se da si el mapa cubre al menos el 90 % del municipio. Detalle por cultivo en el CSV.',
        "Coherence check, not validation: SIAP is declared data, the map carries its errors and mixed edge pixels, and the map's regime comes from the irrigation districts (approximate). The ratio is only given if the map covers at least 90 % of the municipality. Per-crop detail in the CSV."),
    'tab.siap': ('7 · Mapas SIAP',
        '7 · SIAP maps'),
    'tab.help': ('Ayuda', 'Help'),
    'help.title': ('Manual de usuario', 'User manual'),
    'help.text': ('Guía paso a paso, pestaña por pestaña (PDF, en '
                  'español). Puedes guardarla donde quieras o abrirla '
                  'directamente con tu lector de PDF.',
                  'Step-by-step guide, tab by tab (PDF, in Spanish). Save '
                  'it wherever you like or open it with your PDF reader.'),
    'help.download': ('Descargar manual (PDF)…', 'Download manual (PDF)…'),
    'help.open': ('Abrir manual', 'Open manual'),
    'help.saved': ('Manual guardado en:\n%s', 'Manual saved to:\n%s'),
    'help.missing': ('No encuentro el manual dentro del complemento:\n%s',
                     'The manual is missing from the plugin:\n%s'),
    'help.error': ('No se pudo guardar el manual:\n%s',
                   'Could not save the manual:\n%s'),
    'help.version': ('Complemento: EloteSat Tamaulipas %s. Manual: %s.',
                     'Plugin: EloteSat Tamaulipas %s. Manual: %s.'),
    'cs.reg.both': ('Riego + temporal',
        'Irrigated + rain-fed'),
    'cs.reg.riego': ('Riego',
        'Irrigated'),
    'cs.reg.temporal': ('Temporal',
        'Rain-fed'),
    'cs.incomplete': ('Ojo: ese ciclo del SIAP está incompleto en los datos.',
        'Note: that SIAP cycle is incomplete in the data.'),
    'mp.intro': ('Mapas por municipio del Avance de Siembras y Cosechas del SIAP. Elige qué mapear y cómo; la capa se añade al proyecto con estilo y etiquetas, y puedes crear una composición lista para imprimir.',
        'Maps by municipality of the SIAP sowing and harvest progress. Pick what to map and how; the layer is added to the project styled and labelled, and a print layout can be created.'),
    'mp.what': ('Qué mapear',
        'What to map'),
    'mp.year': ('Año agrícola (SIAP)',
        'Agricultural year (SIAP)'),
    'mp.reg': ('Modalidad',
        'Regime'),
    'mp.crop': ('Cultivo',
        'Crop'),
    'mp.crop.both': ('Maíz + sorgo',
        'Maize + sorghum'),
    'mp.crop.maiz': ('Maíz grano',
        'Grain maize'),
    'mp.crop.sorgo': ('Sorgo grano',
        'Grain sorghum'),
    'mp.var': ('Variable',
        'Variable'),
    'mp.var.sembrada_ha': ('Superficie sembrada',
        'Sown area'),
    'mp.var.cosechada_ha': ('Superficie cosechada',
        'Harvested area'),
    'mp.var.siniestrada_ha': ('Superficie siniestrada',
        'Lost area'),
    'mp.var.produccion': ('Producción',
        'Production'),
    'mp.var.rendimiento': ('Rendimiento',
        'Yield'),
    'mp.var.pct_siniestrada': ('% siniestrado',
        '% lost'),
    'mp.var.p50_siembra': ('Mitad de la siembra (fecha)',
        'Half of the sowing (date)'),
    'mp.var.p50_cosecha': ('Mitad de la cosecha (fecha)',
        'Half of the harvest (date)'),
    'mp.cut': ('Corte',
        'Cut-off'),
    'mp.cut.close': ('cierre del ciclo',
        'close of the cycle'),
    'mp.incomplete': ('incompleto',
        'incomplete'),
    'mp.state.start': ('Falta el arranque del ciclo en los datos: las fechas de siembra pueden salir vacías o tardías.',
        'The start of the cycle is missing: sowing dates may be empty or late.'),
    'mp.state.end': ('Falta el final del ciclo en los datos: la cosecha sale corta.',
        'The end of the cycle is missing: harvest is underestimated.'),
    'mp.state.start_end': ('Faltan el arranque y el final del ciclo en los datos.',
        'Both the start and the end of the cycle are missing.'),
    'mp.style': ('Estilo',
        'Style'),
    'mp.method': ('Clases',
        'Classes'),
    'mp.method.jenks': ('Cortes naturales (Jenks)',
        'Natural breaks (Jenks)'),
    'mp.method.quantile': ('Cuantiles',
        'Quantiles'),
    'mp.classes': ('Número de clases',
        'Number of classes'),
    'mp.ramp': ('Colores',
        'Colours'),
    'mp.labels': ('Etiquetas con el nombre',
        'Name labels'),
    'mp.values': ('y el valor',
        'and the value'),
    'mp.run': ('Crear mapa',
        'Make map'),
    'mp.layout': ('Composición de impresión',
        'Print layout'),
    'mp.layout.tip': ('A4 apaisado con título, leyenda, escala, norte y fuentes. Se abre desde el gestor de composiciones.',
        'A4 landscape with title, legend, scale, north arrow and sources. Open it from the layout manager.'),
    'mp.layout.done': ('Composición «%s» creada (Proyecto → Composiciones).',
        "Layout '%s' created (Project → Layouts)."),
    'mp.csv': ('Exportar CSV',
        'Export CSV'),
    'mp.sub': ('Situación: %s. Fuente: SIAP, Avance de Siembras y Cosechas.',
        'Status: %s. Source: SIAP, sowing and harvest progress.'),
    'mp.err.nodata': ('No hay datos para esa combinación.',
        'No data for that combination.'),
    'mp.done': ('Capa «%s» añadida (%d municipios con dato).',
        "Layer '%s' added (%d municipalities with data)."),
    'mp.nodata': ('sin dato',
        'no data'),
    'mp.legend': ('Leyenda',
        'Legend'),
    'mp.sources': ("Datos: SIAP (SADER), Avance de Siembras y Cosechas, nube.agricultura.gob.mx/avance_agricola [licencia y cita: VERIFICAR].\nLímites municipales: Who's On First (whosonfirst.org/docs/licenses) y Quattroshapes (CC-BY); aproximados, no son el Marco Geoestadístico del INEGI.\nElaborado con EloteSat (UAT, FIC) el %s.",
        "Data: SIAP (SADER), sowing and harvest progress, nube.agricultura.gob.mx/avance_agricola [licence and citation: CHECK].\nMunicipal limits: Who's On First (whosonfirst.org/docs/licenses) and Quattroshapes (CC-BY); approximate, not the INEGI Marco Geoestadístico.\nMade with EloteSat (UAT, FIC) on %s."),
    'mp.credits': ("Datos: <a href='https://nube.agricultura.gob.mx/avance_agricola/'>SIAP, Avance de Siembras y Cosechas</a>. Municipios: <a href='https://whosonfirst.org/docs/licenses/'>Who's On First</a> y Quattroshapes (CC-BY), límites aproximados.",
        "Data: <a href='https://nube.agricultura.gob.mx/avance_agricola/'>SIAP sowing and harvest progress</a>. Municipalities: <a href='https://whosonfirst.org/docs/licenses/'>Who's On First</a> and Quattroshapes (CC-BY), approximate limits."),
}
