# -*- coding: utf-8 -*-

import arcpy
import os
import pandas as pd


class Toolbox(object):
    def __init__(self):
        self.label = "Exportar múltiples tablas a Excel"
        self.alias = "ExportMultipleExcel"
        self.tools = [ExportMultipleTablesToExcel]


class ExportMultipleTablesToExcel(object):
    def __init__(self):
        self.label = "Exportar tablas a Excel"
        self.description = (
            "Exporta varias tablas o capas de ArcGIS "
            "a un solo archivo Excel, cada una en una hoja separada."
        )

    def getParameterInfo(self):
        params = []

        input_tables = arcpy.Parameter(
            displayName="Tablas o capas de entrada",
            name="input_tables",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
            multiValue=True
        )

        output_excel = arcpy.Parameter(
            displayName="Archivo Excel de salida",
            name="output_excel",
            datatype="DEFile",
            parameterType="Required",
            direction="Output"
        )
        output_excel.filter.list = ["xlsx"]

        params.append(input_tables)
        params.append(output_excel)

        return params

    def execute(self, parameters, messages):
        tablas = parameters[0].valueAsText.split(";")
        excel_path = parameters[1].valueAsText

        arcpy.AddMessage("Iniciando exportación a Excel...")

        # USAR openpyxl (incluido en ArcGIS Pro)
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            for tabla in tablas:
                nombre_hoja = os.path.basename(tabla)[:31]

                arcpy.AddMessage(f"Exportando: {nombre_hoja}")

                campos = [f.name for f in arcpy.ListFields(tabla)]

                datos = []
                with arcpy.da.SearchCursor(tabla, campos) as cursor:
                    for row in cursor:
                        datos.append(row)

                df = pd.DataFrame(datos, columns=campos)
                df.to_excel(writer, sheet_name=nombre_hoja, index=False)

        arcpy.AddMessage("✅ Exportación finalizada correctamente.")