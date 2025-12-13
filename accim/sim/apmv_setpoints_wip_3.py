# accim - Adaptive-Comfort-Control-Implemented Model
# Copyright (C) 2021-2025 Daniel Sánchez-García
# Distributed under the GNU General Public License v3 or later.

"""
Contains the functions to apply setpoints based on the Adaptive Predicted Mean Vote (aPMV) index.
Unified version supporting EnergyPlus versions pre and post 23.1.
"""
import os
import warnings
from typing import Dict, Any, List, Union, Optional
import pandas as pd
import besos.IDF_class
import eppy
from accim.utils import transform_ddmm_to_int
import accim.sim.accim_Main_single_idf as accim_Main
import besos.objectives

import besos.objectives
import warnings

try:
    _original_read_eso = besos.objectives.read_eso

    def _silent_read_eso(out_dir, file_name='eplusout.eso'):
        try:
            # Intentamos ejecutar la función original
            return _original_read_eso(out_dir, file_name)
        except Exception as e:
            # Si falla por CUALQUIER razón (unidades vacías, duplicados, etc.),
            # lanzamos un warning y devolvemos None para que el script no se rompa.
            warnings.warn(f"BESOS no pudo leer los resultados ({e}). Se continúa la ejecución sin datos de salida.")
            return None

    # Aplicar el parche
    besos.objectives.read_eso = _silent_read_eso

except ImportError:
    pass


# ==============================================================================
# MAIN FUNCTION
# ==============================================================================

def apply_apmv_setpoints(
        building: besos.IDF_class,
        outputs_freq: List[str] = ['hourly'],
        other_PMV_related_outputs: bool = True,
        adap_coeff_cooling: Union[float, dict] = 0.293,
        adap_coeff_heating: Union[float, dict] = -0.293,
        pmv_cooling_sp: Union[float, dict] = -0.5,
        pmv_heating_sp: Union[float, dict] = 0.5,
        tolerance_cooling_sp_cooling_season: Union[float, dict] = -0.1,
        tolerance_cooling_sp_heating_season: Union[float, dict] = -0.1,
        tolerance_heating_sp_cooling_season: Union[float, dict] = 0.1,
        tolerance_heating_sp_heating_season: Union[float, dict] = 0.1,
        cooling_season_start: Union[float, str] = 120,
        cooling_season_end: Union[float, str] = 210,
        dflt_for_adap_coeff_cooling: float = 0.4,
        dflt_for_adap_coeff_heating: float = -0.4,
        dflt_for_pmv_cooling_sp: float = 0.5,
        dflt_for_pmv_heating_sp: float = -0.5,
        dflt_for_tolerance_cooling_sp_cooling_season: float = -0.1,
        dflt_for_tolerance_cooling_sp_heating_season: float = -0.1,
        dflt_for_tolerance_heating_sp_cooling_season: float = 0.1,
        dflt_for_tolerance_heating_sp_heating_season: float = 0.1,
        verboseMode: bool = True,
) -> besos.IDF_class:
    """
    Applies setpoints based on the Adaptive Predicted Mean Vote (aPMV) index.
    Compatible with EnergyPlus versions < 23.1 and >= 23.1.
    """
    
    # 1. DETECT VERSION
    # --------------------------------------------------------------------------
    version_tuple = building.idd_version
    # EnergyPlus introduced Spaces in 23.1.0 (officially prominent then)
    is_legacy = (version_tuple[0] < 23) or (version_tuple[0] == 23 and version_tuple[1] < 1)
    
    # 2. PREPARE DATA BASED ON VERSION
    # --------------------------------------------------------------------------
    
    # Standardize dates
    if isinstance(cooling_season_start, str):
        cooling_season_start = transform_ddmm_to_int(cooling_season_start)
    if isinstance(cooling_season_end, str):
        cooling_season_end = transform_ddmm_to_int(cooling_season_end)

    # These variables will be filled differently depending on version
    ems_target_names = []      # The identifier used in EMS variables (e.g. ZoneName OR Space_People)
    ems_sensor_keys = []       # The key used for sensors (e.g. PeopleName)
    hierarchy_dict = None      # Only used in >= 23.1
    
    if is_legacy:
        if verboseMode: print(f"--- Detected Legacy EnergyPlus Version: {version_tuple} ---")
        
        # --- LEGACY LOGIC (Direct Zone/People scraping) ---
        try:
            ppl_temp = [[people.Zone_or_ZoneList_Name, people.Name] for people in building.idfobjects['People']]
        except AttributeError:
            try:
                ppl_temp = [[people.Zone_or_ZoneList_or_Space_or_SpaceList_Name, people.Name] for people in building.idfobjects['People']]
            except AttributeError:
                ppl_temp = [[people.Zone_Name, people.Name] for people in building.idfobjects['People']]

        zones_with_ppl_colon = [ppl[0] for ppl in ppl_temp] # Used for dataframe lookup and schedule naming
        ppl_names = [ppl[1] for ppl in ppl_temp]            # Used for Sensor Key
        
        # In legacy code, EMS variables were suffixed with the Zone Name (sanitized)
        ems_target_names = [z.replace(':', '_').replace(' ', '_') for z in zones_with_ppl_colon]
        ems_sensor_keys = ppl_names
        
        # Ensure Schedules exist (Legacy Style)
        _ensure_schedules_legacy(building, ems_target_names, verboseMode)
        _ensure_thermostat_legacy(building, zones_with_ppl_colon, ems_target_names)
        
        # Actuators (Legacy Style)
        _add_actuators_legacy(building, ems_target_names, verboseMode)

    else:
        if verboseMode: print(f"--- Detected Modern EnergyPlus Version: {version_tuple} ---")
        
        # --- MODERN LOGIC (Using accim.utils for Spaces) ---
        from accim.utils import get_idf_hierarchy_with_people, get_people_names_for_ems, inspect_thermostat_objects
        
        hierarchy_dict = get_idf_hierarchy_with_people(idf=building)
        ems_sensor_keys = get_people_names_for_ems(idf=building)
        
        # In modern code, EMS variables are suffixed with Space_People (sanitized)
        ems_target_names = [i.replace(' ', '_') for i in ems_sensor_keys]
        
        # Ensure Thermostats (Modern Style)
        instance = inspect_thermostat_objects(idf=building)
        _ensure_thermostat_modern(building, instance)
        
        # Actuators (Modern Style - iterates hierarchy)
        _add_actuators_modern(building, hierarchy_dict, verboseMode)

    # 3. COMMON LOGIC (DataFrame & EMS Generation)
    # --------------------------------------------------------------------------
    
    # Generate DataFrame (Now accepts explicit list of keys to avoid version conflicts)
    # For legacy: keys are Zone Names. For Modern: keys are Space/People unique names.
    keys_for_df = ems_sensor_keys if not is_legacy else zones_with_ppl_colon
    
    df_arguments = generate_df_from_args(
        building=building,
        target_keys_input=keys_for_df,
        is_legacy_mode=is_legacy,
        adap_coeff_heating=adap_coeff_heating,
        adap_coeff_cooling=adap_coeff_cooling,
        pmv_heating_sp=pmv_heating_sp,
        pmv_cooling_sp=pmv_cooling_sp,
        tolerance_cooling_sp_cooling_season=tolerance_cooling_sp_cooling_season,
        tolerance_cooling_sp_heating_season=tolerance_cooling_sp_heating_season,
        tolerance_heating_sp_cooling_season=tolerance_heating_sp_cooling_season,
        tolerance_heating_sp_heating_season=tolerance_heating_sp_heating_season,
        dflt_for_adap_coeff_cooling=dflt_for_adap_coeff_cooling,
        dflt_for_adap_coeff_heating=dflt_for_adap_coeff_heating,
        dflt_for_pmv_cooling_sp=dflt_for_pmv_cooling_sp,
        dflt_for_pmv_heating_sp=dflt_for_pmv_heating_sp,
        dflt_for_tolerance_cooling_sp_cooling_season=dflt_for_tolerance_cooling_sp_cooling_season,
        dflt_for_tolerance_cooling_sp_heating_season=dflt_for_tolerance_cooling_sp_heating_season,
        dflt_for_tolerance_heating_sp_cooling_season=dflt_for_tolerance_heating_sp_cooling_season,
        dflt_for_tolerance_heating_sp_heating_season=dflt_for_tolerance_heating_sp_heating_season,
    )

    # Add Sensors
    _add_apmv_sensors(building, ems_sensor_keys, ems_target_names, verboseMode)
    
    # Add Global Variables
    _add_apmv_global_variables(building, ems_target_names, verboseMode)
    
    # Add EMS Programs
    # Actuator naming convention differs: 
    # Legacy: PMV_H_SP_act_{Zone}
    # Modern: PMV_H_SP_act_{Space_People}
    _add_apmv_programs(
        building, 
        ems_target_names, 
        df_arguments, 
        cooling_season_start, 
        cooling_season_end, 
        verboseMode,
        is_legacy=is_legacy
    )
    
    # Add Calling Managers
    _add_apmv_program_calling_managers(building, verboseMode)
    
    # Add Outputs
    _add_apmv_outputs(
        building, 
        outputs_freq, 
        other_PMV_related_outputs, 
        ems_target_names, 
        hierarchy_dict=hierarchy_dict, 
        is_legacy=is_legacy,
        verboseMode=verboseMode
    )

    return building


# ==============================================================================
# LEGACY SPECIFIC FUNCTIONS (< 23.1)
# ==============================================================================

def _ensure_schedules_legacy(building, zone_names_underscore, verboseMode):
    sch_comp_objs = [i.Name for i in building.idfobjects['Schedule:Compact']]
    for i in ['PMV_H_SP', 'PMV_C_SP']:
        for zone in zone_names_underscore:
            if f'{i}_{zone}' not in sch_comp_objs:
                building.newidfobject(
                    'Schedule:Compact',
                    Name=f'{i}_{zone}',
                    Schedule_Type_Limits_Name="Any Number",
                    Field_1='Through: 12/31',
                    Field_2='For: AllDays',
                    Field_3='Until: 24:00,1'
                )
                if verboseMode: print(f"{i}_{zone} Schedule has been added")

def _ensure_thermostat_legacy(building, zones_colon, zones_underscore):
    comf_fanger_dualsps = [i for i in building.idfobjects['ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint']]
    for i in comf_fanger_dualsps:
        for j in range(len(zones_colon)):
            if zones_colon[j] in i.Name:
                i.Fanger_Thermal_Comfort_Heating_Schedule_Name = f'PMV_H_SP_{zones_underscore[j]}'
                i.Fanger_Thermal_Comfort_Cooling_Schedule_Name = f'PMV_C_SP_{zones_underscore[j]}'

def _add_actuators_legacy(building, zones_underscore, verboseMode):
    actuatornamelist = [actuator.Name for actuator in building.idfobjects['EnergyManagementSystem:Actuator']]
    for i in ['PMV_H_SP', 'PMV_C_SP']:
        for zone in zones_underscore:
            if f'{i}_act_{zone}' not in actuatornamelist:
                building.newidfobject(
                    'EnergyManagementSystem:Actuator',
                    Name=f'{i}_act_{zone}',
                    Actuated_Component_Unique_Name=f'{i}_{zone}',
                    Actuated_Component_Type='Schedule:Compact',
                    Actuated_Component_Control_Type='Schedule Value',
                )
                if verboseMode: print(f'Added - {i}_act_{zone} Actuator')


# ==============================================================================
# MODERN SPECIFIC FUNCTIONS (>= 23.1)
# ==============================================================================

def _ensure_thermostat_modern(building: besos.IDF_class, instance: Dict[str, Any]):
    # Create Schedule:Compact for PMV setpoints if missing
    for i in range(len(instance['ZoneControl:Thermostat'])):
        zone_name = instance['ZoneControl:Thermostat'][i]['Zone_or_ZoneList_Name']
        for mode, value in (['H', -0.5], ['C', 0.5]):
            if len([s for s in building.idfobjects['Schedule:Compact'] if s.Name == f'PMV_{mode}_SP_{zone_name}']) == 0:
                building.newidfobject(
                    key='Schedule:Compact',
                    Name=f'PMV_{mode}_SP_{zone_name}',
                    Schedule_Type_Limits_Name="Any Number",
                    Field_1='Through: 12/31',
                    Field_2='For: AllDays',
                    Field_3=f'Until: 24:00, {value}'
                )

    # Handle Thermostat Conversion
    if len(instance['ZoneControl:Thermostat']) > 0 and len(instance['ZoneControl:Thermostat:ThermalComfort']) == 0:
        for i in range(len(instance['ZoneControl:Thermostat'])):
            zone_name = instance['ZoneControl:Thermostat'][i]['Zone_or_ZoneList_Name']

            building.newidfobject(
                key='Schedule:Compact',
                Name=f'Thermal Comfort Control Type Schedule Name {zone_name}',
                Schedule_Type_Limits_Name="Any Number",
                Field_1='Through: 12/31',
                Field_2='For: AllDays',
                Field_3='Until: 24:00,4'
            )

            building.newidfobject(
                key='ZoneControl:Thermostat:ThermalComfort',
                Name=f'Thermostat Setpoint Dual Setpoint {zone_name}',
                Zone_or_ZoneList_Name=zone_name,
                Thermal_Comfort_Control_Type_Schedule_Name=f'Thermal Comfort Control Type Schedule Name {zone_name}',
                Thermal_Comfort_Control_1_Object_Type='ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint',
                Thermal_Comfort_Control_1_Name=f'Fanger Setpoint {zone_name}'
            )

            building.newidfobject(
                key='ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint',
                Name=f'Fanger Setpoint {zone_name}',
                Fanger_Thermal_Comfort_Heating_Schedule_Name=f'PMV_H_SP_{zone_name}',
                Fanger_Thermal_Comfort_Cooling_Schedule_Name=f'PMV_C_SP_{zone_name}',
            )
            # Cleanup old objects
            for obj_type in ['ZoneControl:Thermostat', 'ThermostatSetpoint:DualSetpoint']:
                to_remove = [obj for obj in building.idfobjects[obj_type] if obj.Name in [instance['ZoneControl:Thermostat'][i]['Name']]]
                for obj in to_remove:
                    building.removeidfobject(obj)

    elif len(instance['ZoneControl:Thermostat:ThermalComfort']) > 0:
        zc_ts_tc_objs = [i for i in building.idfobjects['ZoneControl:Thermostat:ThermalComfort']]
        zc_ts_tc_objs_dict_names = {}
        for ob in zc_ts_tc_objs:
            temp_dict = {'old_name': ob.Name}
            zone_name = ob.Zone_or_ZoneList_Name
            ob.Name = f'Thermostat Setpoint Dual Setpoint {zone_name}'
            ob.Thermal_Comfort_Control_1_Object_Type = 'ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint'
            ob.Thermal_Comfort_Control_1_Name = f'Fanger Setpoint {zone_name}'
            temp_dict.update({'new_name': ob.Name})
            zc_ts_tc_objs_dict_names.update({zone_name: temp_dict})

        thsp_tc_objs = [i for i in building.idfobjects['ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint']]
        for ob in thsp_tc_objs:
            for zone_name, temp_dict in zc_ts_tc_objs_dict_names.items():
                if temp_dict['old_name'] == ob.Name:
                    ob.Name = temp_dict['new_name']
                    ob.Fanger_Thermal_Comfort_Heating_Schedule_Name = f'Fanger Heating Setpoint {zone_name}'
                    ob.Fanger_Thermal_Comfort_Cooling_Schedule_Name = f'Fanger Cooling Setpoint {zone_name}'

def _add_actuators_modern(building, hierarchy_dict, verboseMode):
    actuatornamelist = [actuator.Name for actuator in building.idfobjects['EnergyManagementSystem:Actuator']]
    
    # Iterate through hierarchy to link Space/People specific actuator names to Zone Schedules
    for zone in hierarchy_dict['zones'].keys():
        for space in hierarchy_dict['zones'][zone]['spaces']:
            for i in ['H', 'C']:
                # The actuator Name is specific to the Space/People combination
                temp_name = f'PMV_{i}_SP_act_{space["name"]}_{space["people"].replace(" ", "_")}'
                
                if temp_name not in actuatornamelist:
                    building.newidfobject(
                        'EnergyManagementSystem:Actuator',
                        Name=temp_name,
                        Actuated_Component_Unique_Name=f'PMV_{i}_SP_{zone}', # Acts on the ZONE Schedule
                        Actuated_Component_Type='Schedule:Compact',
                        Actuated_Component_Control_Type='Schedule Value',
                    )
                    if verboseMode: print(f'Added - {temp_name} Actuator')


# ==============================================================================
# SHARED EMS GENERATORS
# ==============================================================================

def _add_apmv_sensors(building, sensor_keys, target_names, verboseMode):
    """
    Adds sensors. 
    sensor_keys: List of keys for the sensor (e.g., People Name).
    target_names: List of suffixes for the EMS Variable Name.
    """
    sensornamelist = [s.Name for s in building.idfobjects['EnergyManagementSystem:Sensor']]

    for i in range(len(target_names)):
        # PMV
        if f'PMV_{target_names[i]}' not in sensornamelist:
            building.newidfobject(
                'EnergyManagementSystem:Sensor',
                Name=f'PMV_{target_names[i]}',
                OutputVariable_or_OutputMeter_Index_Key_Name=sensor_keys[i],
                OutputVariable_or_OutputMeter_Name='Zone Thermal Comfort Fanger Model PMV'
            )
            if verboseMode: print(f'Added - PMV_{target_names[i]} Sensor')

        # Occupant Count
        if f'People_Occupant_Count_{target_names[i]}' not in sensornamelist:
            building.newidfobject(
                'EnergyManagementSystem:Sensor',
                Name=f'People_Occupant_Count_{target_names[i]}',
                OutputVariable_or_OutputMeter_Index_Key_Name=sensor_keys[i],
                OutputVariable_or_OutputMeter_Name='People Occupant Count'
            )
            if verboseMode: print(f'Added - People_Occupant_Count_{target_names[i]} Sensor')

def _add_apmv_global_variables(building, target_names, verboseMode):
    globalvariablenames = ['CoolingSeason', 'CoolSeasonEnd', 'CoolSeasonStart']
    globalvariablezonenames = []
    
    prefixes = [
        'tolerance_cooling_sp', 'tolerance_cooling_sp_cooling_season', 'tolerance_cooling_sp_heating_season',
        'tolerance_heating_sp', 'tolerance_heating_sp_cooling_season', 'tolerance_heating_sp_heating_season',
        'adap_coeff', 'adap_coeff_heating', 'adap_coeff_cooling',
        'pmv_heating_sp', 'pmv_cooling_sp', 'aPMV',
        'comfhour', 'discomfhour', 'discomfhour_heat', 'discomfhour_cold', 'occupied_hour',
        'aPMV_H_SP', 'aPMV_C_SP', 'aPMV_H_SP_noTol', 'aPMV_C_SP_noTol'
    ]

    for prefix in prefixes:
        for name in target_names:
            globalvariablezonenames.append(f'{prefix}_{name}')

    allgvs = globalvariablenames + globalvariablezonenames
    existing_gvs = {gv.Erl_Variable_1_Name for gv in building.idfobjects['EnergyManagementSystem:GlobalVariable']}

    for gv in allgvs:
        if gv not in existing_gvs:
            building.newidfobject('EnergyManagementSystem:GlobalVariable', Erl_Variable_1_Name=gv)
            if verboseMode: print(f'Added - {gv} GlobalVariable object')

def _add_apmv_programs(building, target_names, df_arguments, cool_start, cool_end, verboseMode, is_legacy):
    programlist = [p.Name for p in building.idfobjects['EnergyManagementSystem:Program']]

    # Season Programs
    if 'set_cooling_season_input_data' not in programlist:
        building.newidfobject(
            'EnergyManagementSystem:Program',
            Name='set_cooling_season_input_data',
            Program_Line_1=f'set CoolSeasonStart = {cool_start}',
            Program_Line_2=f'set CoolSeasonEnd = {cool_end}'
        )
        if verboseMode: print('Added - set_cooling_season_input_data Program')

    if 'set_cooling_season' not in programlist:
        building.newidfobject(
            'EnergyManagementSystem:Program',
            Name='set_cooling_season',
            Program_Line_1='if CoolSeasonEnd > CoolSeasonStart',
            Program_Line_2='if (DayOfYear >= CoolSeasonStart) && (DayOfYear < CoolSeasonEnd)',
            Program_Line_3='set CoolingSeason = 1',
            Program_Line_4='else',
            Program_Line_5='set CoolingSeason = 0',
            Program_Line_6='endif',
            Program_Line_7='elseif CoolSeasonStart > CoolSeasonEnd',
            Program_Line_8='if (DayOfYear >= CoolSeasonStart) || (DayOfYear < CoolSeasonEnd)',
            Program_Line_9='set CoolingSeason = 1',
            Program_Line_10='else',
            Program_Line_11='set CoolingSeason = 0',
            Program_Line_12='endif',
            Program_Line_13='endif',
        )
        if verboseMode: print('Added - set_cooling_season Program')

    # Per-Target Programs
    for name in target_names:
        # Find corresponding row in dataframe
        try:
            row_idx = df_arguments[df_arguments['underscore_zonename'] == name].index[0]
        except IndexError:
            if verboseMode: print(f"Warning: Could not match {name} in arguments DataFrame.")
            continue

        # Input Data Program
        if f'set_zone_input_data_{name}' not in programlist:
            building.newidfobject(
                'EnergyManagementSystem:Program',
                Name=f'set_zone_input_data_{name}',
                Program_Line_1=f'set adap_coeff_cooling_{name} = {df_arguments.loc[row_idx, "adap_coeff_cooling"]}',
                Program_Line_2=f'set adap_coeff_heating_{name} = {df_arguments.loc[row_idx, "adap_coeff_heating"]}',
                Program_Line_3=f'set pmv_cooling_sp_{name} = {df_arguments.loc[row_idx, "pmv_cooling_sp"]}',
                Program_Line_4=f'set pmv_heating_sp_{name} = {df_arguments.loc[row_idx, "pmv_heating_sp"]}',
                Program_Line_5=f'set tolerance_cooling_sp_cooling_season_{name} = {df_arguments.loc[row_idx, "tolerance_cooling_sp_cooling_season"]}',
                Program_Line_6=f'set tolerance_cooling_sp_heating_season_{name} = {df_arguments.loc[row_idx, "tolerance_cooling_sp_heating_season"]}',
                Program_Line_7=f'set tolerance_heating_sp_cooling_season_{name} = {df_arguments.loc[row_idx, "tolerance_heating_sp_cooling_season"]}',
                Program_Line_8=f'set tolerance_heating_sp_heating_season_{name} = {df_arguments.loc[row_idx, "tolerance_heating_sp_heating_season"]}',
            )
            if verboseMode: print(f'Added - set_zone_input_data_{name} Program')

        # Main Logic Program
        if f'apply_aPMV_{name}' not in programlist:
            # ACTUATOR NAMING:
            # Legacy: PMV_H_SP_act_{ZoneName}
            # Modern: PMV_H_SP_act_{SpaceName}_{PeopleName} (which is 'name' here)
            if is_legacy:
                act_h = f'PMV_H_SP_act_{name}'
                act_c = f'PMV_C_SP_act_{name}'
            else:
                act_h = f'PMV_H_SP_act_{name}'
                act_c = f'PMV_C_SP_act_{name}'

            building.newidfobject(
                'EnergyManagementSystem:Program',
                Name=f'apply_aPMV_{name}',
                Program_Line_1='if CoolingSeason == 1',
                Program_Line_2=f'set adap_coeff_{name} = adap_coeff_cooling_{name}',
                Program_Line_3=f'set tolerance_cooling_sp_{name} = tolerance_cooling_sp_cooling_season_{name}',
                Program_Line_4=f'set tolerance_heating_sp_{name} = tolerance_heating_sp_cooling_season_{name}',
                Program_Line_5='elseif CoolingSeason == 0',
                Program_Line_6=f'set adap_coeff_{name} = adap_coeff_heating_{name}',
                Program_Line_7=f'set tolerance_cooling_sp_{name} = tolerance_cooling_sp_heating_season_{name}',
                Program_Line_8=f'set tolerance_heating_sp_{name} = tolerance_heating_sp_heating_season_{name}',
                Program_Line_9='endif',
                Program_Line_10=f'set aPMV_H_SP_noTol_{name} = pmv_heating_sp_{name}/(1+adap_coeff_{name}*pmv_heating_sp_{name})',
                Program_Line_11=f'set aPMV_C_SP_noTol_{name} = pmv_cooling_sp_{name}/(1+adap_coeff_{name}*pmv_cooling_sp_{name})',
                Program_Line_12=f'set aPMV_H_SP_{name} = aPMV_H_SP_noTol_{name}+tolerance_heating_sp_{name}',
                Program_Line_13=f'set aPMV_C_SP_{name} = aPMV_C_SP_noTol_{name}+tolerance_cooling_sp_{name}',
                Program_Line_14=f'if People_Occupant_Count_{name} > 0',
                Program_Line_15=f'if aPMV_H_SP_{name} < 0',
                Program_Line_16=f'set {act_h} = aPMV_H_SP_{name}',
                Program_Line_17='else',
                Program_Line_18=f'set {act_h} = 0',
                Program_Line_19='endif',
                Program_Line_20=f'if aPMV_C_SP_{name} > 0',
                Program_Line_21=f'set {act_c} = aPMV_C_SP_{name}',
                Program_Line_22='else',
                Program_Line_23=f'set {act_c} = 0',
                Program_Line_24='endif',
                Program_Line_25='else',
                Program_Line_26=f'set {act_h} = -100',
                Program_Line_27=f'set {act_c} = 100',
                Program_Line_28='endif',
            )
            if verboseMode: print(f'Added - apply_aPMV_{name} Program')

        # Monitor Program
        if f'monitor_aPMV_{name}' not in programlist:
            building.newidfobject(
                'EnergyManagementSystem:Program',
                Name=f'monitor_aPMV_{name}',
                Program_Line_1=f'set aPMV_{name} = PMV_{name}/(1+adap_coeff_{name}*PMV_{name})',
            )
            if verboseMode: print(f'Added - monitor_aPMV_{name} Program')

        # Count Program
        if f'count_aPMV_comfort_hours_{name}' not in programlist:
            building.newidfobject(
                'EnergyManagementSystem:Program',
                Name=f'count_aPMV_comfort_hours_{name}',
                Program_Line_1=f'if aPMV_{name} < aPMV_H_SP_noTol_{name}',
                Program_Line_2=f'set comfhour_{name} = 0',
                Program_Line_3=f'set discomfhour_cold_{name} = 1*ZoneTimeStep',
                Program_Line_4=f'set discomfhour_heat_{name} = 0',
                Program_Line_5=f'elseif aPMV_{name} > aPMV_C_SP_noTol_{name}',
                Program_Line_6=f'set comfhour_{name} = 0',
                Program_Line_7=f'set discomfhour_cold_{name} = 0',
                Program_Line_8=f'set discomfhour_heat_{name} = 1*ZoneTimeStep',
                Program_Line_9='else',
                Program_Line_10=f'set comfhour_{name} = 1*ZoneTimeStep',
                Program_Line_11=f'set discomfhour_cold_{name} = 0',
                Program_Line_12=f'set discomfhour_heat_{name} = 0',
                Program_Line_13='endif',
                Program_Line_14=f'if People_Occupant_Count_{name} > 0',
                Program_Line_15=f'set occupied_hour_{name} = 1*ZoneTimeStep',
                Program_Line_16='else',
                Program_Line_17=f'set occupied_hour_{name} = 0',
                Program_Line_18='endif',
                Program_Line_19=f'set discomfhour_{name} = discomfhour_cold_{name} + discomfhour_heat_{name}',
            )
            if verboseMode: print(f'Added - count_aPMV_comfort_hours_{name} Program')

def _add_apmv_program_calling_managers(building, verboseMode):
    programlist = [p.Name for p in building.idfobjects['EnergyManagementSystem:Program']]
    pcmlist = [pcm.Name for pcm in building.idfobjects['EnergyManagementSystem:ProgramCallingManager']]

    for prog in programlist:
        if prog not in pcmlist:
            building.newidfobject(
                'EnergyManagementSystem:ProgramCallingManager',
                Name=prog,
                EnergyPlus_Model_Calling_Point="BeginTimestepBeforePredictor",
                Program_Name_1=prog
            )
            if verboseMode: print(f'Added - {prog} Program Calling Manager')

def _add_apmv_outputs(building, outputs_freq, other_PMV_related_outputs, target_names, hierarchy_dict, is_legacy, verboseMode):
    # EMS Output Variables
    outputvariablelist = [v.Name for v in building.idfobjects['EnergyManagementSystem:OutputVariable']]
    
    EMSOutputVariableZone_dict = {
        'Adaptive Coefficient': ['adap_coeff', '', 'Averaged'],
        'aPMV': ['aPMV', '', 'Averaged'],
        'aPMV Heating Setpoint': ['aPMV_H_SP', '', 'Averaged'],
        'aPMV Cooling Setpoint': ['aPMV_C_SP', '', 'Averaged'],
        'aPMV Heating Setpoint No Tolerance': ['aPMV_H_SP_noTol', '', 'Averaged'],
        'aPMV Cooling Setpoint No Tolerance': ['aPMV_C_SP_noTol', '', 'Averaged'],
        'Comfortable Hours': ['comfhour', 'H', 'Summed'],
        'Discomfortable Hot Hours': ['discomfhour_heat', 'H', 'Summed'],
        'Discomfortable Cold Hours': ['discomfhour_cold', 'H', 'Summed'],
        'Discomfortable Total Hours': ['discomfhour', 'H', 'Summed'],
        'Occupied hours': ['occupied_hour', 'H', 'Summed'],
    }

    for key, val in EMSOutputVariableZone_dict.items():
        for name in target_names:
            if f'{key}_{name}' not in outputvariablelist:
                building.newidfobject(
                    'EnergyManagementSystem:OutputVariable',
                    Name=f'{key}_{name}',
                    EMS_Variable_Name=f'{val[0]}_{name}',
                    Type_of_Data_in_Variable=val[2],
                    Update_Frequency='ZoneTimestep',
                    Units=val[1]
                )
                if verboseMode: print(f'Added - {key}_{name} Output Variable')

    # Standard Output:Variables
    EMSoutputvariablenamelist = [v.Name for v in building.idfobjects['EnergyManagementSystem:OutputVariable']]

    for freq in outputs_freq:
        current_outputs = [o.Variable_Name for o in building.idfobjects['Output:Variable'] if o.Reporting_Frequency == freq.capitalize()]
        
        # Enable all EMS variables
        for outvar in EMSoutputvariablenamelist:
            if outvar not in current_outputs and not outvar.startswith("WIP"):
                building.newidfobject('Output:Variable', Key_Value='*', Variable_Name=outvar, Reporting_Frequency=freq.capitalize())
                if verboseMode: print(f'Added - {outvar} Reporting Frequency {freq.capitalize()}')

        if other_PMV_related_outputs:
            additional_outputs = [
                'Zone Operative Temperature',
                'Zone Thermal Comfort Clothing Surface Temperature',
                'Zone Thermal Comfort Clothing Value',
                'Zone Thermal Comfort Control Fanger High Setpoint PMV',
                'Zone Thermal Comfort Control Fanger Low Setpoint PMV',
                'Zone Thermal Comfort Fanger Model PMV',
                'Zone Thermal Comfort Fanger Model PPD',
                'Zone Thermal Comfort Mean Radiant Temperature',
                'Zone Air Relative Humidity',
                'Zone Mean Air Temperature',
                'Cooling Coil Total Cooling Rate',
                'Heating Coil Heating Rate',
                'Facility Total HVAC Electric Demand Power',
                'Facility Total HVAC Electricity Demand Rate',
                'AFN Surface Venting Window or Door Opening Factor',
                'AFN Zone Infiltration Air Change Rate',
                'AFN Zone Infiltration Volume',
                'AFN Zone Ventilation Air Change Rate',
                'AFN Zone Ventilation Volume',
            ]
            for item in additional_outputs:
                if item not in current_outputs:
                    building.newidfobject('Output:Variable', Key_Value='*', Variable_Name=item, Reporting_Frequency=freq.capitalize())
                    if verboseMode: print(f'Added - {item} Reporting Frequency {freq.capitalize()}')
            
            # Schedule Value Outputs
            # Legacy: PMV_H_SP_{ZoneName}
            # Modern: PMV_H_SP_{ZoneName} (Derived from hierarchy)
            zones_to_output = []
            if is_legacy:
                zones_to_output = target_names # These are ZoneNames_Underscore
            else:
                if hierarchy_dict:
                    zones_to_output = list(hierarchy_dict['zones'].keys())

            for i in ['PMV_H_SP', 'PMV_C_SP']:
                for zone in zones_to_output:
                    # In legacy, target_names is used directly. In modern, we use zone names.
                    # We need to ensure formatting matches the Schedule Object Name.
                    sch_name = f'{i}_{zone}'
                    building.newidfobject('Output:Variable', Key_Value=sch_name, Variable_Name='Schedule Value', Reporting_Frequency=freq.capitalize())
                    if verboseMode: print(f'Added - {sch_name} Reporting Frequency {freq.capitalize()}')

            # Air Velocity
            air_velocity_schs = list(set([i.Air_Velocity_Schedule_Name for i in building.idfobjects['people']]))
            for i in air_velocity_schs:
                if i not in current_outputs:
                    building.newidfobject('Output:Variable', Key_Value=i, Variable_Name='Schedule Value', Reporting_Frequency=freq.capitalize())
                    if verboseMode: print(f'Added - {i} Reporting Frequency {freq.capitalize()}')

    # Output Control
    outputcontrolfiles = [i for i in building.idfobjects['OutputControl:Files']]
    if not outputcontrolfiles:
        building.newidfobject('OutputControl:Files', Output_CSV='Yes', Output_MTR='Yes', Output_ESO='Yes')
        if verboseMode: print('Added - OutputControl:Files object')
    else:
        outputcontrolfiles[0].Output_CSV = 'Yes'
        outputcontrolfiles[0].Output_MTR = 'Yes'
        outputcontrolfiles[0].Output_ESO = 'Yes'
        if verboseMode: print('Modified - OutputControl:Files object')


# ==============================================================================
# UTILS
# ==============================================================================

def generate_df_from_args(
        building,
        target_keys_input,
        is_legacy_mode,
        adap_coeff_cooling,
        adap_coeff_heating,
        pmv_cooling_sp,
        pmv_heating_sp,
        tolerance_cooling_sp_cooling_season,
        tolerance_cooling_sp_heating_season,
        tolerance_heating_sp_cooling_season,
        tolerance_heating_sp_heating_season,
        dflt_for_adap_coeff_cooling,
        dflt_for_adap_coeff_heating,
        dflt_for_pmv_cooling_sp,
        dflt_for_pmv_heating_sp,
        dflt_for_tolerance_cooling_sp_cooling_season,
        dflt_for_tolerance_cooling_sp_heating_season,
        dflt_for_tolerance_heating_sp_cooling_season,
        dflt_for_tolerance_heating_sp_heating_season,
) -> pd.DataFrame:
    
    # target_keys_input contains the list of keys (People Names or Zone Names depending on mode)
    # This avoids re-scanning People objects inside this function, preventing version mismatches.
    
    space_ppl_names = target_keys_input

    data_adap_coeff_cooling = {}
    data_adap_coeff_heating = {}
    data_pmv_cooling_sp = {}
    data_pmv_heating_sp = {}
    data_tolerance_cooling_sp_cooling_season = {}
    data_tolerance_cooling_sp_heating_season = {}
    data_tolerance_heating_sp_cooling_season = {}
    data_tolerance_heating_sp_heating_season = {}

    for i, j, k, l in [
        (adap_coeff_cooling, data_adap_coeff_cooling, 'adap_coeff_cooling', dflt_for_adap_coeff_cooling),
        (adap_coeff_heating, data_adap_coeff_heating, 'adap_coeff_heating', dflt_for_adap_coeff_heating),
        (pmv_cooling_sp, data_pmv_cooling_sp, 'pmv_cooling_sp', dflt_for_pmv_cooling_sp),
        (pmv_heating_sp, data_pmv_heating_sp, 'pmv_heating_sp', dflt_for_pmv_heating_sp),
        (tolerance_cooling_sp_cooling_season, data_tolerance_cooling_sp_cooling_season, 'tolerance_cooling_sp_cooling_season', dflt_for_tolerance_cooling_sp_cooling_season),
        (tolerance_cooling_sp_heating_season, data_tolerance_cooling_sp_heating_season, 'tolerance_cooling_sp_heating_season', dflt_for_tolerance_cooling_sp_heating_season),
        (tolerance_heating_sp_cooling_season, data_tolerance_heating_sp_cooling_season, 'tolerance_heating_sp_cooling_season', dflt_for_tolerance_heating_sp_cooling_season),
        (tolerance_heating_sp_heating_season, data_tolerance_heating_sp_heating_season, 'tolerance_heating_sp_heating_season', dflt_for_tolerance_heating_sp_heating_season),
    ]:
        if type(i) is dict:
            j.update({'zone list': [x for x in i]})
            j.update({'dropped keys': []})
            for zone in j['zone list']:
                if zone not in space_ppl_names:
                    i.pop(zone)
                    j['dropped keys'].append(zone)
            if len(j['dropped keys']) > 0:
                warnings.warn(f'Values removed from {k} as target not found: {j["dropped keys"]}')
            j.update({'default values': {}})
            for zone in space_ppl_names:
                if zone not in j['zone list']:
                    i.update({zone: l})
                    j['default values'].update({zone: l})
            if len(j['default values']) > 0:
                warnings.warn(f'Default values set for {k}: {j["default values"]}')
            j.update({'series': pd.Series(i, name=k)})
        elif isinstance(i, (float, int)):
            j.update({'series': pd.Series(i, name=k, index=space_ppl_names)})

    df_arguments = pd.concat(
        [
            data_adap_coeff_cooling['series'],
            data_adap_coeff_heating['series'],
            data_pmv_cooling_sp['series'],
            data_pmv_heating_sp['series'],
            data_tolerance_cooling_sp_cooling_season['series'],
            data_tolerance_cooling_sp_heating_season['series'],
            data_tolerance_heating_sp_cooling_season['series'],
            data_tolerance_heating_sp_heating_season['series'],
        ],
        axis=1
    )
    
    # Generate the underscore name used for EMS variable generation
    if is_legacy_mode:
        df_arguments['underscore_zonename'] = [i.replace(':', '_').replace(' ', '_') for i in df_arguments.index]
    else:
        df_arguments['underscore_zonename'] = [i.replace(' ', '_') for i in df_arguments.index]

    return df_arguments


def set_zones_always_occupied(
        building,
        verboseMode: bool = True
):
    sch_comp_objs = [i.Name for i in building.idfobjects['schedule:compact']]

    if 'On' in sch_comp_objs:
        if verboseMode: print(f"On Schedule already was in the model")
    else:
        building.newidfobject(
            'Schedule:Compact',
            Name='On',
            Schedule_Type_Limits_Name="Any Number",
            Field_1='Through: 12/31',
            Field_2='For: AllDays',
            Field_3='Until: 24:00,1'
        )
        if verboseMode: print(f"On Schedule has been added")

    for i in [j for j in building.idfobjects['people']]:
        i.Number_of_People_Schedule_Name = 'On'

    return


def add_vrf_system(
        building,
        SupplyAirTempInputMethod: str = 'supply air temperature',
        eer: float = 2,
        cop: float = 2.1,
        VRFschedule: str = 'On 24/7',
        verboseMode: bool = True,
):
    EnergyPlus_version = f'{building.idd_version[0]}.{building.idd_version[1]}'

    z = accim_Main.accimJob(
        idf_class_instance=building,
        ScriptType='vrf_ac',
        EnergyPlus_version=EnergyPlus_version,
        TempCtrl='pmv',
        verboseMode=verboseMode
    )

    z.setComfFieldsPeople(EnergyPlus_version=EnergyPlus_version, TempCtrl='pmv', verboseMode=verboseMode)

    z.setPMVsetpoint(verboseMode=verboseMode)
    z.addBaseSchedules(verboseMode=verboseMode)
    z.setAvailSchOn(verboseMode=verboseMode)
    z.addVRFsystemSch(verboseMode=verboseMode)
    z.addCurveObj(verboseMode=verboseMode)
    z.addDetHVACobj(
        EnergyPlus_version=EnergyPlus_version,
        verboseMode=verboseMode,
        SupplyAirTempInputMethod=SupplyAirTempInputMethod,
        eer=eer,
        cop=cop,
        VRFschedule=VRFschedule
    )
    z.addForscriptSchVRFsystem(verboseMode=verboseMode)

def change_adaptive_coeff(building, df_arguments):
    # This is a stub helper for modification after generation
    # Needs to be aware of version or re-use underscore_zonename from DF
    for i in df_arguments.index:
        zonename = df_arguments.loc[i, 'underscore_zonename']
        program = [p for p in building.idfobjects['EnergyManagementSystem:Program']
                   if 'set_zone_input_data' in p.Name and zonename.lower() in p.Name.lower()]
        if program:
            program[0].Program_Line_1 = f'set adap_coeff_cooling_{zonename} = {df_arguments.loc[i, "adap_coeff_cooling"]}'
            program[0].Program_Line_2 = f'set adap_coeff_heating_{zonename} = {df_arguments.loc[i, "adap_coeff_heating"]}'


# ==============================================================================
# HELPER FUNCTIONS FOR USER INPUT GENERATION
# ==============================================================================

def get_available_target_names(building: besos.IDF_class) -> List[str]:
    """
    Identifies the valid target names based on the EnergyPlus version.

    - For versions >= 23.1: Returns ['SpaceName PeopleName', ...]
    - For versions < 23.1: Returns ['ZoneName', ...]

    Use these names as keys for the input dictionaries in apply_apmv_setpoints.

    :param building: The besos/eppy IDF object.
    :return: A list of strings representing the valid keys.
    """
    # 1. Detect Version
    version_tuple = building.idd_version
    is_legacy = (version_tuple[0] < 23) or (version_tuple[0] == 23 and version_tuple[1] < 1)

    target_names = []

    if is_legacy:
        # Legacy Logic: Return raw Zone Names directly from People objects
        try:
            ppl_temp = [[people.Zone_or_ZoneList_Name, people.Name] for people in building.idfobjects['People']]
        except AttributeError:
            try:
                ppl_temp = [[people.Zone_or_ZoneList_or_Space_or_SpaceList_Name, people.Name] for people in building.idfobjects['People']]
            except AttributeError:
                ppl_temp = [[people.Zone_Name, people.Name] for people in building.idfobjects['People']]

        # We return the raw Zone Name (e.g. "Zone One").
        # The main function will handle the conversion to "Zone_One" internally for EMS.
        target_names = [ppl[0] for ppl in ppl_temp]

    else:
        # Modern Logic: Use accim.utils to get Space-People names
        from accim.utils import get_people_names_for_ems

        # We return the raw list (e.g. "Space1 People1").
        # We DO NOT replace spaces here, because generate_df_from_args expects the raw keys.
        target_names = get_people_names_for_ems(idf=building)

    # Remove duplicates and return
    return list(dict.fromkeys(target_names))


def get_input_template_dictionary(building: besos.IDF_class) -> Dict[str, str]:
    """
    Generates a template dictionary with all valid target keys.
    The values are set to a placeholder string.

    :param building: The besos/eppy IDF object.
    :return: A dictionary {target_name: "replace_me_with_float_value"}
    """
    keys = get_available_target_names(building)
    return {key: "replace_me_with_float_value" for key in keys}