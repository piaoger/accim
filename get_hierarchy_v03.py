import sys
from typing import Dict, Any, List
from eppy.modeleditor import IDF
from besos import IDF_class


# import besos.eppy_funcs as ef
# building = ef.get_building("TestModel.idf")

def get_idf_hierarchy(idf: IDF) -> Dict[str, Any]:
    """
    Parses an EnergyPlus IDF object (via eppy or besos) to extract the 
    hierarchical relationship between Zones and Spaces, as well as grouping lists.

    This function preserves the original casing of names in the output dictionary
    (e.g., "Floor_1_Zone") but performs case-insensitive matching internally 
    to link Spaces to Zones robustly (handling EnergyPlus case-insensitivity).

    Args:
        idf (IDF): An eppy.modeleditor.IDF object instance.

    Returns:
        Dict[str, Any]: A dictionary containing the hierarchy structure:
            {
                "zones": { ... },
                "groups": { "zone_lists": {...}, "space_lists": {...} }
            }
    """
    
    # Initialize the master dictionary structure
    hierarchy: Dict[str, Any] = {
        "zones": {},
        "groups": {
            "zone_lists": {},
            "space_lists": {}
        }
    }
    
    # Lookup map to handle EnergyPlus case-insensitivity.
    # Key: Uppercase Name (used for matching) -> Value: Original Name (used for output)
    zone_lookup_map: Dict[str, str] = {}

    # --- 1. Process ZONES (Parent Objects) ---
    zones = idf.idfobjects['ZONE']
    for zone in zones:
        z_name_original = zone.Name
        
        # Store the uppercase version to allow robust searching later
        # (EnergyPlus sees "Zone1" and "zone1" as the same object)
        z_name_upper = str(z_name_original).upper()
        zone_lookup_map[z_name_upper] = z_name_original
        
        # Initialize the entry in the result dict using the ORIGINAL name
        hierarchy["zones"][z_name_original] = {
            "object_type": "Zone",
            "spaces": []  # List to hold child spaces
        }

    # --- 2. Process SPACES (Child Objects) ---
    spaces = idf.idfobjects['SPACE']
    
    # Optional: Check if spaces exist (handling legacy files where Zone implies Space)
    if not spaces:
        # You could print a log here: "INFO: No Spaces found (Legacy Mode)"
        pass
    
    for space in spaces:
        s_name = space.Name
        
        # Get the reference to the parent Zone.
        # Convert to string and uppercase to ensure matching against the lookup map.
        parent_ref_upper = str(space.Zone_Name).upper()
        
        # Link Space to Zone using the lookup map
        if parent_ref_upper in zone_lookup_map:
            # Retrieve the original casing of the zone name from our map
            real_zone_name = zone_lookup_map[parent_ref_upper]
            
            # Append the space name to the correct zone entry
            hierarchy["zones"][real_zone_name]["spaces"].append(s_name)
        else:
            # Handle orphan spaces or bad references
            print(f"WARNING: Space '{s_name}' references an unknown Zone: '{space.Zone_Name}'")

    # --- 3. Process Grouping Lists (ZoneList & SpaceList) ---
    
    # Process ZoneList
    for z_list in idf.idfobjects['ZONELIST']:
        # In eppy, .obj is a list like ['ZoneList', 'ListName', 'Member1', 'Member2'...]
        # Slicing [2:] retrieves all members robustly regardless of list length.
        members: List[str] = [m for m in z_list.obj[2:]] 
        hierarchy["groups"]["zone_lists"][z_list.Name] = members

    # Process SpaceList
    for s_list in idf.idfobjects['SPACELIST']:
        # Slicing [2:] skips the Object Type and Object Name fields
        members: List[str] = [m for m in s_list.obj[2:]]
        hierarchy["groups"]["space_lists"][s_list.Name] = members

    return hierarchy