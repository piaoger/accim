import warnings
from typing import List, Literal
from eppy.modeleditor import IDF

def get_available_fields(
    idf_instance: besos.IDF_class,
    object_name: str, 
    source: Literal['idd', 'idf'] = 'idd', 
    separator: str = '_'
) -> List[str]:
    """
    Retrieves the available fields for an EnergyPlus object using an eppy IDF instance.

    Args:
        idf_instance (IDF): The eppy IDF class instance (e.g., from besos.get_building()).
        object_name (str): The type of the object (e.g., 'Zone', 'Material').
        source (str, optional): The source of the field definitions.
            - 'idd': (Default) Extracts the full schema from the EnergyPlus dictionary.
            - 'idf': Extracts fields from the first existing instance in the model.
        separator (str, optional): Character to replace spaces with. Default is '_'.
                                   If " " is passed, the original format is kept.

    Returns:
        List[str]: A list of formatted field names. Returns an empty list if an error occurs.
    
    Raises:
        ValueError: If 'source' is not 'idd' or 'idf'.
    """
    
    # 1. Normalize object name to uppercase (eppy internal format)
    obj_upper = object_name.upper()
    raw_fields: List[str] = []
    
    # --- CASE 1: Extract from IDD (Theoretical Schema) ---
    if source == 'idd':
        # Check if the object TYPE exists in the EnergyPlus dictionary
        if obj_upper in idf_instance.model.dtls:
            # Get the index of the object in the IDD structure
            idx = idf_instance.model.dtls.index(obj_upper)
            
            # idf.idd_info contains the raw metadata
            raw_info = idf_instance.idd_info[idx]
            
            # Extract only the items that are fields
            raw_fields = [item['field'][0] for item in raw_info if 'field' in item]
        else:
            warnings.warn(f"Object type '{object_name}' not found in the loaded IDD.")
            return []

    # --- CASE 2: Extract from IDF (Existing Instance) ---
    elif source == 'idf':
        # Check if there are any created objects of this type
        objects = idf_instance.idfobjects[obj_upper]
        
        if len(objects) > 0:
            # Take the first object to extract its fields
            # (eppy instances have the .fieldnames property)
            raw_fields = objects[0].fieldnames
        else:
            warnings.warn(f"No instances of '{object_name}' found in the current IDF model.")
            return []
            
    else:
        raise ValueError("Parameter 'source' must be either 'idd' or 'idf'.")

    # --- FINAL FORMATTING ---
    # Replace spaces with the specified separator
    if separator != " ":
        formatted_fields = [field.replace(" ", separator) for field in raw_fields]
    else:
        formatted_fields = raw_fields
        
    return formatted_fields

import besos.eppy_funcs as ef
building = ef.get_building("TestModel_TestResidentialUnit_v01_VRF_2.idf")

# Assuming you have your BESOS building instance
# from besos import eppy_funcs as ef
# building = ef.get_building(...)

# 1. Get fields from the IDD (Schema) with default separator ('_')
# Useful for creating new objects
fields = get_available_fields(building, "Zone")
# Output: ['Name', 'Direction_of_Relative_North', 'X_Origin', ...]

# 2. Get fields from an existing object in the IDF
# Useful for inspecting objects that are already there
fields_idf = get_available_fields(building, "FenestrationSurface:Detailed", source='idf')

# 3. Keep original spaces
fields_raw = get_available_fields(building, "Material", separator=" ")
# Output: ['Name', 'Roughness', 'Thickness', ...]

# 4. Warning example (Object not in IDF)
# This will print a UserWarning and return []
fields_missing = get_available_fields(building, "ZoneControl:Thermostat:ThermalComfort", source='idf')
