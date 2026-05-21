# -*- coding: utf-8 -*-
import arcpy
import math
import os

class Toolbox(object):
    def __init__(self):
        self.label = "Vertices 10x"
        self.alias = "vert10x"
        self.tools = [VerticesAtributosDMS]

class VerticesAtributosDMS(object):
    def __init__(self):
        self.label = "Vertices a puntos con atributos + DMS"
        self.description = "Compatible con ArcGIS 10.x"
        self.canRunInBackground = False

    def getParameterInfo(self):
        p0 = arcpy.Parameter(
            name="in_polygons",
            displayName="Capas de entrada",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
            multiValue=True)

        p1 = arcpy.Parameter(
            name="out_fc",
            displayName="Salida puntos",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        p2 = arcpy.Parameter(
            name="out_excel",
            displayName="Excel salida",
            datatype="DEFile",
            parameterType="Required",
            direction="Output")

        return [p0, p1, p2]

    # -----------------------------
    # FUNCIONES
    # -----------------------------
    def dec_a_dms(self, val):
        val = abs(val)
        g = int(val)
        m = int((val - g) * 60)
        s = round(((val - g) * 60 - m) * 60, 4)
        return g, m, s

    def format_coord(self, val, tipo):
        g, m, s = self.dec_a_dms(val)
        if tipo == "LAT":
            hem = "N" if val >= 0 else "S"
        else:
            hem = "E" if val >= 0 else "W"
        return u"%d° %02d' %07.4f\" %s" % (g, m, s, hem)

    def azimut(self, x1, y1, x2, y2):
        dx = x2 - x1
        dy = y2 - y1
        az = math.degrees(math.atan2(dx, dy)) % 360
        return az

    def distancia(self, x1, y1, x2, y2):
        return math.sqrt((x2-x1)**2 + (y2-y1)**2)

    # -----------------------------
    # MAIN
    # -----------------------------
    def execute(self, parameters, messages):

        capas_txt = parameters[0].valueAsText
        capas = capas_txt.split(";")

        out_fc = parameters[1].valueAsText
        out_excel = parameters[2].valueAsText

        arcpy.env.overwriteOutput = True

        # Spatial ref WGS84
        sr = arcpy.SpatialReference(4326)

        # Crear FC
        path, name = os.path.split(out_fc)
        arcpy.CreateFeatureclass_management(path, name, "POINT", spatial_reference=sr)

        # Campos
        arcpy.AddField_management(out_fc, "X", "DOUBLE")
        arcpy.AddField_management(out_fc, "Y", "DOUBLE")
        arcpy.AddField_management(out_fc, "Lat_DMS", "TEXT", "", "", 50)
        arcpy.AddField_management(out_fc, "Lon_DMS", "TEXT", "", "", 50)

        cursor = arcpy.da.InsertCursor(out_fc, ["SHAPE@", "X", "Y", "Lat_DMS", "Lon_DMS"])

        for capa in capas:

            capa = capa.replace("'", "")
            messages.addMessage("Procesando: " + capa)

            # reproyección segura
            tmp = "in_memory\\tmp_prj"
            if arcpy.Exists(tmp):
                arcpy.Delete_management(tmp)

            arcpy.Project_management(capa, tmp, sr)

            with arcpy.da.SearchCursor(tmp, ["SHAPE@"]) as sc:

                for row in sc:
                    geom = row[0]

                    for part in geom:
                        for p in part:
                            if p:
                                x = p.X
                                y = p.Y

                                lat = self.format_coord(y, "LAT")
                                lon = self.format_coord(x, "LON")

                                cursor.insertRow([arcpy.Point(x, y), x, y, lat, lon])

        del cursor

        # Exportar a Excel (compatible 10.x)
        try:
            arcpy.TableToExcel_conversion(out_fc, out_excel)
            messages.addMessage("Excel generado correctamente")
        except:
            messages.addWarning("No se pudo generar Excel")

        arcpy.Delete_management("in_memory")