"""'Actualizar desde el SIAP': download the Avance de Siembras y Cosechas
by municipality (Tamaulipas), from descarga_siap.py (Claudia and Daniel,
28/09/2026; request arguments worked out by hand, see ENCARGO 0.4.0).

- Only the Python standard library.
- The server seems to answer only from Mexico (a VPN with a Mexican exit
  works). Few MB in total; a pause between requests not to load it.
- Figures are cumulative. One response may hold two blocks (months 10-12
  also bring the next OI; months 1-3 the previous PV): each block is read
  with its own header and its real agricultural year.
- A full cycle needs requests of two years: OI Y = months 10-12 of Y-1
  + months 1-12 of Y; PV Y = months 4-12 of Y + months 1-3 of Y+1.
- Every raw response is saved, so the parsing can be checked later.
"""

import csv
import html
import http.cookiejar
import os
import re
import time
import urllib.parse
import urllib.request

URL = "https://nube.agricultura.gob.mx/avance_agricola/"

CICLOS = {1: "Otoño - Invierno", 2: "Primavera - Verano"}
MODALIDADES = {1: "Riego", 2: "Temporal"}
CULTIVOS = {374: "Sorgo grano", 225: "Maíz grano"}
ENTIDAD = 28  # Tamaulipas
MESES_ES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
            "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
            "octubre": 10, "noviembre": 11, "diciembre": 12}

CAMPOS = ["anio_consulta", "anio_agricola", "ciclo", "modalidad", "cultivo",
          "mes_consulta", "fecha_corte", "entidad", "distrito", "municipio",
          "sembrada_ha", "cosechada_ha", "siniestrada_ha",
          "produccion", "rendimiento", "aviso"]


# ------------------------------------------------------------------ red
def abrir_sesion():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0 (EloteSat QGIS plugin; uso academico)"),
                     ("Referer", URL)]
    op.open(URL, timeout=60).read()          # coge la cookie PHPSESSID
    return op


def consultar(op, anio, ciclo, modalidad, cultivo, mes,
              entidad=ENTIDAD, tipo=(0, 1)):
    args = [1, anio, ciclo, modalidad, entidad, 0, 0, cultivo, 200201,
            tipo[0], tipo[1], "undefined", "undefined", "undefined", mes]
    datos = [("xajax", "reporte"),
             ("xajaxr", str(int(time.time() * 1000)))]
    datos += [("xajaxargs[]", str(a)) for a in args]
    req = urllib.request.Request(
        URL, data=urllib.parse.urlencode(datos).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Origin": "https://nube.agricultura.gob.mx"})
    crudo = op.open(req, timeout=120).read()
    return decodificar(crudo)


def decodificar(b):
    # El XML dice iso-8859-1, pero el HTML de la web va en UTF-8: probamos las dos.
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("iso-8859-1")


# ------------------------------------------------------------------ lectura
def limpiar(s):
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def numero(s):
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def leer_respuesta(texto):
    """Devuelve una lista de bloques [(cabecera, filas)].

    A veces la web añade debajo el mismo corte del año agrícola anterior,
    con su propia cabecera: cada bloque se lee por separado.
    """
    m = re.search(r"<!\[CDATA\[(.*?)\]\]>", texto, re.S)
    cuerpo = m.group(1) if m else texto
    cuerpo = re.sub(r"<!--.*?-->", "", cuerpo, flags=re.S)
    trozos = re.split(r'(?=<div class="titulosTabla">)', cuerpo)
    bloques = []
    for tz in trozos:
        if "titulosTabla" not in tz:
            continue
        bloques.append((leer_cabecera(tz), leer_filas(tz)))
    return bloques


def leer_cabecera(tz):
    cab = {}
    mc = re.search(r'titulosTabla">(.*?)</div>', tz, re.S)
    if mc:
        t = limpiar(mc.group(1))
        for clave, patron in [("anio", r"Año agrícola:\s*(\d{4})"),
                              ("ciclo", r"Ciclo:\s*(.*?)\s+Modalidad:"),
                              ("modalidad", r"Modalidad:\s*(.*?)\s+(?:Cultivo:|Entidad|Situación)"),
                              ("cultivo", r"Cultivo:\s*(.*?)\s+(?:Entidad|Situación)"),
                              ("corte", r"Situación al\s*(.*)$")]:
            x = re.search(patron, t)
            if x:
                cab[clave] = x.group(1).strip()
    cab["fecha_corte"] = fecha_iso(cab.get("corte", ""))
    return cab


def leer_filas(tz):
    filas = []
    for tr in re.findall(r"<tr>(.*?)</tr>", tz, re.S):
        tds = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
        if not tds:
            continue                         # cabeceras y total (van en <th>)
        textos = [limpiar(c) for a, c in tds if "tdNum" not in a][1:]
        nums = [numero(limpiar(c)) for a, c in tds if "tdNum" in a]
        if len(nums) < 5 or not textos:
            continue
        filas.append({"entidad": textos[0],
                      "distrito": textos[1] if len(textos) >= 3 else "",
                      "municipio": textos[-1],
                      "sembrada_ha": nums[0], "cosechada_ha": nums[1],
                      "siniestrada_ha": nums[2], "produccion": nums[3],
                      "rendimiento": nums[4]})
    return filas


def fecha_iso(s):
    m = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", s)
    if not m or m.group(2).lower() not in MESES_ES:
        return ""
    return "%s-%02d-%02d" % (m.group(3), MESES_ES[m.group(2).lower()],
                             int(m.group(1)))


def comprobar(cab, ciclo, modalidad, cultivo):
    avisos = []
    if cab.get("ciclo") and cab["ciclo"] != CICLOS[ciclo]:
        avisos.append("ciclo recibido: %s" % cab["ciclo"])
    if cab.get("modalidad") and cab["modalidad"] != MODALIDADES[modalidad]:
        avisos.append("modalidad recibida: %s" % cab["modalidad"])
    if not cab.get("cultivo", "").startswith(CULTIVOS[cultivo]):
        avisos.append("cultivo recibido: %s" % cab.get("cultivo", "(ninguno)"))
    return "; ".join(avisos)



# ------------------------------------------------------------------ plan
def plan(anios, ciclos=(1, 2)):
    """(consult year, month) pairs that cover the agricultural years
    `anios` completely, for each cycle: [(anio_consulta, ciclo, mes)]."""
    out = set()
    for y in anios:
        if 1 in ciclos:
            out |= {(y - 1, 1, m) for m in (10, 11, 12)}
            out |= {(y, 1, m) for m in range(1, 13)}
        if 2 in ciclos:
            out |= {(y, 2, m) for m in range(4, 13)}
            out |= {(y + 1, 2, m) for m in (1, 2, 3)}
    return sorted(out)


def download(anios, out_csv, raw_dir=None, pause=3.0, ciclos=(1, 2),
             feedback=None, cancel_check=None, opener=None, today=None):
    """Download and write one long CSV (same columns as descarga_siap.py).
    Future months are skipped. Returns (rows written, requests, errors)."""
    import datetime as dt
    log = feedback or (lambda m: None)
    today = today or dt.date.today()
    combos = [(an, c, mo, cu, me) for an, c, me in plan(anios, ciclos)
              if dt.date(an, me, 1) <= today
              for mo in MODALIDADES for cu in CULTIVOS]
    raw_dir = raw_dir or os.path.join(os.path.dirname(out_csv),
                                      "siap_crudos")
    os.makedirs(raw_dir, exist_ok=True)
    op = opener or abrir_sesion()
    n_rows, errors = 0, []
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        for i, (an, c, mo, cu, me) in enumerate(combos, 1):
            if cancel_check and cancel_check():
                break
            tag = "%d_%s_%s_%s_mes%02d" % (
                an, "OI" if c == 1 else "PV", MODALIDADES[mo].lower(),
                "sorgo" if cu == 374 else "maiz", me)
            try:
                texto = consultar(op, an, c, mo, cu, me)
            except Exception as e:
                errors.append("%s: %s" % (tag, e))
                log("[%d/%d] %s ERROR: %s" % (i, len(combos), tag, e))
                time.sleep(pause * 3)
                continue
            with open(os.path.join(raw_dir, tag + ".xml"), "w",
                      encoding="utf-8") as fr:
                fr.write(texto)
            rows = rows_from_response(texto, an, c, mo, cu, me)
            for r in rows:
                w.writerow(r)
            n_rows += len(rows)
            log("[%d/%d] %s: %d filas" % (i, len(combos), tag, len(rows)))
            time.sleep(pause)
    return n_rows, len(combos), errors


def rows_from_response(texto, an, c, mo, cu, me):
    """CSV rows of one response (every block, with its own header)."""
    out = []
    for cab, filas in (leer_respuesta(texto) or [({}, [])]):
        aviso = comprobar(cab, c, mo, cu)
        if not filas:
            aviso = (aviso + "; " if aviso else "") + "sin datos"
            filas = [{}]
        for r in filas:
            r = dict(r)
            r.update({"anio_consulta": an,
                      "anio_agricola": cab.get("anio", ""),
                      "ciclo": CICLOS[c], "modalidad": MODALIDADES[mo],
                      "cultivo": CULTIVOS[cu], "mes_consulta": me,
                      "fecha_corte": cab.get("fecha_corte", ""),
                      "aviso": aviso})
            out.append(r)
    return out


def parse_raw_dir(raw_dir, out_csv):
    """Rebuild the CSV from saved raw responses (file names as written
    by download()). Useful to re-check the parsing without the network."""
    rx = re.compile(r"^(\d{4})_(OI|PV)_(riego|temporal)_(sorgo|maiz)_mes"
                    r"(\d{2})\.xml$")
    n = 0
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        for name in sorted(os.listdir(raw_dir)):
            m = rx.match(name)
            if not m:
                continue
            an, c, mo, cu, me = (int(m.group(1)),
                                 1 if m.group(2) == "OI" else 2,
                                 1 if m.group(3) == "riego" else 2,
                                 374 if m.group(4) == "sorgo" else 225,
                                 int(m.group(5)))
            with open(os.path.join(raw_dir, name), encoding="utf-8") as fr:
                for r in rows_from_response(fr.read(), an, c, mo, cu, me):
                    w.writerow(r)
                    n += 1
    return n
