# -*- coding: utf-8 -*-
"""
VerticesAtributosDMS.pyt
Herramienta ArcPy especializada en:
  1. ADOPCIÓN DE ATRIBUTOS: copia todos los campos del polígono original
     a cada vértice extraído.
  2. DMS CON HEMISFERIO CORRECTO: Lat/Lon en grados-minutos-segundos
     con indicador N/S y E/W (esencial para Colombia y toda América).

Salidas:
  - Shapefile de puntos (vértices) con atributos heredados
  - Excel con hoja "Vértices" (columnas originales resaltadas en verde)
    y hoja "Resumen" por feature.

Versión : 1.0
"""

import arcpy
import math
import os

# ═══════════════════════════════════════════════════════════════════════════════
class Toolbox(object):
    def __init__(self):
        self.label  = "Vértices con Atributos y DMS"
        self.alias  = "vert_attr_dms"
        self.tools  = [VerticesAtributosDMS]


# ═══════════════════════════════════════════════════════════════════════════════
class VerticesAtributosDMS(object):

    def __init__(self):
        self.label = "Extraer Vértices — Atributos + DMS Hemisferio"
        self.description = (
            "Extrae vértices de uno o varios polígonos.\n"
            "• Adopta TODOS los atributos del archivo original en cada vértice.\n"
            "• Calcula Lat/Lon en DMS con hemisferio correcto (N/S, E/W).\n"
            "• Incluye azimut, rumbo, distancia y sentido cardinal."
        )
        self.canRunInBackground = False

    # ──────────────────────────────────────────────────────────────────────────
    # PARÁMETROS
    # ──────────────────────────────────────────────────────────────────────────
    def getParameterInfo(self):

        p0 = arcpy.Parameter(
            displayName   = "Capa(s) poligonal(es) de entrada",
            name          = "in_polygons",
            datatype      = "Feature Layer",
            parameterType = "Required",
            direction     = "Input",
            multiValue    = True)
        p0.filter.list = ["Polygon"]

        p1 = arcpy.Parameter(
            displayName   = "Shapefile de puntos de salida",
            name          = "out_fc",
            datatype      = "Feature Class",
            parameterType = "Required",
            direction     = "Output")

        p2 = arcpy.Parameter(
            displayName   = "Archivo Excel de salida",
            name          = "out_excel",
            datatype      = "File",
            parameterType = "Required",
            direction     = "Output")
        p2.filter.list = ["xlsx"]

        return [p0, p1, p2]

    def isLicensed(self):   return True
    def updateParameters(self, p): return
    def updateMessages(self, p):   return

    # ──────────────────────────────────────────────────────────────────────────
    # ▌ BLOQUE 1 — ADOPCIÓN DE ATRIBUTOS
    # ──────────────────────────────────────────────────────────────────────────
    #
    #  Problema que resuelve:
    #    Cuando un polígono tiene atributos (nombre del predio, área catastral,
    #    propietario, código, etc.), al extraer los vértices esa información se
    #    pierde porque los puntos son entidades nuevas.
    #
    #  Solución implementada:
    #    a) _leer_campos_originales()  → descubre qué campos tiene el polígono
    #       (excluye OBJECTID, Shape, Shape_Area, Shape_Length que son internos).
    #    b) _nombre_campo_seguro()     → trunca y desambigua nombres a ≤10 chars
    #       para que sean válidos en Shapefile (límite del formato .shp).
    #    c) _crear_campos_origen()     → agrega esos campos al FC de salida
    #       con el mismo tipo de dato (texto, numérico, fecha).
    #    d) En el cursor de inserción se incluyen los valores del polígono
    #       original y se copian literalmente a cada vértice de ese polígono.
    #
    #  Resultado:
    #    Cada punto hereda todos los atributos del polígono al que pertenece,
    #    permitiendo filtrar, etiquetar y analizar los vértices con contexto.

    @staticmethod
    def _leer_campos_originales(fc):
        """
        Retorna [(nombre, tipo_arcpy, longitud)] de los campos de usuario.
        Excluye campos internos de ArcGIS que no aportan información temática.
        """
        EXCLUIR_TIPOS  = {"OID", "Geometry", "GlobalID", "Guid"}
        EXCLUIR_NOMBRES = {
            "shape_length", "shape_area",
            "shape", "objectid", "fid"
        }
        resultado = []
        for f in arcpy.ListFields(fc):
            if f.type in EXCLUIR_TIPOS:
                continue
            if f.name.lower() in EXCLUIR_NOMBRES:
                continue
            resultado.append((f.name, f.type, f.length))
        return resultado

    @staticmethod
    def _nombre_campo_seguro(nombre_propuesto, nombres_usados, max_len=10):
        """
        Garantiza que el nombre de campo:
          - No supere max_len caracteres (límite Shapefile = 10).
          - No colisione con ningún campo ya existente.
        Si hay colisión agrega un sufijo numérico (ej. MiCamp → MiCam_1).
        """
        base      = nombre_propuesto[:max_len]
        candidato = base
        contador  = 1
        usados_up = [n.upper() for n in nombres_usados]
        while candidato.upper() in usados_up:
            sfx       = str(contador)
            candidato = base[:max_len - len(sfx)] + sfx
            contador += 1
        nombres_usados.append(candidato)
        return candidato

    @staticmethod
    def _crear_campos_origen(fc, campos_info, nombres_usados):
        """
        Agrega al FC de salida los campos heredados del polígono.
        Devuelve un dict  nombre_original → nombre_en_salida
        para usarlo al copiar valores.
        """
        mapa = {}
        for (nom_orig, tipo_arc, longitud) in campos_info:
            # Prefijo "O_" indica campo "Original" → fácil de identificar en tabla
            propuesto = "O_" + nom_orig
            nom_salida = VerticesAtributosDMS._nombre_campo_seguro(
                propuesto, nombres_usados)

            # Mapear tipos ArcGIS → tipos AddField
            if tipo_arc in ("String",):
                arcpy.management.AddField(fc, nom_salida, "TEXT",
                                          field_length=max(longitud, 60))
            elif tipo_arc in ("Integer", "SmallInteger"):
                arcpy.management.AddField(fc, nom_salida, "LONG")
            elif tipo_arc in ("Single", "Double"):
                arcpy.management.AddField(fc, nom_salida, "DOUBLE")
            elif tipo_arc == "Date":
                arcpy.management.AddField(fc, nom_salida, "DATE")
            else:
                # Cualquier otro tipo (BLOB, Raster, etc.) → texto legible
                arcpy.management.AddField(fc, nom_salida, "TEXT",
                                          field_length=100)
            mapa[nom_orig] = nom_salida
        return mapa

    # ──────────────────────────────────────────────────────────────────────────
    # ▌ BLOQUE 2 — DMS CON HEMISFERIO CORRECTO
    # ──────────────────────────────────────────────────────────────────────────
    #
    #  Problema que resuelve:
    #    Las coordenadas geográficas en grados decimales son negativas para el
    #    hemisferio sur (latitud) y para el hemisferio oeste (longitud).
    #    Ej.: Pitalito, Colombia  →  Lat = -1.87°,  Lon = -76.04°
    #
    #    La conversión naïve  int(-1.87) → -1°  produce DMS ambiguos:
    #      "-1° 52' 12\""  — ¿es norte o sur?  El signo no es estándar.
    #
    #  Solución implementada:
    #    a) Trabajar siempre con el valor ABSOLUTO para los grados/min/seg.
    #    b) Asignar el indicador de hemisferio según el signo original:
    #         Latitud  ≥ 0  →  "N"    Latitud  < 0  →  "S"
    #         Longitud ≥ 0  →  "E"    Longitud < 0  →  "W"
    #    c) Formatear como:   1° 52' 12.0000" S   /   76° 02' 24.0000" W
    #       (forma estándar cartográfica usada en levantamientos topográficos)
    #
    #  Ejemplos reales (Colombia):
    #    Lat  = -1.8700  →  1° 52' 12.0000" S
    #    Lon  = -76.0400 →  76° 02' 24.0000" W
    #    Lat  =  4.7110  →  4° 42' 39.6000" N   (Neiva)
    #    Lon  = -75.2820 →  75° 16' 55.2000" W

    @staticmethod
    def _dec_a_dms(valor_decimal):
        """
        Convierte grados decimales a (grados, minutos, segundos).
        Opera sobre el valor ABSOLUTO; el signo/hemisferio lo maneja
        el llamador (format_lat / format_lon).
        """
        abs_val  = abs(valor_decimal)
        grados   = int(abs_val)
        minutos  = int((abs_val - grados) * 60)
        segundos = round(((abs_val - grados) * 60 - minutos) * 60, 4)
        return grados, minutos, segundos

    def format_lat(self, y):
        """
        Latitud en DMS con hemisferio.
        Ejemplos:
          y =  4.7110  →  '4° 42' 39.6000" N'
          y = -1.8700  →  '1° 52' 12.0000" S'
        """
        g, m, s  = self._dec_a_dms(y)
        hemisferio = "N" if y >= 0 else "S"
        return f"{g}° {m:02d}' {s:.4f}\" {hemisferio}"

    def format_lon(self, x):
        """
        Longitud en DMS con hemisferio.
        Ejemplos:
          x = -76.0400 →  '76° 02' 24.0000" W'
          x =  75.2820 →  '75° 16' 55.2000" E'
        """
        g, m, s  = self._dec_a_dms(x)
        hemisferio = "E" if x >= 0 else "W"
        return f"{g}° {m:02d}' {s:.4f}\" {hemisferio}"

    # ──────────────────────────────────────────────────────────────────────────
    # UTILIDADES ADICIONALES (azimut, rumbo, distancia, sentido)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _azimut(x1, y1, x2, y2):
        ang = math.degrees(math.atan2(x2 - x1, y2 - y1))
        return round(ang % 360.0, 4)

    @staticmethod
    def _rumbo(az):
        def dms(v):
            d = int(v); m = int((v - d) * 60)
            s = round(((v - d) * 60 - m) * 60, 1)
            return f"{d}°{m:02d}'{s:04.1f}\""
        az = az % 360.0
        if   az == 0:                return "N 0°00'00.0\" E"
        elif 0   < az < 90:          return f"N {dms(az)} E"
        elif az == 90:               return "N 90°00'00.0\" E"
        elif 90  < az < 180:         return f"S {dms(180 - az)} E"
        elif az == 180:              return "S 0°00'00.0\" W"
        elif 180 < az < 270:         return f"S {dms(az - 180)} W"
        elif az == 270:              return "N 90°00'00.0\" W"
        else:                        return f"N {dms(360 - az)} W"

    @staticmethod
    def _sentido(x, y, cx, cy):
        dx, dy = x - cx, y - cy
        bear   = (90 - math.degrees(math.atan2(dy, dx))) % 360
        for lim, nombre in [(22.5,"Norte"),(67.5,"Noreste"),(112.5,"Este"),
                            (157.5,"Sureste"),(202.5,"Sur"),(247.5,"Suroeste"),
                            (292.5,"Oeste"),(337.5,"Noroeste")]:
            if bear < lim: return nombre
        return "Norte"

    @staticmethod
    def _haversine(x1, y1, x2, y2):
        R   = 6_371_000.0
        lat1, lat2 = math.radians(y1), math.radians(y2)
        dlat = math.radians(y2 - y1)
        dlon = math.radians(x2 - x1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
        return round(2 * R * math.asin(math.sqrt(min(a, 1.0))), 4)

    @staticmethod
    def _ordenar_horario(vertices, centroide):
        def angulo_norte_horario(p):
            return (90 - math.degrees(
                math.atan2(p[1] - centroide.Y, p[0] - centroide.X))) % 360
        return sorted(vertices, key=angulo_norte_horario)

    # ──────────────────────────────────────────────────────────────────────────
    # EXECUTE
    # ──────────────────────────────────────────────────────────────────────────
    def execute(self, params, messages):

        layers_raw = params[0].values
        output_fc  = params[1].valueAsText
        excel_path = params[2].valueAsText

        arcpy.env.overwriteOutput = True
        wgs84 = arcpy.SpatialReference(4326)

        # Normalizar lista de capas
        if isinstance(layers_raw, list):
            capas = layers_raw
        else:
            capas = str(layers_raw).split(";")

        capas = [str(c).strip("'\" ") for c in capas]
        messages.addMessage(f"▶ Capas recibidas: {len(capas)}")

        # ── Crear FC de salida ──────────────────────────────────────────────
        out_folder = os.path.dirname(output_fc) or arcpy.env.workspace or os.getcwd()
        out_name   = os.path.basename(output_fc)
        arcpy.management.CreateFeatureclass(out_folder, out_name, "POINT",
                                            spatial_reference=wgs84)

        # Campos fijos calculados
        nombres_usados = ["OBJECTID", "Shape"]
        CAMPOS_FIJOS = [
            ("Capa",      "TEXT",   80),
            ("Src_FID",   "LONG",    0),
            ("Vert_Num",  "SHORT",   0),
            ("Vert_Tot",  "SHORT",   0),
            ("X_Dec",     "DOUBLE",  0),
            ("Y_Dec",     "DOUBLE",  0),
            ("Lat_DMS",   "TEXT",   45),   # ← DMS con hemisferio
            ("Lon_DMS",   "TEXT",   45),   # ← DMS con hemisferio
            ("Sentido",   "TEXT",   15),
            ("Azimut",    "DOUBLE",  0),
            ("Rumbo",     "TEXT",   35),
            ("Dist_m",    "DOUBLE",  0),
        ]
        for fname, ftype, flen in CAMPOS_FIJOS:
            nombres_usados.append(fname)
            if ftype == "TEXT":
                arcpy.management.AddField(output_fc, fname, ftype, field_length=flen)
            else:
                arcpy.management.AddField(output_fc, fname, ftype)

        # ── BLOQUE 1: Descubrir y crear campos originales de todas las capas ─
        mapa_global   = {}   # nombre_original → nombre_en_salida
        esquema_union = {}   # nombre_original → (tipo, longitud)

        for capa in capas:
            for (nom, tipo, long_) in self._leer_campos_originales(capa):
                if nom not in esquema_union:
                    esquema_union[nom] = (tipo, long_)

        campos_info_lista = [(n, t, l) for n, (t, l) in esquema_union.items()]
        mapa_global = self._crear_campos_origen(output_fc, campos_info_lista,
                                                nombres_usados)

        nombres_orig_src = list(mapa_global.keys())
        nombres_orig_out = list(mapa_global.values())
        messages.addMessage(f"▶ Campos originales adoptados: {len(nombres_orig_src)}")
        for src, out_ in mapa_global.items():
            messages.addMessage(f"    {src}  →  {out_}")

        # ── Cursor de inserción ─────────────────────────────────────────────
        insert_cols = (["SHAPE@"] +
                       [f[0] for f in CAMPOS_FIJOS] +
                       nombres_orig_out)

        datos_excel = []
        resumen     = []
        feat_global = 0

        with arcpy.da.InsertCursor(output_fc, insert_cols) as icur:

            for capa in capas:
                nombre_capa = os.path.basename(capa)
                messages.addMessage(f"  ● {nombre_capa}")

                # Proyectar a WGS84 si es necesario
                sr_src = arcpy.Describe(capa).spatialReference
                if sr_src.factoryCode != 4326:
                    tmp = "in_memory/tmp_prj_{}".format(
                        nombre_capa.replace(" ","_").replace(".","_"))
                    arcpy.management.Project(capa, tmp, wgs84)
                    work = tmp
                else:
                    work = capa

                # Campos disponibles en esta capa
                disp = [f.name for f in arcpy.ListFields(work)
                        if f.name in nombres_orig_src]
                search_cols = ["SHAPE@", "OID@"] + disp

                with arcpy.da.SearchCursor(work, search_cols) as scur:
                    for srow in scur:
                        poly    = srow[0]
                        src_fid = srow[1]
                        vals    = list(srow[2:])

                        # ── BLOQUE 1: construir dict con valores originales ──
                        # Los campos que no existen en esta capa quedan None
                        attr_dict = {}
                        vi = 0
                        for nom in nombres_orig_src:
                            if nom in disp:
                                attr_dict[nom] = vals[vi]; vi += 1
                            else:
                                attr_dict[nom] = None

                        centroide = poly.centroid

                        # Recolectar vértices (sin cierre de anillo)
                        raw = []
                        for parte in poly:
                            pts = [p for p in parte if p is not None]
                            if (len(pts) > 1 and
                                    abs(pts[0].X - pts[-1].X) < 1e-9 and
                                    abs(pts[0].Y - pts[-1].Y) < 1e-9):
                                pts = pts[:-1]
                            raw += [(p.X, p.Y) for p in pts]

                        if not raw:
                            messages.addWarning(
                                f"    ⚠ FID={src_fid} sin vértices, omitida.")
                            continue

                        verts = self._ordenar_horario(raw, centroide)
                        n     = len(verts)
                        feat_global += 1
                        perim = 0.0

                        for i, (x1, y1) in enumerate(verts):
                            x2, y2 = verts[(i + 1) % n]

                            # ── BLOQUE 2: DMS con hemisferio correcto ───────
                            lat_dms = self.format_lat(y1)
                            lon_dms = self.format_lon(x1)
                            # ────────────────────────────────────────────────

                            snt  = self._sentido(x1, y1, centroide.X, centroide.Y)
                            az   = self._azimut(x1, y1, x2, y2)
                            rbo  = self._rumbo(az)
                            dist = self._haversine(x1, y1, x2, y2)
                            perim += dist

                            fila = ([arcpy.Point(x1, y1)]
                                    + [nombre_capa, src_fid, i + 1, n,
                                       x1, y1, lat_dms, lon_dms,
                                       snt, az, rbo, dist]
                                    + [attr_dict.get(nom) for nom in nombres_orig_src])

                            icur.insertRow(fila)

                            excel_row = {
                                "Capa"    : nombre_capa,
                                "Src_FID" : src_fid,
                                "Vert_Num": i + 1,
                                "Vert_Tot": n,
                                "X_Dec"   : x1,
                                "Y_Dec"   : y1,
                                "Lat_DMS" : lat_dms,
                                "Lon_DMS" : lon_dms,
                                "Sentido" : snt,
                                "Azimut"  : az,
                                "Rumbo"   : rbo,
                                "Dist_m"  : dist,
                            }
                            # Agregar campos originales con prefijo visible
                            for nom in nombres_orig_src:
                                excel_row[f"[ORIG] {nom}"] = attr_dict.get(nom)

                            datos_excel.append(excel_row)

                        resumen.append({
                            "Capa"       : nombre_capa,
                            "Src_FID"    : src_fid,
                            "N_Vertices" : n,
                            "Perimetro_m": round(perim, 2),
                            "Centroide_X": round(centroide.X, 8),
                            "Centroide_Y": round(centroide.Y, 8),
                        })

        messages.addMessage(f"✔ Shapefile: {output_fc}  ({len(datos_excel)} puntos)")

        # ── Exportar Excel ─────────────────────────────────────────────────
        try:
            import openpyxl
            from openpyxl.styles import (PatternFill, Font, Alignment,
                                         Border, Side)
            from openpyxl.utils import get_column_letter

            AZUL  = PatternFill("solid", fgColor="1F4E79")
            VERDE = PatternFill("solid", fgColor="1B5E20")   # cols originales
            ALT   = PatternFill("solid", fgColor="EBF5FB")
            BORDE = Border(**{s: Side(style="thin")
                              for s in ("left","right","top","bottom")})
            F_BL  = Font(color="FFFFFF", bold=True, size=10)
            CENT  = Alignment(horizontal="center", vertical="center")

            def _estilo_header(cell, orig=False):
                cell.fill      = VERDE if orig else AZUL
                cell.font      = F_BL
                cell.alignment = CENT
                cell.border    = BORDE

            wb   = openpyxl.Workbook()

            # Hoja Vértices
            ws   = wb.active
            ws.title = "Vértices"
            if datos_excel:
                cols = list(datos_excel[0].keys())
                for ci, col in enumerate(cols, 1):
                    _estilo_header(ws.cell(1, ci, col), orig=col.startswith("[ORIG]"))

                for ri, rd in enumerate(datos_excel, 2):
                    fill = ALT if ri % 2 == 0 else PatternFill()
                    for ci, col in enumerate(cols, 1):
                        c = ws.cell(ri, ci, rd.get(col))
                        c.fill = fill; c.border = BORDE

                for ci, col in enumerate(cols, 1):
                    w = max(len(col), max(
                        (len(str(r.get(col) or "")) for r in datos_excel),
                        default=0))
                    ws.column_dimensions[get_column_letter(ci)].width = min(w+3, 55)
                ws.freeze_panes = "A2"
                ws.auto_filter.ref = ws.dimensions

            # Hoja Resumen
            ws2 = wb.create_sheet("Resumen")
            if resumen:
                rcols = list(resumen[0].keys())
                for ci, col in enumerate(rcols, 1):
                    _estilo_header(ws2.cell(1, ci, col))
                for ri, rd in enumerate(resumen, 2):
                    fill = ALT if ri % 2 == 0 else PatternFill()
                    for ci, col in enumerate(rcols, 1):
                        c = ws2.cell(ri, ci, rd.get(col))
                        c.fill = fill; c.border = BORDE
                for ci, col in enumerate(rcols, 1):
                    w = max(len(col), max(
                        (len(str(r.get(col) or "")) for r in resumen), default=0))
                    ws2.column_dimensions[get_column_letter(ci)].width = min(w+3,40)
                ws2.freeze_panes = "A2"

            wb.save(excel_path)
            messages.addMessage(f"✔ Excel: {excel_path}")

        except ImportError:
            # Fallback sin openpyxl
            messages.addWarning("openpyxl no disponible — usando TableToExcel básico.")
            tmp = "in_memory/tmp_excel"
            arcpy.management.CreateTable("in_memory", "tmp_excel")
            cols_flat = list(datos_excel[0].keys()) if datos_excel else []
            for col in cols_flat:
                sc = col.replace("[ORIG] ","O_")[:10]
                v0 = datos_excel[0].get(col)
                t  = "DOUBLE" if isinstance(v0, float) else \
                     "LONG"   if isinstance(v0, int)   else "TEXT"
                arcpy.AddField_management(tmp, sc, t,
                                          **({"field_length":100} if t=="TEXT" else {}))
            sc_list = [c.replace("[ORIG] ","O_")[:10] for c in cols_flat]
            with arcpy.da.InsertCursor(tmp, sc_list) as tc:
                for rd in datos_excel:
                    tc.insertRow([rd.get(c) for c in cols_flat])
            arcpy.conversion.TableToExcel(tmp, excel_path)
            messages.addMessage(f"✔ Excel básico: {excel_path}")

        # ── Resumen final ───────────────────────────────────────────────────
        messages.addMessage("=" * 55)
        messages.addMessage("✔ PROCESO COMPLETADO")
        messages.addMessage(f"  • Features procesadas    : {feat_global}")
        messages.addMessage(f"  • Total vértices         : {len(datos_excel)}")
        messages.addMessage(f"  • Campos originales adoptados: {len(nombres_orig_src)}")
        messages.addMessage(f"  • Shapefile : {output_fc}")
        messages.addMessage(f"  • Excel     : {excel_path}")
        messages.addMessage("=" * 55)
