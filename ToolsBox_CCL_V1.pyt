# -*- coding: utf-8 -*-
import arcpy
import os

class Toolbox(object):
    def __init__(self):
        self.label = "Herramientas de Teledetección CLC"
        self.alias = "clc_tools"
        self.tools = [GeneradorCLCPro]

class GeneradorCLCPro(object):
    def __init__(self):
        self.label = "Generador Corine Land Cover (Nivel 4)"
        self.description = "Clasifica imágenes y genera base de datos vectorial jerárquica."
        self.canRunInBackground = False

    def getParameterInfo(self):
        # Parámetros de la herramienta
        p0 = arcpy.Parameter("in_raster", "Imagen de Entrada (Drone/Satélite)", "Input", "GPRasterLayer", "Required")
        p1 = arcpy.Parameter("train_samples", "Polígonos de Entrenamiento", "Input", "GPFeatureLayer", "Required")
        p2 = arcpy.Parameter("class_field", "Campo de Código (ej: 3111)", "Input", "Field", "Required")
        p2.parameterContext = [p1.name]
        p3 = arcpy.Parameter("out_feature_class", "Capa de Coberturas Final (Vector)", "Output", "DEFeatureClass", "Required")
        return [p0, p1, p2, p3]

    def execute(self, params, messages):
        in_raster = params[0].valueAsText
        train_samples = params[1].valueAsText
        class_field = params[2].valueAsText
        out_fc = params[3].valueAsText

        arcpy.env.overwriteOutput = True
        
        # --- DICCIONARIO CORINE LAND COVER NIVEL 4 ---
        # Estructura: Código -> (Nivel 1, Nivel 2, Nivel 3, Nivel 4)
        NOMENCLATURA = {
            # 1. Territorios Artificializados
            111: ("Territorios Artificializados", "Zonas Urbanizadas", "Tejido Urbano Continuo", "Casco Urbano Denso"),
            112: ("Territorios Artificializados", "Zonas Urbanizadas", "Tejido Urbano Discontinuo", "Vivienda Campestre / Dispersa"),
            121: ("Territorios Artificializados", "Zonas Industriales o Comerciales", "Zonas Industriales", "Infraestructura Industrial"),
            122: ("Territorios Artificializados", "Zonas Industriales o Comerciales", "Red Vial y Territorios Asociados", "Vías Principales y Secundarias"),
            131: ("Territorios Artificializados", "Zonas de Extracción Minera", "Extracción de Materiales", "Canteras y Depósitos de Minería"),
            
            # 2. Territorios Agrícolas
            211: ("Territorios Agrícolas", "Cultivos Transitorios", "Otros Cultivos Transitorios", "Hortalizas y Cultivos de Ciclo Corto"),
            231: ("Territorios Agrícolas", "Pastos", "Pastos Limpios", "Potreros Manejados sin Maleza"),
            232: ("Territorios Agrícolas", "Pastos", "Pastos Arbolados", "Potreros con Árboles Dispersos"),
            233: ("Territorios Agrícolas", "Pastos", "Pastos Enmalezados", "Potreros en Abandono / Enmalezados"),
            242: ("Territorios Agrícolas", "Áreas Agrícolas Heterogéneas", "Mosaico de Cultivos", "Mosaico de Cultivos y Pastos"),
            244: ("Territorios Agrícolas", "Áreas Agrícolas Heterogéneas", "Mosaico de Pastos y Espacios Naturales", "Mosaico de Pastos con Vegetación Natural"),

            # 3. Bosques y Áreas Seminaturales
            3111: ("Bosques y Áreas Seminaturales", "Bosques", "Bosque Denso", "Bosque Denso Alto de Tierra Firme"),
            3112: ("Bosques y Áreas Seminaturales", "Bosques", "Bosque Denso", "Bosque Denso Bajo de Inundación"),
            313: ("Bosques y Áreas Seminaturales", "Bosques", "Bosque Fragmentado", "Bosque Fragmentado con Pastos y Cultivos"),
            314: ("Bosques y Áreas Seminaturales", "Bosques", "Bosque de Galería y Ripario", "Vegetación de Ribera / Corredores Biológicos"),
            321: ("Bosques y Áreas Seminaturales", "Áreas con Vegetación Herbácea y Arbustiva", "Arbustal", "Matorrales y Arbustos Densos"),
            323: ("Bosques y Áreas Seminaturales", "Áreas con Vegetación Herbácea y Arbustiva", "Vegetación Secundaria", "Rastrojos en Recuperación"),

            # 5. Superficies de Agua
            511: ("Superficies de Agua", "Aguas Continentales", "Ríos", "Cuerpos de Agua Lóticos / Ríos / Quebradas"),
            512: ("Superficies de Agua", "Aguas Continentales", "Lagunas, Lagos y Ciénagas", "Cuerpos de Agua Lénticos")
        }

        try:
            # Requisito de Licencia
            if arcpy.CheckExtension("Spatial") != "Available":
                raise Exception("Requiere licencia de Spatial Analyst.")
            arcpy.CheckOutExtension("Spatial")

            # 1. PROCESAMIENTO RASTER (MACHINE LEARNING)
            messages.addMessage(">> Segmentando imagen para análisis de objetos...")
            # Parámetros optimizados para Drone (15/15/20)
            seg_raster = arcpy.sa.SegmentMeanShift(in_raster, 15.5, 15, 20)
            
            messages.addMessage(">> Entrenando Clasificador Random Forest...")
            output_ecd = os.path.join(arcpy.env.scratchFolder, "modelo_entrenado.ecd")
            arcpy.ia.TrainRandomForestClassifier(seg_raster, train_samples, output_ecd, None, 100, 30, 1000, class_field)
            
            messages.addMessage(">> Clasificando Imagen...")
            cl_raster = arcpy.ia.ClassifyRaster(in_raster, output_ecd, seg_raster)

            # 2. CONVERSIÓN A VECTOR
            messages.addMessage(">> Convirtiendo a polígonos...")
            temp_fc = "in_memory/clc_raw"
            arcpy.RasterToPolygon_conversion(cl_raster, temp_fc, "SIMPLIFY", "Value")

            # 3. CREACIÓN DE ESTRUCTURA CORINE
            messages.addMessage(">> Construyendo tabla de atributos Nivel 4...")
            campos_nuevos = [
                ("Codigo_CLC", "LONG"),
                ("Nivel_1", "TEXT"),
                ("Nivel_2", "TEXT"),
                ("Nivel_3", "TEXT"),
                ("Nivel_4", "TEXT"),
                ("Area_Ha", "DOUBLE")
            ]
            for c_nom, c_tipo in campos_nuevos:
                arcpy.AddField_management(temp_fc, c_nom, c_tipo, field_length=150 if c_tipo=="TEXT" else None)

            # 4. TRADUCCIÓN Y CÁLCULOS
            with arcpy.da.UpdateCursor(temp_fc, ["gridcode", "Nivel_1", "Nivel_2", "Nivel_3", "Nivel_4", "Area_Ha", "Codigo_CLC", "SHAPE@"]) as cursor:
                for row in cursor:
                    cod = row[0]
                    if cod in NOMENCLATURA:
                        row[1], row[2], row[3], row[4] = NOMENCLATURA[cod]
                    
                    row[6] = cod # Codigo_CLC
                    # Cálculo de área geodésica (preciso incluso en WGS84)
                    row[5] = row[7].getArea("GEODESIC", "HECTARES")
                    cursor.updateRow(row)

            # 5. LIMPIEZA DE "RUIDO" (Opcional: elimina polígonos menores a 10m2)
            arcpy.management.SelectLayerByAttribute(temp_fc, "NEW_SELECTION", "Area_Ha < 0.001")
            if int(arcpy.management.GetCount(temp_fc)[0]) > 0:
                arcpy.management.DeleteFeatures(temp_fc)

            # 6. GUARDAR RESULTADO FINAL
            arcpy.management.CopyFeatures(temp_fc, out_fc)
            messages.addMessage(">> Proceso finalizado exitosamente.")

        except Exception as e:
            messages.addErrorMessage(u"Error: {}".format(str(e)))
        finally:
            arcpy.CheckInExtension("Spatial")
            arcpy.management.Delete("in_memory")