import sys
import besos.eppy_funcs as ef
building = ef.get_building("TestModel_TestResidentialUnit_v01_VRF_2.idf")

def get_idf_hierarchy(idf):
    """
    Obtiene la jerarquía manteniendo los nombres originales (Case-Preserving),
    pero realiza las búsquedas de forma Case-Insensitive para evitar errores.
    """
    
    hierarchy = {
        "zones": {},
        "groups": {
            "zone_lists": {},
            "space_lists": {}
        }
    }
    
    # DICCIONARIO AUXILIAR DE MAPEO
    # Clave: NOMBRE EN MAYÚSCULAS (para buscar)
    # Valor: Nombre Original (para guardar)
    zone_lookup_map = {}

    # 1. Obtener ZONES
    zones = idf.idfobjects['ZONE']
    for zone in zones:
        z_name_original = zone.Name
        # Normalizamos a mayúsculas solo para el índice de búsqueda
        z_name_upper = str(z_name_original).upper()
        
        # Guardamos en el mapa auxiliar
        zone_lookup_map[z_name_upper] = z_name_original
        
        # Guardamos en la jerarquía final con el NOMBRE ORIGINAL
        hierarchy["zones"][z_name_original] = {
            "object_type": "Zone",
            "spaces": [] 
        }

    # 2. Obtener SPACES
    spaces = idf.idfobjects['SPACE']
    
    if not spaces:
        # Opcional: print("INFO: No spaces found (Legacy mode).")
        pass
    
    for space in spaces:
        s_name = space.Name
        
        # Obtenemos la referencia a la zona
        # Usamos str() por seguridad y upper() para buscar en el mapa
        parent_ref_upper = str(space.Zone_Name).upper()
        
        # Buscamos en el mapa auxiliar
        if parent_ref_upper in zone_lookup_map:
            # Recuperamos el nombre original correcto
            real_zone_name = zone_lookup_map[parent_ref_upper]
            
            # Usamos ese nombre original para insertar el espacio
            hierarchy["zones"][real_zone_name]["spaces"].append(s_name)
        else:
            print(f"ALERTA: El espacio '{s_name}' apunta a una zona desconocida: '{space.Zone_Name}'")

    # 3. Listas de Agrupación (ZoneList y SpaceList)
    
    # Procesar ZoneList
    for z_list in idf.idfobjects['ZONELIST']:
        # Usamos slicing [2:] que es robusto en eppy para listas extensibles
        members = [m for m in z_list.obj[2:]] 
        hierarchy["groups"]["zone_lists"][z_list.Name] = members

    # Procesar SpaceList
    for s_list in idf.idfobjects['SPACELIST']:
        members = [m for m in s_list.obj[2:]]
        hierarchy["groups"]["space_lists"][s_list.Name] = members

    return hierarchy

hierarchy = get_idf_hierarchy(building)