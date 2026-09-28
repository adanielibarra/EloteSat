<p align="center">
  <img src="logos/elotesat.png" width="160" alt="EloteSat Tamaulipas">
</p>

<h1 align="center">EloteSat Tamaulipas</h1>

<p align="center">
Complemento de QGIS para mapear <b>maíz y sorgo de grano</b> en Tamaulipas (México) a partir de su fenología.<br>
<i>QGIS plugin to map grain maize and sorghum in Tamaulipas, Mexico, from their phenology.</i>
</p>

---

## Qué hace

Maíz y sorgo se parecen mucho desde el espacio y cada parcela se siembra en una fecha distinta. EloteSat no compara fechas fijas, sino **la misma fase de la curva de verdor (NDVI) de cada píxel**, y se apoya en los calendarios del SIAP para saber qué imágenes buscar.

| Pestaña | Qué hace |
|---|---|
| 1 · Calendario | Perfiles de siembra y cosecha por municipio y modalidad (riego o temporal), sacados del *Avance de Siembras y Cosechas* del SIAP. Actualizables desde la web. |
| 2 · Descarga | Busca y descarga Sentinel-2 L2A y Landsat 8/9 recortados a tu zona, descartando lo nublado. Asigna el perfil según la zona de estudio. |
| 3 · Variables | Curva de NDVI de cada píxel, variables en ventanas relativas a su arranque, máximo y bajada, y métricas de forma. |
| 4 · Grupos | k-means para explorar sin datos de campo. |
| 5 · Muestras | Lee parcelas de campo, mide la separabilidad (Jeffries-Matusita) y prueba umbrales. |
| 6 · Clasificación | Random Forest jerárquico o plano con validación por parcela, mapa de clases y comparación con la superficie del SIAP. |
| 7 · Mapas SIAP | Mapas municipales del Avance con estilo y composición de impresión A4. |
| Ayuda | El manual de usuario en PDF, para abrirlo o guardarlo. |

## Instalación

1. Descarga `elotesat_vX.Y.Z.zip` de la última versión en [Releases](../../releases). **No uses *Code → Download ZIP***: baja una carpeta `EloteSat-main` que QGIS no puede instalar.
2. En QGIS: *Complementos → Administrar e instalar complementos → Instalar a partir de ZIP*.
3. Se abre desde el menú **EloteSat** de la barra de menús (una entrada por pestaña) o desde su barra de herramientas.

Requisitos: QGIS 3.28 o posterior. Sin dependencias obligatorias (usa GDAL y numpy, que ya trae QGIS). Con scikit-learn la clasificación va más rápida.

El manual de usuario, paso a paso y pestaña por pestaña, viene dentro del plugin (pestaña **Ayuda**, fichero en `docs/`). La interfaz arranca en español; el inglés se elige en la pestaña Inicio.

## Estado

**Experimental.** Probado con comprobaciones automáticas en QGIS 3.34, sin pruebas contra los servidores reales de imágenes ni con parcelas de campo. Solo funciona en Tamaulipas.

Hasta la versión 0.4.0 se llamaba **FenoSat**; al abrirlo por primera vez copia su configuración.

## Datos y créditos

- Imágenes: contiene datos modificados de Copernicus Sentinel; Landsat, cortesía del U.S. Geological Survey. Servidos por Earth Search (Element 84) o Microsoft Planetary Computer.
- Calendarios: SIAP (SADER), *Avance de Siembras y Cosechas*.
- Municipios: [Who's On First](https://whosonfirst.org/docs/licenses/), geometría de Quattroshapes (CC-BY). Límites aproximados, no son el Marco Geoestadístico del INEGI.
- Distritos de riego: CONAGUA, vía INFOTECA de SEMARNAT.

## Autoría

Daniel Ibarra-Marinas · Facultad de Ingeniería y Ciencias, Universidad Autónoma de Tamaulipas · daniel.ibarra@uat.edu.mx

## Licencia

GNU General Public License. Ver [LICENSE](LICENSE).
