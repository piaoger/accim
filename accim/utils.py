# accim - Adaptive-Comfort-Control-Implemented Model
# Copyright (C) 2021-2025 Daniel Sánchez-García

# accim is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.

# accim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import os
from tempfile import mkstemp
from shutil import move, copymode
from os import fdopen, remove, rename

import besos.IDF_class
from besos.IDF_class import IDF
import besos
from os import PathLike
from unidecode import unidecode
from typing import List, Literal, Dict, Any, Union

from accim import lists

def modify_timesteps(idf_object: besos.IDF_class.IDF, timesteps: int) -> besos.IDF_class.IDF:
    """
    Modifies the timesteps of the idf object.

    :param idf_object: the IDF class from besos or eppy
    :type idf_object: IDF
    :param timesteps: The number of timesteps.
        Allowable values include 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, and 60
    :type timesteps: int
    """
    if timesteps not in [1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60]:
        raise ValueError(f'{timesteps} not in allowable values: 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, and 60')
    obj_timestep = [i for i in idf_object.idfobjects['Timestep']][0]
    timestep_prev = obj_timestep.Number_of_Timesteps_per_Hour
    obj_timestep.Number_of_Timesteps_per_Hour = timesteps
    print(f'Number of Timesteps per Hour was previously set to '
          f'{timestep_prev} days, and it has been modified to {timesteps} days.')


def modify_timesteps_path(idfpath: str, timesteps: int):
    """
    Modifies the timesteps of the idf.

    :param idfpath: the path to the idf
    :type idfpath: str
    :param timesteps: The number of timesteps.
        Allowable values include 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, and 60
    :type timesteps: int
    """
    from besos.eppy_funcs import get_building
    building = get_building(idfpath)
    modify_timesteps(idf_object=building, timesteps=timesteps)
    building.save()


def set_occupancy_to_always(idf_object: besos.IDF_class.IDF) -> besos.IDF_class.IDF:
    """
    Sets the occupancy to always occupied for all zones with people object.

    :param idf_object: the IDF class from besos or eppy
    :type idf_object: IDF
    """
    if 'On 24/7' in [i.Name for i in idf_object.idfobjects['Schedule:Compact']]:
        print('On 24/7 Schedule:Compact object was already in the model.')
    else:
        idf_object.newidfobject(
            key='Schedule:Compact',
            Schedule_Type_Limits_Name='Any Number',
            Field_1='Through: 12/31',
            Field_2='For: AllDays',
            Field_3='Until: 24:00',
            Field_4='1'
        )

    obj_ppl = [i for i in idf_object.idfobjects['people']]
    for ppl in obj_ppl:
        ppl.Number_of_People_Schedule_Name = 'On 24/7'
        print(f'{ppl.Name} Number of People Schedule Name has been set to always occupied.')


def set_occupancy_to_always_path(idfpath: str):
    """
    Sets the occupancy to always occupied for all zones with people object.

    :param idfpath: the path to the idf
    :type idfpath: str
    """
    from besos.eppy_funcs import get_building
    building = get_building(idfpath)
    set_occupancy_to_always(idf_object=building)
    building.save()


def reduce_runtime(
        idf_object: besos.IDF_class.IDF,
        minimal_shadowing: bool = True,
        shading_calculation_update_frequency: int = 20,
        maximum_figures_in_shadow_overlap_calculations: int = 200,
        timesteps: int = 6,
        runperiod_begin_month: int = 1,
        runperiod_begin_day_of_month: int = 1,
        runperiod_end_month: int = 1,
        runperiod_end_day_of_month: int = 1,
) -> besos.IDF_class.IDF:
    """
    Modifies the idf to reduce the simulation runtime.

    :param idf_object:
    :param minimal_shadowing: True or False. If True, applies minimal shadowing setting.
    :param shading_calculation_update_frequency: An integer. Sets the intervals for the shading calculation update
    :param maximum_figures_in_shadow_overlap_calculations: An integer.
        Applies the number to the maximum figures in shadow overlap calculations.
    :param timesteps: An integer. Sets the number of timesteps.
    :param runperiod_begin_day_of_month: the day of the month to start the simulation
    :param runperiod_begin_month: the month to start the simulation
    :param runperiod_end_day_of_month: the day of the month to end the simulation
    :param runperiod_end_month: the month to end the simulation
    """
    if shading_calculation_update_frequency < 1 or shading_calculation_update_frequency > 365:
        raise ValueError('shading_calculation_update_frequency cannot be smaller than 1 or larger than 365')
    if timesteps < 2 or timesteps > 60:
        raise ValueError('timesteps cannot be smaller than 2 or larger than 60')

    if minimal_shadowing:
        obj_building = [i for i in idf_object.idfobjects['Building']][0]
        if obj_building.Solar_Distribution == 'MinimalShadowing':
            print('Solar distribution is already set to MinimalShadowing, therefore no action has been performed.')
        else:
            obj_building.Solar_Distribution = 'MinimalShadowing'
            print('Solar distribution has been set to MinimalShadowing.')

    runperiod_obj = [i for i in idf_object.idfobjects['Runperiod']][0]
    runperiod_obj.Begin_Month = runperiod_begin_month
    runperiod_obj.Begin_Day_of_Month = runperiod_begin_day_of_month
    runperiod_obj.End_Month = runperiod_end_month
    runperiod_obj.End_Day_of_Month = runperiod_end_day_of_month

    obj_shadowcalc = [i for i in idf_object.idfobjects['ShadowCalculation']][0]
    shadowcalc_freq_prev = obj_shadowcalc.Shading_Calculation_Update_Frequency
    obj_shadowcalc.Shading_Calculation_Update_Frequency = shading_calculation_update_frequency
    print(f'Shading Calculation Update Frequency was previously set to '
          f'{shadowcalc_freq_prev} days, and it has been modified to {shading_calculation_update_frequency} days.')
    shadowcalc_maxfigs_prev = obj_shadowcalc.Maximum_Figures_in_Shadow_Overlap_Calculations
    obj_shadowcalc.Maximum_Figures_in_Shadow_Overlap_Calculations = maximum_figures_in_shadow_overlap_calculations
    print(f'Maximum Figures in Shadow Overlap Calculations was previously set to '
          f'{shadowcalc_maxfigs_prev} days, and it has been modified to {maximum_figures_in_shadow_overlap_calculations} days.')

    obj_timestep = [i for i in idf_object.idfobjects['Timestep']][0]
    timestep_prev = obj_timestep.Number_of_Timesteps_per_Hour
    obj_timestep.Number_of_Timesteps_per_Hour = timesteps
    print(f'Number of Timesteps per Hour was previously set to '
          f'{timestep_prev} days, and it has been modified to {timesteps} days.')


def amend_idf_version_from_dsb(file_path: str):
    """
    Amends the idf version of the Designbuilder-sourced idf file, for Designbuilder v7.X.
    Replaces the string 'Version, 9.4.0.002' with 'Version, 9.4'.

    :param idf_path: the path to the idf
    :type idf_path: str
    """
    pattern = 'Version, 9.4.0.002'
    subst = 'Version, 9.4'

    # Create temp file
    fh, abs_path = mkstemp()
    with fdopen(fh, 'w') as new_file:
        with open(file_path) as old_file:
            for line in old_file:
                new_file.write(line.replace(pattern, subst))
    # Copy the file permissions from the old file to the new file
    copymode(file_path, abs_path)
    # Remove original file
    remove(file_path)
    # Move new file
    move(abs_path, file_path)


import pandas as pd
import warnings
from besos import eppy_funcs as ef
from besos.eplus_funcs import get_idf_version, run_building


class print_available_outputs_mod:
    def __init__(
            self,
            building,
            version=None,
            name=None,
            frequency=None,
    ):
        """
        A modified version of besos' print_available_outputs function.

        :param building: The besos or eppy idf class instance.
        :param version: Deprecated.
        :param name:
        :param frequency:
        """
        # backwards compatibility
        if version:
            warnings.warn(
                "the version argument is deprecated for print_available_outputs,"
                " and will be removed in the future",
                FutureWarning,
            )
            assert version == get_idf_version(building), "Incorrect version"

        if name is not None:
            name = name.lower()
        if frequency is not None:
            frequency = frequency.lower()
        results = run_building(building, stdout_mode="Verbose", out_dir='available_outputs')
        outputlist = []
        for key in results.keys():
            if name is not None:
                if name not in key[0].lower():
                    continue
                if frequency is not None and key[1].lower() != frequency:
                    continue
            elif frequency is not None:
                if key[1].lower() != frequency:
                    continue
            # print(list(key))
            outputlist.append(list(key))

        self.variablereaderlist = []
        self.meterreaderlist = []
        for i in range(len(outputlist)):
            if ',' in outputlist[i][0]:
                outputlist[i] = [
                    outputlist[i][0].split(',')[0],
                    outputlist[i][0].split(',')[1],
                    outputlist[i][1]
                ]
                self.variablereaderlist.append(outputlist[i])
            else:
                self.meterreaderlist.append(outputlist[i])
        # return outputlist, self.meterreaderlist, self.variablereaderlist


# available_outputs = print_available_outputs_mod(building)

# for i in range(len(available_outputs)):
#     if ',' in available_outputs[i][0]:
#         available_outputs[i] = [
#             available_outputs[i][0].split(',')[0],
#             available_outputs[i][0].split(',')[1],
#             available_outputs[i][1]
#         ]

def transform_ddmm_to_int(string_date: str) -> int:
    """
    This function converts a date string in the format "dd/mm" to the day of the year as an integer.

    :param string_date: A string representing the date in format "dd/mm"
    :return: The day of the year as an integer
    :rtype: int
    """
    num_date = list(int(num) for num in string_date.split('/'))
    from datetime import date
    day_of_year = date(2007, num_date[1], num_date[0]).timetuple().tm_yday
    return day_of_year


def remove_accents(input_str: str) -> str:
    return unidecode(input_str)


def remove_accents_in_idf(idf_path: str):
    """
    Replaces all letters with accent with the same letter without accent.

    :type idf_path: str
    """
    with open(idf_path, 'r', encoding='utf-8') as file:
        content = file.read()

    content_without_accents = remove_accents(content)

    with open(idf_path, 'w', encoding='utf-8') as file:
        file.write(content_without_accents)

def get_accim_args(idf_object: besos.IDF_class) -> dict:
    """
    Collects all the EnergyManagementSystem:Program Program lines used to
    set the values for the arguments of ACCIS, and saves them in a dictionary.

    :param idf_object: the besos.IDF_class instance
    :return: a dictionary
    """
    # set_input_data = [i for i in idf_object.idfobjects['EnergyManagementSystem:Program'] if i.Name.lower() == 'setinputdata'][0]
    # set_vof_input_data = [i for i in idf_object.idfobjects['EnergyManagementSystem:Program'] if i.Name.lower() == 'setvofinputdata'][0]
    # applycat = [i for i in idf_object.idfobjects['EnergyManagementSystem:Program'] if i.Name.lower() == 'applycat'][0]
    # setast = [i for i in idf_object.idfobjects['EnergyManagementSystem:Program'] if i.Name.lower() == 'setast'][0]
    # setapplimits = [i for i in idf_object.idfobjects['EnergyManagementSystem:Program'] if i.Name.lower() == 'setapplimits'][0]
    # other_args = {'SetpointAcc': setast.Program_Line_1}
    # cust_ast_args = {
    #     'ACSToffset': applycat.Program_Line_4,
    #     'AHSToffset': applycat.Program_Line_5,
    #     'm': setast.Program_Line_2,
    #     'n': setast.Program_Line_3,
    #     'ACSTaul': setapplimits.Program_Line_2,
    #     'ACSTall': setapplimits.Program_Line_3,
    #     'AHSTaul': setapplimits.Program_Line_4,
    #     'AHSTall': setapplimits.Program_Line_5,
    # }
    # accim_args = {
    #     'SetInputData': set_input_data,
    #     'SetVOFinputData': set_vof_input_data,
    #     'CustAST': cust_ast_args,
    #     'other': other_args
    # }
    # return accim_args

    # Remove the first two lines and the last line with an empty string
    def program_to_dict(program):
        program = program[2:]

        # Initialize an empty dictionary
        parameters = {}

        # Iterate over each line and extract the parameter name and value
        for line in program:
            line = line.strip()
            if line.startswith("set"):
                parts = line.split("=", 1)  # Split only at the first occurrence of "="
                # key = parts[0].replace("set", "").strip()
                key = parts[0][4:].strip()
                value = parts[1].replace(",", "").strip()
                try:
                    # Evaluate the expression to get the actual value
                    value = eval(value)
                except:
                    pass
                parameters[key] = value

        return parameters

    programs = {}
    try:
        for p in ['SetInputData', 'SetVOFinputData']:
            data = [i for i in idf_object.idfobjects['EnergyManagementSystem:Program'] if i.Name.lower() == p.lower()][0].obj
            programs.update({p: program_to_dict(data)})

        setast = [i for i in idf_object.idfobjects['EnergyManagementSystem:Program'] if i.Name.lower() == 'setast'.lower()][0].obj[:3]
        programs.update({'SetAST': program_to_dict(setast)})

        applycat = [i for i in idf_object.idfobjects['EnergyManagementSystem:Program'] if i.Name.lower() == 'applycat'][0]
        setast = [i for i in idf_object.idfobjects['EnergyManagementSystem:Program'] if i.Name.lower() == 'setast'][0]
        setapplimits = [i for i in idf_object.idfobjects['EnergyManagementSystem:Program'] if i.Name.lower() == 'setapplimits'][0]

        cust_ast_args = [
            'x',
            'x',
            applycat.Program_Line_4,
            applycat.Program_Line_5,
            setast.Program_Line_2,
            setast.Program_Line_3,
            setapplimits.Program_Line_2,
            setapplimits.Program_Line_3,
            setapplimits.Program_Line_4,
            setapplimits.Program_Line_5,
        ]
        programs.update({'CustAST': program_to_dict(cust_ast_args)})
    except IndexError:
        ems_programs = [i for i in idf_object.idfobjects['EnergyManagementSystem:Program'] if 'set_zone_input_data' in i.Name.lower()]
        for p in ems_programs:
            programs.update({p.Name: program_to_dict(p.obj)})

    return programs

def get_accim_args_flattened(idf_object):
    from accim.utils import get_accim_args
    accim_args = get_accim_args(idf_object=idf_object)
    def flatten_dict(d):
        flat_dict = {}

        def _flatten(d, parent_key=''):
            for k, v in d.items():
                if isinstance(v, dict):
                    _flatten(v)
                else:
                    flat_dict[k] = v

        _flatten(d)
        return flat_dict

    flattened_dict = flatten_dict(accim_args)
    # print(flattened_dict)
    return flattened_dict


def get_idd_path_from_ep_version(EnergyPlus_version: str):
    if EnergyPlus_version.lower() == '9.1':
        iddfile = 'C:/EnergyPlusV9-1-0/Energy+.idd'
    elif EnergyPlus_version.lower() == '9.2':
        iddfile = 'C:/EnergyPlusV9-2-0/Energy+.idd'
    elif EnergyPlus_version.lower() == '9.3':
        iddfile = 'C:/EnergyPlusV9-3-0/Energy+.idd'
    elif EnergyPlus_version.lower() == '9.4':
        iddfile = 'C:/EnergyPlusV9-4-0/Energy+.idd'
    elif EnergyPlus_version.lower() == '9.5':
        iddfile = 'C:/EnergyPlusV9-5-0/Energy+.idd'
    elif EnergyPlus_version.lower() == '9.6':
        iddfile = 'C:/EnergyPlusV9-6-0/Energy+.idd'
    elif EnergyPlus_version.lower() == '22.1':
        iddfile = 'C:\EnergyPlusV22-1-0\Energy+.idd'
    elif EnergyPlus_version.lower() == '22.2':
        iddfile = 'C:\EnergyPlusV22-2-0\Energy+.idd'
    elif EnergyPlus_version.lower() == '23.1':
        iddfile = 'C:\EnergyPlusV23-1-0\Energy+.idd'
    elif EnergyPlus_version.lower() == '23.2':
        iddfile = 'C:\EnergyPlusV23-2-0\Energy+.idd'
    elif EnergyPlus_version.lower() == '24.1':
        iddfile = 'C:/EnergyPlusV24-1-0/Energy+.idd'
    elif EnergyPlus_version.lower() == '24.2':
        iddfile = 'C:/EnergyPlusV24-2-0/Energy+.idd'
    elif EnergyPlus_version.lower() == '25.1':
        iddfile = 'C:/EnergyPlusV25-1-0/Energy+.idd'
    else:
        iddfile = 'not-supported'

    return iddfile


def get_available_fields(
        idf_instance: besos.IDF_class.IDF,
        object_name: str,
        source: Literal['idd', 'idf'] = 'idd',
        separator: str = '_'
) -> List[str]:
    """
    Retrieves the available fields for an EnergyPlus object using an eppy IDF instance.
    It automatically removes colons (':') from field names.

    Args:
        idf_instance (IDF): The eppy IDF class instance (e.g., from besos.get_building()).
        object_name (str): The type of the object (e.g., 'Zone', 'Material').
        source (str, optional): The source of the field definitions.
            - 'idd': (Default) Extracts the full schema from the EnergyPlus dictionary.
            - 'idf': Extracts fields from the first existing instance in the model.
        separator (str, optional): Character to replace spaces with. Default is '_'.
                                   If " " is passed, the original spaces are kept.

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
            idx = idf_instance.model.dtls.index(obj_upper)
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
            raw_fields = objects[0].fieldnames
        else:
            warnings.warn(f"No instances of '{object_name}' found in the current IDF model.")
            return []

    else:
        raise ValueError("Parameter 'source' must be either 'idd' or 'idf'.")

    # --- FINAL FORMATTING ---
    formatted_fields: List[str] = []

    for field in raw_fields:
        # 1. Remove colons (e.g., 'Output:Variable' -> 'OutputVariable')
        clean_field = field.replace(":", "")

        # 2. Replace spaces with the specified separator
        if separator != " ":
            clean_field = clean_field.replace(" ", separator)

        formatted_fields.append(clean_field)

    return formatted_fields


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


def get_people_names_for_ems(
        idf: besos.IDF_class.IDF,
        output_format: str = 'list'
) -> Union[List[str], Dict[str, List[str]]]:
    """
    Generates unique instance names for People objects applied to spaces.

    Naming Pattern: "{SpaceName} {PeopleName}"
    Example: "Floor_1 Residential Living Occupants"

    Args:
        idf (besos.IDF_class.IDF): The BESOS IDF model object.
        output_format (str): Controls the structure of the return value.
                             - 'list' (Default): Returns a flat list of all generated names.
                             - 'dict': Returns a dictionary {PeopleName: [GeneratedNames]}.

    Returns:
        Union[List[str], Dict[str, List[str]]]: A flat list or a dictionary depending on output_format.
    """

    # 1. Get the raw hierarchy data
    hierarchy_data = get_people_hierarchy(idf)

    # Initialize containers
    expanded_names_dict: Dict[str, List[str]] = {}
    flat_list: List[str] = []

    # 2. Iterate and generate names
    for people_name, data in hierarchy_data.items():
        affected_spaces = data.get("affected_spaces", [])

        # Generate names: Space Name + People Name
        generated_names = [f"{space.strip()} {people_name.strip()}" for space in affected_spaces]

        if output_format == 'dict':
            expanded_names_dict[people_name] = generated_names
        else:
            # If list mode, extend the master list
            flat_list.extend(generated_names)

    # 3. Return based on requested format
    if output_format == 'dict':
        return expanded_names_dict
    else:
        return flat_list

def get_idf_hierarchy(idf: besos.IDF_class) -> Dict[str, Any]:
    """
    Parses an EnergyPlus IDF model object (from eppy or besos) to extract the
    hierarchical relationship between Zones and Spaces, as well as grouping lists.

    This function is designed to be Case-Preserving for output keys (keeping the
    original IDF capitalization) while remaining Case-Insensitive for internal
    logic (robustly linking Spaces to Zones regardless of capitalization).

    Args:
        idf (Union[IDF, IDF_class]): The IDF model object to be parsed.
                                     Accepts both eppy's IDF and besos's IDF_class.

    Returns:
        Dict[str, Any]: A dictionary representing the model structure:
            {
                "zones": {
                    "ZoneName_Original": {
                        "object_type": "Zone",
                        "spaces": ["Space1", "Space2"]
                    },
                    ...
                },
                "groups": {
                    "zone_lists": { "ListName": ["Zone1", "Zone2"] },
                    "space_lists": { "ListName": ["Space1", "Space2"] }
                }
            }
    """

    # Initialize the master dictionary structure to hold the results
    hierarchy: Dict[str, Any] = {
        "zones": {},
        "groups": {
            "zone_lists": {},
            "space_lists": {}
        }
    }

    # Internal lookup map to handle EnergyPlus case-insensitivity.
    # Structure: { "UPPERCASE_NAME": "Original_Name" }
    zone_lookup_map: Dict[str, str] = {}

    # --- 1. Process ZONES (Parent Objects) ---
    # Both eppy and besos allow accessing objects via .idfobjects['TYPE']
    zones = idf.idfobjects['ZONE']

    for zone in zones:
        z_name_original = zone.Name

        # We store the UPPERCASE version to allow robust searching later,
        # ensuring "Zone1" matches "zone1" as EnergyPlus expects.
        z_name_upper = str(z_name_original).upper()
        zone_lookup_map[z_name_upper] = z_name_original

        # Initialize the entry in the result dict using the ORIGINAL name for readability
        hierarchy["zones"][z_name_original] = {
            "object_type": "Zone",
            "spaces": []  # List to hold children (Spaces)
        }

    # --- 2. Process SPACES (Child Objects) ---
    spaces = idf.idfobjects['SPACE']

    # Note: If 'spaces' is empty, it might be a legacy IDF (pre-v9.6) or a simplified model.
    for space in spaces:
        s_name = space.Name

        # Get the reference to the parent Zone.
        # We convert to string and uppercase to query our lookup map safely.
        parent_ref_upper = str(space.Zone_Name).upper()

        # Link Space to Zone using the lookup map
        if parent_ref_upper in zone_lookup_map:
            # Retrieve the correct original casing of the zone name
            real_zone_name = zone_lookup_map[parent_ref_upper]

            # Append the space name to the correct zone entry
            hierarchy["zones"][real_zone_name]["spaces"].append(s_name)
        else:
            # Log warning for orphan spaces (spaces pointing to non-existent zones)
            print(f"WARNING: Space '{s_name}' references an unknown Zone: '{space.Zone_Name}'")

    # --- 3. Process Grouping Lists (ZoneList & SpaceList) ---

    # Process ZoneList
    for z_list in idf.idfobjects['ZONELIST']:
        # In eppy/besos, the .obj property is a list: ['ZoneList', 'Name', 'Member1', 'Member2'...]
        # Slicing from index 2 ([2:]) retrieves all members dynamically, regardless of list length.
        members: List[str] = [m for m in z_list.obj[2:]]
        hierarchy["groups"]["zone_lists"][z_list.Name] = members

    # Process SpaceList
    for s_list in idf.idfobjects['SPACELIST']:
        # Same logic applied to SpaceLists
        members: List[str] = [m for m in s_list.obj[2:]]
        hierarchy["groups"]["space_lists"][s_list.Name] = members

    return hierarchy


def get_spaces_from_spacelist(idf: besos.IDF_class.IDF, spacelist_name: str) -> List[str]:
    """
    Retrieves the list of Space names belonging to a specific SpaceList object.

    Performs a case-insensitive search for the SpaceList name to ensure robustness.

    Args:
        idf (Union[IDF, IDF_class]): The IDF model object.
        spacelist_name (str): The name of the SpaceList to query (e.g. "Residential - Living Space").

    Returns:
        List[str]: A list of space names contained in that SpaceList.
                   Returns an empty list [] if the SpaceList is not found.
    """

    # Normalize the target name to uppercase for case-insensitive comparison
    target_name_upper = spacelist_name.upper()

    # Iterate through all SPACELIST objects in the IDF
    for s_list in idf.idfobjects['SPACELIST']:

        # Check if this is the list we are looking for
        if s_list.Name.upper() == target_name_upper:
            # In eppy/besos, .obj is a list: ['SpaceList', 'Name', 'Space1', 'Space2'...]
            # Slicing from index 2 ([2:]) retrieves only the members (the spaces).
            members = [space_name for space_name in s_list.obj[2:]]

            return members

    # If the loop finishes without finding the list, return an empty list or handle error
    print(f"WARNING: SpaceList '{spacelist_name}' not found in the IDF.")
    return []
