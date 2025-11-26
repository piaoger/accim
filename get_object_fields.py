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
