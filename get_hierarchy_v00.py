import sys
from eppy.modeleditor import IDF

# Configuración inicial (ajusta las rutas a tu instalación)
# IDD es necesario para que Eppy entienda la estructura
# iddfile = "/usr/local/EnergyPlus-23-1-0/Energy+.idd" # Ejemplo ruta Mac/Linux
# iddfile = "C:/EnergyPlusV23-1-0/Energy+.idd"       # Ejemplo ruta Windows
# fname = "tu_archivo.idf"                             # Tu archivo IDF

import besos.eppy_funcs as ef
building = ef.get_building("TestModel_TestResidentialUnit_v01_VRF_2.idf")

def get_idf_hierarchy(idf):
    # Cargar IDD e IDF
    # IDF.setiddname(idd_path)
    # try:
    #     idf = IDF(idf_path)
    # except Exception as e:
    #     print(f"Error cargando archivo: {e}")
    #     return {}

    # Diccionario maestro para guardar la jerarquía
    hierarchy = {
        "zones": {},      # Jerarquía física: Zone -> Spaces
        "groups": {       # Agrupaciones lógicas
            "zone_lists": {},
            "space_lists": {}
        }
    }

    # 1. Obtener todas las ZONES (Los padres)
    # Inicializamos el diccionario con cada zona encontrada
    zones = idf.idfobjects['ZONE']
    for zone in zones:
        z_name = zone.Name
        hierarchy["zones"][z_name] = {
            "object_type": "Zone",
            "spaces": [] # Aquí guardaremos los hijos (Spaces)
        }

    # 2. Obtener todos los SPACES (Los hijos)
    # Iteramos los espacios y buscamos a qué zona pertenecen
    spaces = idf.idfobjects['SPACE']
    
    if not spaces:
        print("INFO: No se encontraron objetos 'Space'. Es un IDF estilo 'Legacy' (Zone = Space).")
    
    for space in spaces:
        s_name = space.Name
        # El campo 'Zone_Name' en el objeto Space dice quién es el padre
        parent_zone = space.Zone_Name 
        
        # Verificamos si la zona padre existe en nuestro registro y añadimos el espacio
        if parent_zone in hierarchy["zones"]:
            hierarchy["zones"][parent_zone]["spaces"].append(s_name)
        else:
            print(f"ALERTA: El espacio '{s_name}' referencia una zona no encontrada: '{parent_zone}'")

    # 3. (Opcional) Obtener las Listas de Agrupación (ZoneList y SpaceList)
    # Esto es útil para saber qué zonas/espacios se controlan en conjunto
    
    # Procesar ZoneList
    for z_list in idf.idfobjects['ZONELIST']:
        # Eppy maneja los campos extensibles, iteramos sobre ellos
        # Los nombres de las zonas suelen estar desde el campo 2 en adelante
        members = [field for field in z_list.obj if field and field != z_list.Name and field != "ZoneList"]
        hierarchy["groups"]["zone_lists"][z_list.Name] = members

    # Procesar SpaceList
    for s_list in idf.idfobjects['SPACELIST']:
        members = [field for field in s_list.obj if field and field != s_list.Name and field != "SpaceList"]
        hierarchy["groups"]["space_lists"][s_list.Name] = members

    return hierarchy

hierarchy = get_idf_hierarchy(building)

# # --- EJECUCIÓN ---
# if __name__ == "__main__":
#     # Nota: Asegúrate de configurar la variable iddfile arriba antes de ejecutar
#     # O usa un archivo de ejemplo si tienes eppy instalado correctamente
#     try:
#         # data = get_idf_hierarchy(iddfile, fname)
#         # Para demostración, imprimiré cómo se vería la estructura resultante:
#         print("--- Estructura simulada del resultado ---")
#
#         resultado_ejemplo = {
#             "zones": {
#                 "Planta_1_Zona_Norte": {
#                     "spaces": ["Oficina_101", "Oficina_102", "Baño_Norte"]
#                 },
#                 "Planta_1_Zona_Sur": {
#                     "spaces": ["Open_Office_Sur"]
#                 }
#             },
#             "groups": {
#                 "zone_lists": {
#                     "Todas_Las_Zonas": ["Planta_1_Zona_Norte", "Planta_1_Zona_Sur"]
#                 },
#                 "space_lists": {
#                     "Baños": ["Baño_Norte"]
#                 }
#             }
#         }
#
#         import json
#         print(json.dumps(resultado_ejemplo, indent=4, ensure_ascii=False))
#
#     except Exception as e:
#         print(e)