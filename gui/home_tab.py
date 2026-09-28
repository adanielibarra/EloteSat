"""Home tab: logos, language selector and instructions."""

import configparser
import os

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QFrame,
    QTextBrowser)

from ..core import i18n
from .translatable import Translatable

PLUGIN_DIR = os.path.dirname(os.path.dirname(__file__))
LOGO_HEIGHT = 64


def plugin_version():
    cp = configparser.ConfigParser()
    try:
        cp.read(os.path.join(PLUGIN_DIR, "metadata.txt"), encoding="utf-8")
        return cp.get("general", "version")
    except Exception:
        return "?"


HTML = {
    "es": """
<h3>Qué es EloteSat Tamaulipas</h3>
<p>Fase 1 de una herramienta para distinguir el maíz del sorgo y de otros
cultivos en Tamaulipas. Descarga Sentinel-2 y Landsat 8/9 recortados a tu
zona de estudio y guarda cada imagen en la carpeta de la etapa del cultivo
que le toca según un calendario que tú editas. Después calcula
variables por etapa y de la curva de NDVI, y sirve para dos pasos:
<b>1)</b> separar maíz y sorgo del resto y <b>2)</b> separar el maíz del
sorgo. Se pueden hacer por separado o a la vez.</p>

<h3>Pestaña 1 · Calendario</h3>
<ol>
<li>Dos ciclos: <b>OI</b> (otoño-invierno) y <b>PV</b> (primavera-verano).
Cada uno con cuatro etapas: <code>00_siembra_emergencia</code>,
<code>01_vegetativo</code>, <code>02_floracion_espigamiento</code> y
<code>03_madurez_senescencia</code>.</li>
<li><b>Perfiles desde el SIAP</b>: uno por municipio y modalidad (riego o
temporal), sacados del Avance de Siembras y Cosechas; la columna Origen
dice qué fecha sale del SIAP, cuál es estimada y cuál has cambiado tú.
<i>Actualizar desde el SIAP</i> descarga años nuevos (necesita conexión
desde México o una VPN con salida en México).</li>
<li><b>Perfiles</b>: un calendario por región (duplica el genérico para
norte, centro-sur…) y, si quieres, las ventanas esperadas de arranque y
máximo del maíz y del sorgo, <b>solo para interpretar</b>.</li>
<li>Las fechas son MM-DD. Un ciclo puede cruzar el año: lo que cae antes
del inicio de la primera etapa pasa al año siguiente. Las ventanas no se
pueden solapar; los huecos sí (esas fechas van a
<code>fuera_de_etapa</code>).</li>
<li><b>Las fechas que vienen de fábrica son un punto de partida, no un dato
verificado.</b> Ajústalas con el calendario del SIAP, de SADER o del
distrito de riego.</li>
<li>Se guarda solo. Puedes exportarlo o importarlo en JSON.</li>
<li><i>Reordenar carpeta</i>: si cambias las ventanas después de descargar,
mueve los ficheros a sus nuevas carpetas (nunca sobrescribe) y rehace
los mosaicos.</li>
</ol>

<h3>Pestaña 2 · Descarga</h3>
<ol>
<li>Elige la capa con la <b>zona de estudio</b> (un distrito de riego, un
municipio, un rectángulo). Tamaulipas entero son muchos GB por fecha: la
etiqueta de tamaño te da una cota antes de descargar.</li>
<li><i>Asignar por zona</i> elige el perfil del SIAP del municipio que más
ocupa la zona (riego si la mitad cae en distritos de riego).</li>
<li>Elige ciclo y año: las fechas de búsqueda se ponen solas con el
calendario (puedes cambiarlas). Al lado sale el año equivalente del SIAP.</li>
<li>Sensores y fuente:
<ul>
<li>Sentinel-2 L2A: Earth Search (AWS, sin cuenta) o Planetary Computer
(Microsoft, sin cuenta; el plugin pide un token temporal).</li>
<li>Landsat 8/9 C2 L2: Planetary Computer (sin cuenta), o Earth Search con el
bucket de la USGS, que es <b>de pago por quien descarga</b> (requester
pays): hace falta una cuenta de AWS y la transferencia cuesta dinero.</li>
</ul></li>
<li>Filtros: nubes de la tesela (grueso), <b>cobertura</b> mínima de la
zona (qué parte de la zona tiene datos en esa tesela) y <b>despejado</b>
mínimo (de la parte cubierta, cuánto está libre de nubes, sombras y
nieve, según SCL o QA_PIXEL).</li>
<li><i>Buscar escenas</i>. La tabla dice a qué etapa va cada fecha.</li>
<li><i>Descargar seleccionadas</i>. Primero baja solo la máscara del
recorte y descarta la escena si no pasa los filtros.</li>
</ol>

<h3>Qué sale</h3>
<pre>
carpeta/
  OI_2026/
    manifest.csv  calendario.json  parametros.txt
    00_siembra_emergencia/
      S2/        S2_20260210_14RPP_S2A_10m.tif, ..._20m.tif
      LANDSAT/   LS_20260212_026042_L9_30m.tif
    01_vegetativo/ ...
</pre>
<ul>
<li>Sentinel-2: 10 m (B02 B03 B04 B08) y 20 m (B05 B06 B07 B8A B11 B12 SCL),
en su malla, sin remuestrear.</li>
<li>Landsat: 30 m (SR_B2 a SR_B7 y QA_PIXEL).</li>
<li>Números digitales (UInt16) con scale y offset escritos en cada banda:
reflectancia = DN × scale + offset.</li>
<li>Si una fecha necesita varias teselas en el mismo SRC, un mosaico virtual
<code>MOS_*.vrt</code>.</li>
</ul>

<h3>Pestaña 3 · Variables</h3>
<ol>
<li>Elige la carpeta del ciclo (se rellena sola desde la pestaña 2).</li>
<li>Malla común (20 m por defecto). Sentinel-2 y Landsat van <b>por
separado</b>: cada variable lleva su prefijo (<code>S2_</code>,
<code>LS_</code>).</li>
<li>Curva de NDVI de cada píxel: su arranque, su máximo y su bajada.</li>
<li><b>Ventanas relativas</b> a esos momentos (arranque, máximo, 20 a 40
días después del máximo, bajada): mediana de cada banda y de NDVI, GCVI,
NDMI, NDTI y, solo en S2, NDRE y CIre. Cada parcela se compara en su misma
fase aunque se sembrara otro día.</li>
<li><b>Forma de la curva</b>: amplitud, velocidad de subida y bajada, días
del arranque al máximo, duración. Fechas absolutas y etapas fijas, solo
como opción.</li>
<li>Si el perfil tiene referencias, <code>referencia.tif</code> dice si
cada píxel encaja con lo esperado del maíz, del sorgo, de los dos o de
ninguno.</li>
<li>Sale <code>variables/variables.tif</code> (una banda por variable) y
<code>nobs.tif</code> (fechas limpias por etapa).</li>
</ol>

<h3>Pestaña 4 · Grupos (sin datos de campo)</h3>
<p>k-means sobre las variables que elijas (por defecto, NDVI por etapa y la
curva de S2). Mapa de grupos, tabla con superficie y fechas de la curva, y
perfil medio de cada grupo. <b>Los grupos no son cultivos</b>: sirven para
ver cuántos calendarios hay y decidir dónde muestrear.</p>

<h3>Pestaña 5 · Muestras y separabilidad</h3>
<ol>
<li>Capa de polígonos o puntos con el cultivo. Asigna cada valor a maíz,
sorgo, otros o ignorar. El campo de parcela sirve para validar dejando
fuera parcelas enteras.</li>
<li>Elige paso 1 (maíz+sorgo frente a otros) o paso 2 (maíz frente a
sorgo), por píxel o por parcela.</li>
<li>La tabla ordena las variables por distancia de Jeffries-Matusita (0 a
2) y da el mejor umbral de cada una. Al elegir una, ves sus histogramas
por clase y puedes mover el umbral y ver cuántas acierta. <i>Regla al
mapa</i> la pinta.</li>
<li><i>Mejor combinación</i>: elige variables paso a paso y las puedes
mandar a la pestaña 6.</li>
</ol>

<h3>Pestaña 6 · Clasificación</h3>
<ol>
<li>Random Forest (scikit-learn si está instalado; si no, uno propio en
numpy, más lento).</li>
<li>Jerárquica (paso 1 y luego paso 2) y/o plana (3 clases a la vez).</li>
<li>Validación cruzada <b>por parcela</b>. Da la matriz por píxel y por
parcela, la exactitud de cada paso y la importancia de cada variable
para cada paso.</li>
<li>Mapa de clases, probabilidades e informe en
<code>clasificacion/</code>.</li>
</ol>

<h3>Pestaña 7 · Mapas SIAP</h3>
<p>Mapas por municipio del Avance de Siembras y Cosechas: elige ciclo, año,
modalidad, cultivo, variable y corte, y pulsa <i>Crear mapa</i>.
<i>Composición de impresión</i> prepara un A4 con título, leyenda, escala,
norte y fuentes.</p>

<h3>Limitaciones que conviene tener presentes</h3>
<ul>
<li>Las carpetas agrupan por <b>fecha</b>, pero la fenología va por
<b>parcela</b>. Con fechas de siembra distintas, una misma imagen pilla
parcelas en etapas distintas. Las carpetas son para organizarse; la
clasificación tendrá que usar la serie entera.</li>
<li>Sentinel-2 y Landsat no están armonizados (bandas y respuestas
espectrales distintas). No mezcles sus valores sin corregirlos.</li>
<li>Sin datos de campo no hay forma de saber si separa bien maíz y sorgo.
Los grupos de la pestaña 4 ayudan a explorar, no a validar.</li>
<li>No se ha podido probar contra los servidores reales ni con parcelas
reales: solo con datos sintéticos.</li>
</ul>

<h3>Créditos</h3>
<p>Creado por Daniel Ibarra-Marinas.<br>
Facultad de Ingeniería y Ciencias, Universidad Autónoma de Tamaulipas.</p>
<p>Datos: contiene datos modificados de Copernicus Sentinel [año de los
datos]. Landsat: cortesía del U.S. Geological Survey. Servidos por Earth
Search (Element 84, AWS Registry of Open Data) o Microsoft Planetary
Computer, según la fuente elegida.</p>
<p>Municipios: <a href="https://whosonfirst.org/docs/licenses/">Who's On
First</a>, geometría de Quattroshapes (CC-BY). Distritos de riego: CONAGUA,
vía INFOTECA de SEMARNAT (año agrícola 2016-2017).</p>
<p><a href="https://www.researchgate.net/profile/Daniel-Ibarra-Marinas">ResearchGate</a> · <a href="https://scholar.google.com/citations?user=5JgVP2MAAAAJ&amp;hl=es">Google Académico</a></p>
""",
    "en": """
<h3>What EloteSat Tamaulipas is</h3>
<p>Phase 1 of a tool to tell maize from sorghum and other crops in
Tamaulipas. It downloads Sentinel-2 and Landsat 8/9 clipped to your study
area and files each image in the folder of the crop stage it belongs to,
following a calendar you edit. Then it computes variables per stage
and from the NDVI curve, for two steps: <b>1)</b> tell maize and sorghum
from the rest and <b>2)</b> tell maize from sorghum. Separately or at
once.</p>

<h3>Tab 1 · Calendar</h3>
<ol>
<li>Two cycles: <b>OI</b> (autumn-winter) and <b>PV</b> (spring-summer),
each with four stages: <code>00_siembra_emergencia</code>,
<code>01_vegetativo</code>, <code>02_floracion_espigamiento</code> and
<code>03_madurez_senescencia</code>.</li>
<li><b>Profiles</b>: one calendar per region (duplicate the generic one
for north, centre-south…) and, optionally, the expected green-up and peak
windows of maize and sorghum, <b>for interpretation only</b>.</li>
<li>Dates are MM-DD. A cycle may cross New Year: anything before the start
of the first stage falls in the next year. Windows cannot overlap; gaps
are allowed (those dates go to <code>fuera_de_etapa</code>).</li>
<li><b>The default dates are a starting point, not verified data.</b>
Adjust them with the SIAP, SADER or irrigation district calendar.</li>
<li>Saved automatically. Can be exported or imported as JSON.</li>
<li><i>Reorganize folder</i>: if you change the windows after downloading,
moves the files to their new folders (never overwrites) and rebuilds the
mosaics.</li>
</ol>

<h3>Tab 2 · Download</h3>
<ol>
<li>Choose the <b>study area</b> layer (an irrigation district, a
municipality, a rectangle). The whole state is many GB per date: the size
label gives an upper bound before downloading.</li>
<li>Choose cycle and year: search dates are filled from the calendar (you
can change them).</li>
<li>Sensors and source:
<ul>
<li>Sentinel-2 L2A: Earth Search (AWS, no account) or Planetary Computer
(Microsoft, no account; the plugin requests a temporary token).</li>
<li>Landsat 8/9 C2 L2: Planetary Computer (no account), or Earth Search with
the USGS bucket, which is <b>requester pays</b>: it needs an AWS account
and the transfer costs money.</li>
</ul></li>
<li>Filters: tile cloud cover (coarse), minimum <b>cover</b> of the area
(how much of the area has data in that tile) and minimum <b>clear</b>
(of the covered part, how much is free of cloud, shadow and snow, from
SCL or QA_PIXEL).</li>
<li><i>Search scenes</i>. The table shows the stage of each date.</li>
<li><i>Download checked</i>. Only the mask of the clip is read first; the
scene is skipped if it fails the filters.</li>
</ol>

<h3>Output</h3>
<pre>
folder/
  OI_2026/
    manifest.csv  calendario.json  parametros.txt
    00_siembra_emergencia/
      S2/        S2_20260210_14RPP_S2A_10m.tif, ..._20m.tif
      LANDSAT/   LS_20260212_026042_L9_30m.tif
    01_vegetativo/ ...
</pre>
<ul>
<li>Sentinel-2: 10 m (B02 B03 B04 B08) and 20 m (B05 B06 B07 B8A B11 B12
SCL), on their own grid, no resampling.</li>
<li>Landsat: 30 m (SR_B2 to SR_B7 and QA_PIXEL).</li>
<li>Digital numbers (UInt16) with scale and offset written in each band:
reflectance = DN × scale + offset.</li>
<li>If one date needs several tiles in the same CRS, a virtual mosaic
<code>MOS_*.vrt</code>.</li>
</ul>

<h3>Tab 3 · Variables</h3>
<ol>
<li>Choose the cycle folder (filled from tab 2).</li>
<li>Common grid (20 m by default). Sentinel-2 and Landsat are kept
<b>apart</b>: each variable has its prefix (<code>S2_</code>,
<code>LS_</code>).</li>
<li>Each pixel's NDVI curve: its green-up, peak and senescence.</li>
<li><b>Relative windows</b> around those moments (green-up, peak, 20 to 40
days after the peak, senescence): median of each band and of NDVI, GCVI,
NDMI, NDTI and, S2 only, NDRE and CIre. Every field is compared at its
own phase whatever its sowing date.</li>
<li><b>Curve shape</b>: amplitude, rise and fall speed, days from green-up
to peak, duration. Absolute dates and fixed stages only as options.</li>
<li>If the profile has references, <code>referencia.tif</code> says
whether each pixel fits what is expected of maize, sorghum, both or
neither.</li>
<li>Output <code>variables/variables.tif</code> (one band per variable)
and <code>nobs.tif</code> (clear dates per stage).</li>
</ol>

<h3>Tab 4 · Groups (no field data)</h3>
<p>k-means on the variables you choose (default: S2 NDVI per stage and
curve). Group map, table with area and curve dates, and mean profile of
each group. <b>Groups are not crops</b>: they show how many calendars
there are and help decide where to sample.</p>

<h3>Tab 5 · Samples and separability</h3>
<ol>
<li>Polygon or point layer with the crop. Map each value to maize,
sorghum, other or ignore. The field id lets validation hold out whole
fields.</li>
<li>Choose step 1 (maize+sorghum vs other) or step 2 (maize vs sorghum),
per pixel or per field.</li>
<li>The table ranks variables by Jeffries-Matusita distance (0 to 2) and
gives each one's best threshold. Pick one to see its histograms per class,
move the threshold and see how many are right. <i>Rule to map</i> draws
it.</li>
<li><i>Best combination</i>: step-wise selection you can send to tab
6.</li>
</ol>

<h3>Tab 6 · Classification</h3>
<ol>
<li>Random Forest (scikit-learn if installed; otherwise a small numpy one,
slower).</li>
<li>Hierarchical (step 1 then step 2) and/or flat (3 classes at once).</li>
<li>Cross-validation <b>by field</b>. Confusion per pixel and per field,
accuracy of each step and variable importance for each step.</li>
<li>Class map, probabilities and report in
<code>clasificacion/</code>.</li>
</ol>

<h3>Tab 7 · SIAP maps</h3>
<p>Maps by municipality of the SIAP sowing and harvest progress: choose
cycle, year, regime, crop, variable and cut-off, and press <i>Create
map</i>. <i>Print layout</i> prepares an A4 with title, legend, scale bar,
north arrow and sources.</p>

<h3>Limitations to keep in mind</h3>
<ul>
<li>Folders group by <b>date</b>, but phenology is per <b>field</b>. With
different sowing dates, one image catches fields at different stages.
Folders are for organizing; classification will need the whole series.</li>
<li>Sentinel-2 and Landsat are not harmonized (different bands and
spectral responses). Do not mix their values without correcting them.</li>
<li>Without field data there is no way to know whether maize and sorghum
are separated. The groups of tab 4 help explore, not validate.</li>
<li>Not tested against the real servers or real fields: only with
synthetic data.</li>
</ul>

<h3>Credits</h3>
<p>Created by Daniel Ibarra-Marinas.<br>
Facultad de Ingeniería y Ciencias, Universidad Autónoma de Tamaulipas.</p>
<p>Data: contains modified Copernicus Sentinel data [year of the data].
Landsat: courtesy of the U.S. Geological Survey. Served by Earth Search
(Element 84, AWS Registry of Open Data) or Microsoft Planetary Computer,
depending on the chosen source.</p>
<p>Municipalities: <a href="https://whosonfirst.org/docs/licenses/">Who's
On First</a>, geometry from Quattroshapes (CC-BY). Irrigation districts:
CONAGUA, via SEMARNAT INFOTECA (agricultural year 2016-2017).</p>
<p><a href="https://www.researchgate.net/profile/Daniel-Ibarra-Marinas">ResearchGate</a> · <a href="https://scholar.google.com/citations?user=5JgVP2MAAAAJ&amp;hl=en">Google Scholar</a></p>
""",
}


class HomeTab(QWidget, Translatable):
    languageChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        # logos on a white strip: the official logos are designed for a
        # light background and the grey text is unreadable on dark themes
        strip = QFrame()
        strip.setObjectName("logoStrip")
        strip.setStyleSheet("#logoStrip { background: white; "
                            "border-radius: 6px; }")
        hl = QHBoxLayout(strip)
        hl.setContentsMargins(16, 10, 16, 10)
        self.logo_labels = []
        for name in ("elotesat.png", "uat.png", "fic.png"):
            lab = QLabel()
            pm = QPixmap(os.path.join(PLUGIN_DIR, "logos", name))
            if not pm.isNull():
                lab.setPixmap(pm.scaledToHeight(LOGO_HEIGHT,
                                                Qt.SmoothTransformation))
            else:
                lab.setText(name.split(".")[0].upper())
            self.logo_labels.append(lab)
        # EloteSat, UAT, FIC, close together and centred
        hl.setSpacing(28)
        hl.addStretch()
        for lab in self.logo_labels:
            hl.addWidget(lab)
        hl.addStretch()
        lay.addWidget(strip)

        head = QHBoxLayout()
        title = QLabel("<span style='font-size:18pt; font-weight:600'>"
                       "EloteSat Tamaulipas</span>")
        self.subtitle = QLabel()
        self._t(self.subtitle.setText, "home.subtitle")
        self.version = QLabel()
        self._t(self.version.setText, "home.version", plugin_version())
        tbox = QVBoxLayout()
        tbox.addWidget(title)
        tbox.addWidget(self.subtitle)
        tbox.addWidget(self.version)
        head.addLayout(tbox)
        head.addStretch()
        self.lbl_lang = QLabel()
        self._t(self.lbl_lang.setText, "home.language")
        self.cb_lang = QComboBox()
        for code, name in i18n.LANGS.items():
            self.cb_lang.addItem(name, code)
        self.cb_lang.setCurrentIndex(self.cb_lang.findData(i18n.lang()))
        self.cb_lang.currentIndexChanged.connect(self._lang_changed)
        head.addWidget(self.lbl_lang)
        head.addWidget(self.cb_lang)
        lay.addLayout(head)

        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        lay.addWidget(self.text, 1)
        self._retranslate_extra()

    def _lang_changed(self):
        code = self.cb_lang.currentData()
        i18n.set_lang(code)
        try:
            i18n.save_lang(code)
        except Exception:
            pass
        self.languageChanged.emit(code)

    def _retranslate_extra(self):
        self.text.setHtml(HTML[i18n.lang()])
        idx = self.cb_lang.findData(i18n.lang())
        if idx != self.cb_lang.currentIndex():
            self.cb_lang.blockSignals(True)
            self.cb_lang.setCurrentIndex(idx)
            self.cb_lang.blockSignals(False)
