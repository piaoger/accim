def obtener_campos_desde_besos(idf_besos, nombre_objeto):
    """
    Obtiene el esquema (campos disponibles) para un tipo de objeto
    usando una instancia IDF generada por BESOS.
    
    Args:
        idf_besos: La instancia devuelta por besos.eppy_funcs.get_building()
        nombre_objeto (str): El tipo de objeto (ej. 'Zone', 'Lights').
        
    Returns:
        list: Nombres de los campos con espacios sustituidos por guiones bajos.
    """
    # 1. Normalizar a mayúsculas (formato interno de eppy)
    obj_upper = nombre_objeto.upper()
    
    # 2. Verificar si el tipo de objeto existe en el diccionario cargado por BESOS
    # idf_besos.model.dtls contiene la lista de TODOS los objetos posibles del IDD
    if obj_upper in idf_besos.model.dtls:
        
        # Obtener el índice numérico del objeto en la estructura del IDD
        idx = idf_besos.model.dtls.index(obj_upper)
        
        # 3. Extraer la metadata cruda del IDD desde la instancia
        # idf_besos.idd_info contiene la definición de campos para cada objeto
        raw_info = idf_besos.idd_info[idx]
        
        campos_formateados = []
        
        # 4. Iterar y limpiar nombres
        for item in raw_info:
            if 'field' in item:
                nombre_original = item['field'][0]
                nombre_limpio = nombre_original.replace(" ", "_")
                campos_formateados.append(nombre_limpio)
                
        return campos_formateados
    else:
        print(f"Error: El objeto '{nombre_objeto}' no existe en la versión de EnergyPlus cargada por BESOS.")
        return []


import besos.eppy_funcs as ef
building = ef.get_building("TestModel_TestResidentialUnit_v01_VRF_2.idf")

fields = obtener_campos_desde_besos(idf_besos=building, nombre_objeto="ZoneControl:Thermostat:ThermalComfort")