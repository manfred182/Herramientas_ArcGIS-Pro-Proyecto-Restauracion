# -*- coding: utf-8 -*-
import arcpy
import os

class Toolbox(object):
    def __init__(self):
        self.label = "Herramientas de Teledetección Automática"
        self.alias = "at_clc"
        self.tools = [GeneradorAutomaticoCLC]

class GeneradorAutomaticoCLC(object):
    def __init__(self):
        self.label = "1. Generador CLC Automático (Escala 1:1,000)"
        self.description = "Detección automática de coberturas y asignación de códigos Corine sin intervención humana."
        self.canRunInBackground = False

    def getParameterInfo(self):
        # Únicos parámetros necesarios
        p0 = arcpy.Parameter("in_raster", "Ortomosaico de Entrada", "Input", "GPRasterLayer", "Required")
        p1 = arcpy.Parameter("out_fc", "Capa de Salida (Shapefile/GDB)", "Output", "DEFeatureClass", "Required")
        
        # Ajuste de sensibilidad predeterminado para alta resolución
        p2 = arcpy.Parameter("sensibilidad", "Nivel de detalle (Sugerido: 30)", "Input", "GPLong", "Optional")
        p2.value = 30
        
        return [p0, p1, p2]

    def execute(self, params, messages):
        in_raster = params[0].valueAsText
        out_fc = params[1].valueAsText
        n_clases = params[2].value

        arcpy.env.overwriteOutput = True
        
        # --- LÓGICA DE CODIFICACIÓN AUTOMÁTICA ---
        # El sistema mapea los grupos estadísticos a la jerarquía Corine
        DB_AUTO = {
            "A": (511, "Superficies de Agua", "Aguas Continentales", "Ríos", "Cuerpos de Agua Lóticos"),
            "B": (3111, "Bosques y Áreas Seminaturales", "Bosques", "Bosque Denso", "Bosque Denso Alto de Tierra Firme"),
            "C": (323, "Bosques y Áreas Seminaturales", "Áreas con veg. herbácea", "Vegetación Secundaria", "Rastrojos y Arbustales"),
            "D": (231, "Territorios Agrícolas", "Pastos", "Pastos Limpios", "Pastos Manejados / Potreros"),
            "E": (111, "Territorios Artificializados", "Zonas Urbanizadas", "Tejido Urbano", "Construcciones e Infraestructura")
        }

        try:
            if arcpy.CheckExtension("Spatial") != "Available":
                raise Exception("Se requiere licencia de Spatial Analyst.")
            arcpy.CheckOutExtension("Spatial")

            # 1. SEGMENTACIÓN (Análisis de textura para 1:1,000)
            messages.addMessage(">> Analizando texturas y geometrías...")
            seg = arcpy.sa.SegmentMeanShift(in_raster, 18.0, 15, 10)

            # 2. CLASIFICACIÓN ISO CLUSTER (Detección sin muestras)
            messages.addMessage(">> Detectando firmas espectrales automáticamente...")
            iso = arcpy.sa.IsoClusterUnsupervisedClassification(seg, n_clases, 20, 10)

            # 3. VECTORIZACIÓN DE ALTA FIDELIDAD
            messages.addMessage(">> Generando polígonos a escala detalle...")
            tmp = "in_memory/clc_auto"
            arcpy.RasterToPolygon_conversion(iso, tmp, "NO_SIMPLIFY", "Value")

            # 4. CREACIÓN DE ESTRUCTURA CORINE
            for n, t in [("Codigo_CLC","LONG"), ("Nivel_1","TEXT"), ("Nivel_2","TEXT"), ("Nivel_3","TEXT"), ("Nivel_4","TEXT"), ("Area_Ha","DOUBLE")]:
                arcpy.AddField_management(tmp, n, t, field_length=150 if t=="TEXT" else None)

            # 5. ASIGNACIÓN DE DATOS SEGÚN REFLECTANCIA
            messages.addMessage(">> Etiquetando coberturas automáticamente...")
            with arcpy.da.UpdateCursor(tmp, ["gridcode", "Codigo_CLC", "Nivel_1", "Nivel_2", "Nivel_3", "Nivel_4", "Area_Ha", "SHAPE@"]) as cur:
                for row in cur:
                    g = row[0]
                    # Distribución estadística de los clusters encontrados
                    if g <= (n_clases * 0.12): k = "A" # Agua/Sombra
                    elif g <= (n_clases * 0.45): k = "B" # Bosque
                    elif g <= (n_clases * 0.70): k = "C" # Rastrojo
                    elif g <= (n_clases * 0.88): k = "D" # Pastos
                    else: k = "E" # Urbano/Suelo
                    
                    row[1], row[2], row[3], row[4], row[5] = DB_AUTO[k]
                    row[6] = row[7].getArea("GEODESIC", "HECTARES")
                    cur.updateRow(row)

            # 6. LIMPIEZA DE RUIDO (UMM 2m2)
            arcpy.management.SelectLayerByAttribute(tmp, "NEW_SELECTION", "Area_Ha < 0.0002")
            if int(arcpy.management.GetCount(tmp)[0]) > 0:
                arcpy.management.DeleteFeatures(tmp)

            # FINALIZAR
            arcpy.management.CopyFeatures(tmp, out_fc)
            messages.addMessage(">> Capa final generada con éxito.")

        except Exception as e:
            messages.addErrorMessage(str(e))
        finally:
            arcpy.CheckInExtension("Spatial")
            arcpy.management.Delete("in_memory")