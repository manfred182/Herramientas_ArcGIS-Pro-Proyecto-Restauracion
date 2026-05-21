import arcpy

class Toolbox(object):
    def __init__(self):
        """Define la toolbox (el nombre que aparece en el panel)."""
        self.label = "Herramientas de Vértices"
        self.alias = "VérticesCardinales"
        self.tools = [SeleccionarDiezPuntos]

class SeleccionarDiezPuntos(object):
    def __init__(self):
        """Define la herramienta."""
        self.label = "Seleccionar 10 Puntos Cardinales"
        self.description = "Extrae los 10 puntos más importantes basados en el sentido cardinal y la distancia."
        self.can_run_background = False

    def getParameterInfo(self):
        """Define los parámetros de la interfaz de usuario."""
        # Parámetro 1: Capa de entrada
        param_in = arcpy.Parameter(
            displayName="Capa de Puntos de Entrada",
            name="in_features",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param_in.filter.list = ["Point"]

        # Parámetro 2: Capa de salida
        param_out = arcpy.Parameter(
            displayName="Capa de Salida (Puntos Principales)",
            name="out_features",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        return [param_in, param_out]

    def execute(self, parameters, messages):
        """Aquí se ejecuta la lógica principal."""
        input_fc = parameters[0].valueAsText
        output_fc = parameters[1].valueAsText

        # 1. Definimos los sentidos cardinales a buscar
        # Nota: Asegúrate que coincidan con los nombres exactos en tu tabla
        sentidos = ['Norte', 'Sur', 'Este', 'Oeste', 'Noreste', 'Noroeste', 'Sureste', 'Suroeste']
        
        oid_list = []
        desc = arcpy.Describe(input_fc)
        oid_field = desc.OIDFieldName

        messages.addMessage("Analizando rumbos y distancias...")

        # 2. Primero intentamos obtener el punto con mayor distancia de cada sentido principal
        for rumbo in sentidos:
            # Consulta SQL dinámica según el campo 'Sentido'
            where = f"Sentido = '{rumbo}'"
            
            # Usamos un SearchCursor ordenando por Dist_m de mayor a menor
            # El campo Dist_m debe existir en tu tabla como mencionaste
            try:
                with arcpy.da.SearchCursor(input_fc, [oid_field, "Dist_m"], 
                                           where_clause=where, 
                                           sql_clause=(None, "ORDER BY Dist_m DESC")) as cursor:
                    for row in cursor:
                        if row[0] not in oid_list:
                            oid_list.append(row[0])
                            break # Solo tomamos el mejor de este rumbo
            except Exception:
                # Si un rumbo no existe en la tabla, pasamos al siguiente
                continue
            
            if len(oid_list) >= 10:
                break

        # 3. Si aún no tenemos 10 puntos, rellenamos con los de mayor distancia general
        if len(oid_list) < 10:
            faltantes = 10 - len(oid_list)
            messages.addMessage(f"Rellenando con {faltantes} puntos adicionales de mayor longitud...")
            with arcpy.da.SearchCursor(input_fc, [oid_field], 
                                       sql_clause=(None, "ORDER BY Dist_m DESC")) as cursor:
                for row in cursor:
                    if row[0] not in oid_list:
                        oid_list.append(row[0])
                    if len(oid_list) == 10:
                        break

        # 4. Crear la selección y exportar
        if oid_list:
            where_final = f"{oid_field} IN ({','.join(map(str, oid_list))})"
            arcpy.management.SelectLayerByAttribute(input_fc, "NEW_SELECTION", where_final)
            arcpy.management.CopyFeatures(input_fc, output_fc)
            arcpy.management.SelectLayerByAttribute(input_fc, "CLEAR_SELECTION")
            messages.addMessage(f"¡Listo! Se han guardado 10 puntos en: {output_fc}")
        else:
            messages.addErrorMessage("No se encontraron puntos que coincidan con los criterios.")

        return