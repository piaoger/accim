from eppy.modeleditor import IDF

def obtener_campos_idd(idf_instance, nombre_objeto):
    """
    Obtiene la lista de campos disponibles (esquema) para un tipo de objeto 
    según el IDD cargado en la instancia IDF.
    
    Args:
        idf_instance (IDF): La instancia de eppy.modeleditor.IDF cargada.
        nombre_objeto (str): El nombre del objeto (ej. 'Zone', 'Material').
        
    Returns:
        list: Lista con los nombres de los campos o None si el objeto no existe.
    """
    # 1. Normalizar el nombre a mayúsculas (eppy almacena las claves en mayúsculas)
    obj_upper = nombre_objeto.upper()
    
    # 2. Verificar si el objeto existe en el diccionario (dtls)
    if obj_upper in idf_instance.model.dtls:
        # Obtener el índice numérico del objeto en la estructura IDD
        idx = idf_instance.model.dtls.index(obj_upper)
        
        # 3. Acceder a la información cruda del IDD
        # idf.idd_info es una lista de listas con metadatos
        raw_info = idf_instance.idd_info[idx]
        
        campos = []
        
        # 4. Iterar sobre los metadatos para extraer los nombres de los campos
        # Nota: El primer elemento suele ser metadatos del objeto, los siguientes son campos.
        for item in raw_info:
            if 'field' in item:
                # 'field' es una lista, tomamos el primer elemento (el nombre)
                campos.append(item['field'][0])
                
        return campos
    else:
        print(f"Error: El objeto '{nombre_objeto}' no existe en el IDD actual.")
        return None

import besos.eppy_funcs as ef

idfname = 'TestModel_TestResidentialUnit_v01_VRF_2.idf'
epwfile = "Seville.epw"

# print(f"IDF File: {idfname}")
# print(f"EPW File: {epwfile}")

# Load the building model using BESOS
building = ef.get_building(idfname)

fields = obtener_campos_idd(
    idf_instance=building,
    nombre_objeto='People',
)

##
import os

def obtener_esquema_desde_idd(ruta_idd, nombre_objeto):
    """
    Carga un archivo IDD y extrae los campos disponibles para un objeto específico.
    Sustituye espacios por guiones bajos.

    Args:
        ruta_idd (str): Ruta completa al archivo Energy+.idd.
        nombre_objeto (str): Nombre del objeto (ej. 'Zone', 'Lights').

    Returns:
        list: Lista de campos en formato snake_case.
    """

    # 1. Verificar que el archivo IDD existe
    if not os.path.exists(ruta_idd):
        raise FileNotFoundError(f"No se encontró el archivo IDD en: {ruta_idd}")

    # 2. Cargar el IDD en la clase IDF de eppy
    # Nota: Esto configura el IDD globalmente para la sesión de eppy.
    try:
        IDF.setiddname(ruta_idd)
    except Exception as e:
        # Si el IDD ya estaba cargado, eppy a veces lanza advertencias o errores,
        # pero generalmente podemos continuar si es el mismo archivo.
        pass

    # 3. Normalizar nombre del objeto a mayúsculas (formato interno de eppy)
    obj_upper = nombre_objeto.upper()

    # 4. Acceder a las estructuras internas de la CLASE IDF (no de una instancia)
    # IDF.model.dtls contiene la lista de todos los nombres de objetos válidos
    if obj_upper in IDF.model.dtls:
        # Obtener el índice del objeto
        idx = IDF.model.dtls.index(obj_upper)

        # IDF.idd_info contiene la definición detallada (metadatos)
        raw_info = IDF.idd_info[idx]

        campos_formateados = []

        # 5. Extraer los campos
        for item in raw_info:
            if 'field' in item:
                nombre_original = item['field'][0]
                # Reemplazar espacios por guiones bajos
                nombre_limpio = nombre_original.replace(" ", "_")
                campos_formateados.append(nombre_limpio)

        return campos_formateados
    else:
        print(f"El objeto '{nombre_objeto}' no existe en el IDD proporcionado.")
        return []

idd_dict = obtener_esquema_desde_idd(ruta_idd="C:\EnergyPlusV25-1-0\Energy+.idd", nombre_objeto="Zone")