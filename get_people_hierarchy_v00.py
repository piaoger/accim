import sys
from typing import Dict, Any, List, Union

# --- IMPORTS & TYPE HINTING SETUP ---
from eppy.modeleditor import IDF
import besos
import besos.eppy_funcs as ef

# --- MAIN FUNCTION ---

def get_people_hierarchy(idf: besos.IDF_class.IDF) -> Dict[str, Any]:
    """
    Extracts the relationship between People objects and the physical Spaces they occupy.

    Since a 'People' object can reference a Zone, a ZoneList, a Space, or a SpaceList,
    this function resolves all these references down to a list of specific Space names.

    Args:
        idf (Union[IDF, IDF_class]): The IDF model object.

    Returns:
        Dict[str, Any]: A dictionary where keys are People object names and values
                        contain the target reference and the resolved list of spaces.
                        Example:
                        {
                            "Residential Living Occupants": {
                                "target_ref": "Residential - Living Space",
                                "target_type": "SpaceList",  (inferred)
                                "affected_spaces": ["Floor_1", "Floor_2"]
                            }
                        }
    """

    # 1. BUILD A RESOLVER MAP (Key: UpperName -> Value: List of Space Names)
    # We need a unified dictionary to look up any name (Zone, Space, List)
    # and immediately get the list of spaces it represents.
    resolver_map: Dict[str, List[str]] = {}

    # Helper to track what type the name refers to (for info purposes)
    type_map: Dict[str, str] = {}

    # --- A. Index Single SPACES ---
    # A Space references itself.
    spaces = idf.idfobjects['SPACE']
    for s in spaces:
        s_upper = s.Name.upper()
        resolver_map[s_upper] = [s.Name]
        type_map[s_upper] = "Space"

    # --- B. Index ZONES (Zone -> Spaces) ---
    # We map Zones to the Spaces they contain.
    # We iterate through spaces to find their parent Zone.
    zone_to_spaces_temp: Dict[str, List[str]] = {}

    for s in spaces:
        z_ref_upper = str(s.Zone_Name).upper()
        if z_ref_upper not in zone_to_spaces_temp:
            zone_to_spaces_temp[z_ref_upper] = []
        zone_to_spaces_temp[z_ref_upper].append(s.Name)

    # Add to main resolver
    for z_upper, s_list in zone_to_spaces_temp.items():
        resolver_map[z_upper] = s_list
        type_map[z_upper] = "Zone"

    # --- C. Index SPACELISTS ---
    for sl in idf.idfobjects['SPACELIST']:
        sl_upper = sl.Name.upper()
        # Get members (fields starting from index 2)
        members = [m for m in sl.obj[2:]]
        resolver_map[sl_upper] = members
        type_map[sl_upper] = "SpaceList"

    # --- D. Index ZONELISTS ---
    # A ZoneList contains Zones, which contain Spaces. We need to chain this.
    for zl in idf.idfobjects['ZONELIST']:
        zl_upper = zl.Name.upper()
        z_members = [m.upper() for m in zl.obj[2:]]

        # Collect all spaces from all zones in this list
        all_spaces_in_list = []
        for z_name in z_members:
            if z_name in zone_to_spaces_temp:
                all_spaces_in_list.extend(zone_to_spaces_temp[z_name])

        resolver_map[zl_upper] = all_spaces_in_list
        type_map[zl_upper] = "ZoneList"

    # 2. PROCESS PEOPLE OBJECTS
    people_hierarchy = {}

    for person in idf.idfobjects['PEOPLE']:
        p_name = person.Name
        # The critical field that links People to Geometry
        target_name = person.Zone_or_ZoneList_or_Space_or_SpaceList_Name
        target_upper = str(target_name).upper()

        # Resolve the spaces using our map
        # Default to empty list if target is invalid/missing
        affected_spaces = resolver_map.get(target_upper, [])
        inferred_type = type_map.get(target_upper, "Unknown")

        people_hierarchy[p_name] = {
            "target_ref": target_name,
            "inferred_type": inferred_type,
            "affected_spaces": affected_spaces
        }

    return people_hierarchy


def get_people_names_for_ems(idf: besos.IDF_class.IDF) -> Dict[str, List[str]]:
    """
    Generates a list of unique instance names for People objects applied to spaces.

    Naming Pattern: "{SpaceName} {PeopleName}"
    Example: "Floor_1 Residential Living Occupants"

    Args:
        idf (besos.IDF_class.IDF): The BESOS IDF model object.

    Returns:
        Dict[str, List[str]]: Dictionary mapping original People Object Name to
                              the list of generated names per space.
    """

    # Get the raw hierarchy data
    hierarchy_data = get_people_hierarchy(idf)

    expanded_names_dict: Dict[str, List[str]] = {}

    for people_name, data in hierarchy_data.items():
        affected_spaces = data.get("affected_spaces", [])

        # Generate names: Space Name + People Name
        generated_names = [f"{space.strip()} {people_name.strip()}" for space in affected_spaces]

        expanded_names_dict[people_name] = generated_names

    return expanded_names_dict

idfname = 'TestModel_TestResidentialUnit_v01_VRF_2.idf'
epwfile = "Seville.epw"

# print(f"IDF File: {idfname}")
# print(f"EPW File: {epwfile}")

# Load the building model using BESOS
building = ef.get_building(idfname)

people_dict = get_people_hierarchy(idf=building)
people_names_for_ems = get_people_expanded_names(idf=building)