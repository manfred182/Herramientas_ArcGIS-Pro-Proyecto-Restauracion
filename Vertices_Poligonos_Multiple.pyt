# -*- coding: utf-8 -*-
import arcpy
import math
import os

class Toolbox(object):
    def __init__(self):
        self.label = "Herramientas Geográficas Personalizadas"
        self.alias = "herr_perso"
        self.tools = [VerticesPoligonos_Multiple]

class VerticesPoligonos_Multiple(object):

    def __init__(self):
        self.label = "Extraer vértices múltiples"
        self.description = ("Procesa varios polígonos, copia atributos, ordena vértices, calcula DMS, distancias, azimut y rumbos.")
        self.canRunInBackground = False

    def getParameterInfo(self):
        p1 = arcpy.Parameter(displayName="Capas poligonales (múltiples)", name="in_polygons", datatype="Feature Layer", parameterType="Required", direction="Input", multiValue=True)
        p1.filter.list = ["Polygon"]

        p2 = arcpy.Parameter(displayName="Shapefile de salida", name="out_fc", datatype="Feature Class", parameterType="Required", direction="Output")

        p3 = arcpy.Parameter(displayName="Archivo Excel de salida", name="out_excel", datatype="File", parameterType="Required", direction="Output")
        p3.filter.list = ["xlsx"]

        return [p1, p2, p3]

    def dec_to_dms(self,value):
        d = int(value)
        m = int(abs(value-d)*60)
        s = round((abs(value-d)*60-m)*60,2)
        return d,m,s

    def azimut(self,x1,y1,x2,y2):
        ang = math.degrees(math.atan2((x2-x1),(y2-y1)))
        if ang<0: ang+=360
        return round(ang,2)

    def rumbo(self,az):
        if az==0: return "N 0° E"
        if az==90: return "S 90° E"
        if az==180: return "S 0° W"
        if az==270: return "N 90° W"
        if 0<az<90: return f"N {az}° E"
        if 90<az<180: return f"S {180-az}° E"
        if 180<az<270: return f"S {az-180}° W"
        return f"N {360-az}° W"

    def sentido(self,x,y,cx,cy):
        dx=x-cx; dy=y-cy
        if abs(dx)>abs(dy): return "Este" if dx>0 else "Oeste"
        return "Norte" if dy>0 else "Sur"

    def haversine(self,x1,y1,x2,y2):
        R=6371000
        dx=math.radians(x2-x1)
        dy=math.radians(y2-y1)
        a=math.sin(dy/2)**2 + math.cos(math.radians(y1))*math.cos(math.radians(y2))*math.sin(dx/2)**2
        return 2*R*math.asin(math.sqrt(a))

    def execute(self, params, messages):

        layers = params[0].values
        output_fc = params[1].valueAsText
        excel_path = params[2].valueAsText

        arcpy.env.overwriteOutput = True

        # inicializar salida
        wgs84 = arcpy.SpatialReference(4326)
        out_folder = os.path.dirname(output_fc)
        out_name = os.path.basename(output_fc)

        arcpy.management.CreateFeatureclass(out_folder,out_name,"POINT",spatial_reference=wgs84)

        # campos comunes
        base_fields = ["SourceID","Lat_DMS","Lon_DMS","Sentido","Azimut","Rumbo","Dist_m"]
        for f in base_fields:
            arcpy.AddField_management(output_fc,f,"TEXT" if f not in ("Azimut","Dist_m") else "DOUBLE")

        datos_excel=[]

        insert_fields=["SHAPE@","SourceID","Lat_DMS","Lon_DMS","Sentido","Azimut","Rumbo","Dist_m"]

        with arcpy.da.InsertCursor(output_fc, insert_fields) as icur:
            feat_id=1

            for layer in layers:
                temp_poly="in_memory/temp_poly"
                arcpy.management.Project(layer,temp_poly,wgs84)

                with arcpy.da.SearchCursor(temp_poly,["SHAPE@"]) as cur:
                    for row in cur:
                        poly=row[0]
                        centroid=poly.centroid
                        vertices=[]

                        for part in poly:
                            for p in part:
                                if p:
                                    vertices.append((p.X,p.Y))

                        # ordenar horario
                        vertices.sort(key=lambda p: math.atan2(p[1]-centroid.Y,p[0]-centroid.X), reverse=True)

                        for i,(x1,y1) in enumerate(vertices):
                            x2,y2=vertices[(i+1)%len(vertices)]

                            lat_d,lat_m,lat_s=self.dec_to_dms(y1)
                            lon_d,lon_m,lon_s=self.dec_to_dms(x1)
                            lat=f"{lat_d}° {lat_m}' {lat_s}\""
                            lon=f"{lon_d}° {lon_m}' {lon_s}\""

                            snt=self.sentido(x1,y1,centroid.X,centroid.Y)
                            az=self.azimut(x1,y1,x2,y2)
                            rbo=self.rumbo(az)
                            dist=self.haversine(x1,y1,x2,y2)

                            icur.insertRow([arcpy.Point(x1,y1),feat_id,lat,lon,snt,az,rbo,dist])
                            datos_excel.append([x1,y1,feat_id,lat,lon,snt,az,rbo,dist])

                        feat_id+=1

        # exportar excel
        temp_table="in_memory/temp_table"
        arcpy.management.CreateTable("in_memory","temp_table")

        excel_fields=["X","Y","SourceID","Lat_DMS","Lon_DMS","Sentido","Azimut","Rumbo","Dist_m"]
        for f in excel_fields:
            t="DOUBLE" if f in ("X","Y","Azimut","Dist_m","SourceID") else "TEXT"
            arcpy.AddField_management(temp_table,f,t)

        with arcpy.da.InsertCursor(temp_table,excel_fields) as tcur:
            for r in datos_excel:
                tcur.insertRow(r)

        arcpy.conversion.TableToExcel(temp_table,excel_path)
        messages.addMessage("✔ Procesamiento múltiple completado correctamente.")
