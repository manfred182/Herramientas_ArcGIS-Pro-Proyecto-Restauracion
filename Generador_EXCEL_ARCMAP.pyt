# -*- coding: utf-8 -*-
import arcpy
import os

class Toolbox(object):
    def __init__(self):
        self.label = "Exportar Tablas Excel"
        self.alias = "ExportarExcel"
        self.tools = [ExportarTablas]

class ExportarTablas(object):
    def __init__(self):
        self.label = "Exportar múltiples tablas"
        self.description = "Exporta varias tablas a archivos Excel individuales"

    def getParameterInfo(self):

        entrada = arcpy.Parameter(
            displayName="Tablas de entrada",
            name="entrada",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
            multiValue=True)

        salida = arcpy.Parameter(
            displayName="Carpeta salida",
            name="salida",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input")

        return [entrada, salida]

    def execute(self, parameters, messages):

        tablas = parameters[0].valueAsText.split(";")
        carpeta = parameters[1].valueAsText

        for tabla in tablas:

            nombre = os.path.basename(tabla)
            archivo = os.path.join(carpeta, nombre + ".xls")

            arcpy.AddMessage("Exportando " + nombre)

            arcpy.TableToExcel_conversion(tabla, archivo)

        arcpy.AddMessage("Proceso terminado")