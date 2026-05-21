# -*- coding: utf-8 -*-
import arcpy
import math
import os

class Toolbox(object):
    def __init__(self):
        self.label = "Vértices con Atributos y DMS"
        self.alias = "vert_attr_dms"
        self.tools = [VerticesAtributosDMS]

class VerticesAtributosDMS(object):
    def __init__(self):
        self.label = "Extraer Vértices — Atributos + DMS Hemisferio"
        self.description = "Extrae vértices adoptando todos los atributos originales y calculando DMS profesional."
        self.canRunInBackground = False

    def getParameterInfo(self):
        p0 = arcpy.Parameter("in_polygons", "Capa(s) poligonal(es) de entrada", "Input", "Feature Layer", "Required", multiValue=True)
        p0.filter.list = ["Polygon"]
        p1 = arcpy.Parameter("out_fc", "Shapefile de puntos de salida", "Output", "Feature Class", "Required")
        p2 = arcpy.Parameter("out_excel", "Archivo Excel de salida", "Output", "File", "Required")
        p2.filter.list = ["xlsx"]
        return [p0, p1, p2]

    # ──────────────────────────────────────────────────────────────────────────
    # MÉTODOS DE CÁLCULO (Lógica pura)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _dec_a_dms(valor):
        """Convierte decimal a GMS con precisión de 4 decimales en segundos."""
        abs_val = abs(valor)
        g = int(abs_val)
        m = int((abs_val - g) * 60)
        s = round(((abs_val - g) * 60 - m) * 60, 4)
        # Corrección de desbordamiento por redondeo (60.0" -> 1')
        if s >= 60.0:
            s = 0.0
            m += 1
        if m >= 60:
            m = 0
            g += 1
        return g, m, s

    def format_coord(self, val, tipo="LAT"):
        g, m, s = self._dec_a_dms(val)
        if tipo == "LAT":
            hem = "N" if val >= 0 else "S"
        else:
            hem = "E" if val >= 0 else "W"
        return u"{}° {:02d}' {:07.4f}\" {}".format(g, m, s, hem)

    @staticmethod
    def _azimut_rumbo(x1, y1, x2, y2):
        """Calcula Azimut y Rumbo en una sola pasada para ahorrar ciclos."""
        dx, dy = x2 - x1, y2 - y1
        az = math.degrees(math.atan2(dx, dy)) % 360.0
        
        # Lógica de Rumbo
        def to_dms_str(v):
            d = int(v); m = int((v-d)*60); s = round(((v-d)*60-m)*60, 1)
            return u"{}°{:02d}'{:04.1f}\"".format(d, m, s)

        if az == 0 or az == 360: r = "N 00°00'00\" E"
        elif 0 < az < 90:   r = "N {} E".format(to_dms_str(az))
        elif az == 90:      r = "E 90°00'00\""
        elif 90 < az < 180: r = "S {} E".format(to_dms_str(180 - az))
        elif az == 180:     r = "S 00°00'00\" W"
        elif 180 < az < 270:r = "S {} W".format(to_dms_str(az - 180))
        elif az == 270:     r = "W 90°00'00\""
        else:               r = "N {} W".format(to_dms_str(360 - az))
        return round(az, 4), r

    @staticmethod
    def _haversine(x1, y1, x2, y2):
        R = 6371000.0
        phi1, phi2 = math.radians(y1), math.radians(y2)
        dphi, dlam = math.radians(y2-y1), math.radians(x2-x1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        return round(2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a)), 4)

    # ──────────────────────────────────────────────────────────────────────────
    # GESTIÓN DE CAMPOS (Adopción de Atributos)
    # ──────────────────────────────────────────────────────────────────────────

    def _preparar_esquema(self, capas, output_fc):
        """Analiza todas las capas y crea el esquema unificado en el destino."""
        excluir = {"shape_length", "shape_area", "shape", "objectid", "fid"}
        tipos_validos = {"OID", "Geometry", "GlobalID", "Guid"}
        
        nombres_usados = ["OBJECTID", "Shape", "Capa", "Src_FID", "Vert_Num", "Vert_Tot", 
                          "X_Dec", "Y_Dec", "Lat_DMS", "Lon_DMS", "Sentido", "Azimut", "Rumbo", "Dist_m"]
        
        mapa_global = {} # nom_original -> nom_seguro
        esquema = []     # (nom_seguro, tipo, longitud)

        for capa in capas:
            for f in arcpy.ListFields(capa):
                if f.type in tipos_validos or f.name.lower() in excluir: continue
                if f.name not in mapa_global:
                    # Crear nombre seguro para Shapefile (max 10 chars)
                    base = ("O_" + f.name)[:10]
                    candidato = base
                    idx = 1
                    while candidato.upper() in [n.upper() for n in nombres_usados]:
                        sufijo = str(idx)
                        candidato = base[:10-len(sufijo)] + sufijo
                        idx += 1
                    
                    mapa_global[f.name] = candidato
                    nombres_usados.append(candidato)
                    esquema.append((candidato, f.type, f.length))

        # Crear campos en el FC de salida
        for nom, tipo, lon in esquema:
            if tipo == "String": arcpy.AddField_management(output_fc, nom, "TEXT", field_length=max(lon, 60))
            elif tipo in ("Double", "Single"): arcpy.AddField_management(output_fc, nom, "DOUBLE")
            elif tipo in ("Integer", "SmallInteger"): arcpy.AddField_management(output_fc, nom, "LONG")
            elif tipo == "Date": arcpy.AddField_management(output_fc, nom, "DATE")
            else: arcpy.AddField_management(output_fc, nom, "TEXT", field_length=100)
            
        return mapa_global

    # ──────────────────────────────────────────────────────────────────────────
    # EJECUCIÓN PRINCIPAL
    # ──────────────────────────────────────────────────────────────────────────

    def execute(self, params, messages):
        capas_in = [str(c).strip("'") for c in params[0].valueAsText.split(";")]
        out_fc = params[1].valueAsText
        out_xls = params[2].valueAsText
        
        arcpy.env.overwriteOutput = True
        wgs84 = arcpy.SpatialReference(4326)

        # Crear Feature Class
        path, name = os.path.split(out_fc)
        arcpy.CreateFeatureclass_management(path or arcpy.env.scratchGDB, name, "POINT", spatial_reference=wgs84)
        
        # Campos de cálculo fijos
        fijos = [("Capa", "TEXT", 80), ("Src_FID", "LONG"), ("Vert_Num", "SHORT"), ("Vert_Tot", "SHORT"),
                 ("X_Dec", "DOUBLE"), ("Y_Dec", "DOUBLE"), ("Lat_DMS", "TEXT", 45), ("Lon_DMS", "TEXT", 45),
                 ("Sentido", "TEXT", 15), ("Azimut", "DOUBLE"), ("Rumbo", "TEXT", 35), ("Dist_m", "DOUBLE")]
        
        for f in fijos:
            arcpy.AddField_management(out_fc, f[0], f[1], field_length=f[2] if len(f)>2 else None)

        # Bloque 1: Adoptar Atributos
        mapa_attr = self._preparar_esquema(capas_in, out_fc)
        nombres_orig = sorted(mapa_attr.keys())
        nombres_dest = [mapa_attr[n] for n in nombres_orig]

        # Inserción de datos
        insert_fields = ["SHAPE@"] + [f[0] for f in fijos] + nombres_dest
        datos_excel = []
        resumen_excel = []

        with arcpy.da.InsertCursor(out_fc, insert_fields) as icur:
            for capa in capas_in:
                messages.addMessage(u"Procesando: {}".format(os.path.basename(capa)))
                
                # Proyección al vuelo para precisión DMS
                sr_capa = arcpy.Describe(capa).spatialReference
                if sr_capa.factoryCode != 4326:
                    capa_work = arcpy.Project_management(capa, "in_memory/tmp_prj", wgs84)
                else:
                    capa_work = capa

                campos_capa = [f.name for f in arcpy.ListFields(capa_work)]
                disp_capa = [n for n in nombres_orig if n in campos_capa]
                
                with arcpy.da.SearchCursor(capa_work, ["SHAPE@", "OID@"] + disp_capa) as scur:
                    for srow in scur:
                        poly = srow[0]
                        fid = srow[1]
                        # Diccionario de atributos originales
                        attr_vals = dict(zip(disp_capa, srow[2:]))
                        
                        # Extraer vértices ordenados
                        centro = poly.centroid
                        # Ignorar último punto si es igual al primero (cierre de anillo)
                        pts = []
                        for part in poly:
                            p_list = [p for p in part if p]
                            if p_list and p_list[0].equals(p_list[-1]): p_list = p_list[:-1]
                            pts.extend([(p.X, p.Y) for p in p_list])
                        
                        # Ordenar horario respecto al centroide
                        pts.sort(key=lambda p: (90 - math.degrees(math.atan2(p[1]-centro.Y, p[0]-centro.X))) % 360)
                        
                        total_v = len(pts)
                        perim_acum = 0
                        
                        for i, (x1, y1) in enumerate(pts):
                            x2, y2 = pts[(i + 1) % total_v]
                            
                            lat_s = self.format_coord(y1, "LAT")
                            lon_s = self.format_coord(x1, "LON")
                            az, rbo = self._azimut_rumbo(x1, y1, x2, y2)
                            dist = self._haversine(x1, y1, x2, y2)
                            perim_acum += dist
                            
                            # Sentido cardinal relativo al centroide
                            dx, dy = x1 - centro.X, y1 - centro.Y
                            br = (90 - math.degrees(math.atan2(dy, dx))) % 360
                            snt = "Norte"
                            for lim, n in [(22.5,"Norte"),(67.5,"Noreste"),(112.5,"Este"),(157.5,"Sureste"),
                                           (202.5,"Sur"),(247.5,"Suroeste"),(292.5,"Oeste"),(337.5,"Noroeste")]:
                                if br < lim: snt = n; break

                            # Preparar fila para InsertCursor
                            fila_fija = [arcpy.Point(x1, y1), os.path.basename(capa), fid, i+1, total_v, 
                                         x1, y1, lat_s, lon_s, snt, az, rbo, dist]
                            fila_attr = [attr_vals.get(n) for n in nombres_orig]
                            icur.insertRow(fila_fija + fila_attr)
                            
                            # Guardar para Excel
                            ex_row = dict(zip([f[0] for f in fijos], fila_fija[1:]))
                            for n in nombres_orig: ex_row["[ORIG] " + n] = attr_vals.get(n)
                            datos_excel.append(ex_row)

                        resumen_excel.append({
                            "Capa": os.path.basename(capa), "Src_FID": fid, "Vértices": total_v,
                            "Perímetro_m": round(perim_acum, 2), "Centro_X": centro.X, "Centro_Y": centro.Y
                        })

        # Bloque Excel con openpyxl
        try:
            import openpyxl
            from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
            wb = openpyxl.Workbook()
            # Hoja de Vértices
            ws1 = wb.active
            ws1.title = "Vértices"
            if datos_excel:
                headers = list(datos_excel[0].keys())
                for c, h in enumerate(headers, 1):
                    cell = ws1.cell(1, c, h)
                    cell.fill = PatternFill("solid", fgColor="1B5E20" if "[ORIG]" in h else "1F4E79")
                    cell.font = Font(color="FFFFFF", bold=True)
                    cell.alignment = Alignment(horizontal="center")
                for r, row in enumerate(datos_excel, 2):
                    for c, h in enumerate(headers, 1):
                        ws1.cell(r, c, row.get(h))
            # Hoja Resumen
            ws2 = wb.create_sheet("Resumen")
            if resumen_excel:
                h2 = list(resumen_excel[0].keys())
                for c, h in enumerate(h2, 1):
                    ws2.cell(1, c, h).font = Font(bold=True)
                for r, row in enumerate(resumen_excel, 2):
                    for c, h in enumerate(h2, 1):
                        ws2.cell(r, c, row.get(h))
            wb.save(out_xls)
            messages.addMessage(u"Excel generado: {}".format(out_xls))
        except:
            messages.addWarning("No se pudo usar openpyxl. Use TableToExcel manualmente.")

        arcpy.Delete_management("in_memory")