# -*- coding: utf-8 -*-
import arcpy
import math
import os

class Toolbox(object):
    def __init__(self):
        self.label = "Herramientas Geográficas Personalizadas"
        self.alias = "herr_perso"
        self.tools = [VerticesPoligonoAvanzado]

class VerticesPoligonoAvanzado(object):

    def __init__(self):
        self.label = "Extraer vértices (avanzado)"
        self.description = ("Extrae los vértices de un polígono, los ordena "
                            "en sentido horario, calcula Lat/Long en DMS, "
                            "el sentido cardinal, el azimut y exporta Excel.")
        self.canRunInBackground = False

    def getParameterInfo(self):
        params = []

        p1 = arcpy.Parameter(
            displayName="Polígono de entrada",
            name="in_polygon",
            datatype="Feature Class",
            parameterType="Required",
            direction="Input")
        p1.filter.list = ["Polygon"]

        p2 = arcpy.Parameter(
            displayName="Shapefile de salida",
            name="out_fc",
            datatype="Feature Class",
            parameterType="Required",
            direction="Output")

        p3 = arcpy.Parameter(
            displayName="Archivo Excel de salida",
            name="out_excel",
            datatype="File",
            parameterType="Required",
            direction="Output")
        p3.filter.list = ["xlsx"]

        params.append(p1)
        params.append(p2)
        params.append(p3)

        return params

    def dec_to_dms(self, value):
        degrees = int(value)
        minutes = int(abs(value - degrees) * 60)
        seconds = round((abs(value - degrees) * 60 - minutes) * 60, 2)
        return degrees, minutes, seconds

    def calcular_azimut(self, x1, y1, x2, y2):
        ang = math.degrees(math.atan2((x2 - x1), (y2 - y1)))
        if ang < 0:
            ang += 360
        return round(ang, 2)

    def execute(self, params, messages):

        polygon_fc = params[0].valueAsText
        output_fc = params[1].valueAsText
        excel_path = params[2].valueAsText

        arcpy.env.overwriteOutput = True

        vertices = []
        centroid = None

        with arcpy.da.SearchCursor(polygon_fc, ["SHAPE@"]) as sCur:
            for row in sCur:
                polygon = row[0]
                centroid = polygon.centroid

                for part in polygon:
                    for point in part:
                        if point:
                            vertices.append((point.X, point.Y))

        vertices.sort(key=lambda p: math.atan2(p[1] - centroid.Y,
                                               p[0] - centroid.X),
                      reverse=True)

        out_path = os.path.dirname(output_fc)
        out_name = os.path.basename(output_fc)

        arcpy.management.CreateFeatureclass(
            out_path=out_path,
            out_name=out_name,
            geometry_type="POINT",
            spatial_reference=polygon_fc
        )

        arcpy.management.AddField(output_fc, "Lat_DMS", "TEXT", 255)
        arcpy.management.AddField(output_fc, "Lon_DMS", "TEXT", 255)
        arcpy.management.AddField(output_fc, "Sentido", "TEXT", 1)
        arcpy.management.AddField(output_fc, "Azimut", "DOUBLE")

        datos_excel = []

        with arcpy.da.InsertCursor(output_fc,
            ["SHAPE@", "Lat_DMS", "Lon_DMS", "Sentido", "Azimut"]) as iCur:

            for i in range(len(vertices)):
                x, y = vertices[i]
                x2, y2 = vertices[(i + 1) % len(vertices)]

                lat_d, lat_m, lat_s = self.dec_to_dms(y)
                lon_d, lon_m, lon_s = self.dec_to_dms(x)

                lat_dms = f"{lat_d}° {lat_m}' {lat_s}\""
                lon_dms = f"{lon_d}° {lon_m}' {lon_s}\""

                if y > centroid.Y:
                    sentido = "N"
                elif y < centroid.Y:
                    sentido = "S"
                elif x > centroid.X:
                    sentido = "E"
                else:
                    sentido = "W"

                az = self.calcular_azimut(x, y, x2, y2)

                iCur.insertRow([arcpy.Point(x, y), lat_dms, lon_dms, sentido, az])

                datos_excel.append([x, y, lat_dms, lon_dms, sentido, az])

        temp_table = os.path.join("in_memory", "temp_vertices")

        arcpy.management.CreateTable("in_memory", "temp_vertices")

        arcpy.management.AddField(temp_table, "X", "DOUBLE")
        arcpy.management.AddField(temp_table, "Y", "DOUBLE")
        arcpy.management.AddField(temp_table, "Lat_DMS", "TEXT", 255)
        arcpy.management.AddField(temp_table, "Lon_DMS", "TEXT", 255)
        arcpy.management.AddField(temp_table, "Sentido", "TEXT", 1)
        arcpy.management.AddField(temp_table, "Azimut", "DOUBLE")

        with arcpy.da.InsertCursor(temp_table,
            ["X", "Y", "Lat_DMS", "Lon_DMS", "Sentido", "Azimut"]) as tCur:
            for row in datos_excel:
                tCur.insertRow(row)

        arcpy.conversion.TableToExcel(temp_table, excel_path)

        messages.addMessage("✔ Proceso completado con éxito.")
        messages.addMessage(f"✔ Shapefile creado: {output_fc}")
        messages.addMessage(f"✔ Excel generado: {excel_path}")
