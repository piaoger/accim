import sys
import besos.eppy_funcs as ef # Descomentar si usas BESOS
building = ef.get_building("TestModel_TestResidentialUnit_v01_VRF_2.idf")

def get_idf_hierarchy(idf):
    """
    Extrae la jerarquía de un objeto IDF de eppy/besos.
    Normaliza todos los nombres a MAYÚSCULAS para evitar errores de case-sensitivity.
    """
    
    # Diccionario maestro
    hierarchy = {
        "zones": {},
        "groups": {
            "zone_lists": {},
            "space_lists": {}
        }
    }

    # 1. Obtener ZONES (Normalizamos nombres a .upper())
    zones = idf.idfobjects['ZONE']
    for zone in zones:
        # Usamos upper() para que sea seguro buscar después
        z_name = zone.Name.upper() 
        hierarchy["zones"][z_name] = {
            "original_name": zone.Name, # Guardamos el nombre real por si acaso
            "object_type": "Zone",
            "spaces": [] 
        }

    # 2. Obtener SPACES
    spaces = idf.idfobjects['SPACE']
    
    if not spaces:
        print("INFO: No se encontraron objetos 'Space'. Es un IDF estilo 'Legacy'.")
    
    for space in spaces:
        s_name = space.Name # El nombre del espacio lo dejamos tal cual o upper según prefieras
        
        # Obtenemos la referencia a la zona y la convertimos a mayúsculas
        parent_zone_ref = str(space.Zone_Name).upper()
        
        if parent_zone_ref in hierarchy["zones"]:
            hierarchy["zones"][parent_zone_ref]["spaces"].append(s_name)
        else:
            print(f"ALERTA: El espacio '{s_name}' apunta a una zona desconocida: '{space.Zone_Name}'")

    # 3. Listas de Agrupación (ZoneList y SpaceList)
    
    # Procesar ZoneList
    for z_list in idf.idfobjects['ZONELIST']:
        # Método robusto: En eppy, obj es una lista ['ZoneList', 'NombreLista', 'Zona1', 'Zona2'...]
        # Saltamos los 2 primeros elementos para coger solo los miembros
        members = [m for m in z_list.obj[2:]] 
        hierarchy["groups"]["zone_lists"][z_list.Name] = members

    # Procesar SpaceList
    for s_list in idf.idfobjects['SPACELIST']:
        # Saltamos los 2 primeros elementos (Type, Name)
        members = [m for m in s_list.obj[2:]]
        hierarchy["groups"]["space_lists"][s_list.Name] = members

    return hierarchy

# --- EJEMPLO DE USO ---
hierarchy = get_idf_hierarchy(building)
print(hierarchy["zones"].keys())