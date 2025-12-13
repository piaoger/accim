# accim - Adaptive-Comfort-Control-Implemented Model
# Copyright (C) 2021-2025 Daniel Sánchez-García
# Distributed under the GNU General Public License v3 or later.

"""
Contains the functions to apply setpoints based on the Adaptive Predicted Mean Vote (aPMV) index.
Unified version supporting EnergyPlus versions pre and post 23.1.
Supports ZoneList and SpaceList expansion.
"""

import warnings
import os
import re
from typing import Dict, Any, List, Union, Optional
import pandas as pd
import besos.IDF_class
import besos.objectives
import eppy
from accim.utils import transform_ddmm_to_int
import accim.sim.accim_Main_single_idf as accim_Main

# ==============================================================================
# MONKEY PATCH FOR BESOS (Suppress Errors Only)
# ==============================================================================
try:
    _original_read_eso = besos.objectives.read_eso

    def _silent_read_eso(out_dir, file_name='eplusout.eso'):
        try:
            return _original_read_eso(out_dir, file_name)
        except Exception as e:
            warnings.warn(f"BESOS no pudo leer los resultados ({e}). Se continúa la ejecución sin datos de salida.")
            return None

    besos.objectives.read_eso = _silent_read_eso
except ImportError:
    pass


# ==============================================================================
# CORE RESOLUTION LOGIC
# ==============================================================================

def _sanitize_ems_name(name: str) -> str:
    """
    Replaces invalid characters for EMS variable names (spaces, colons, hyphens).
    """
    return name.replace(' ', '_').replace(':', '_').replace('-', '_')


def _resolve_targets(building: besos.IDF_class) -> List[Dict[str, str]]:
    """
    Analyzes the IDF to find all People objects and resolves their target Zones/Spaces.
    PRIORITY: SpaceList > ZoneList > Space > Zone.
    """
    targets = []

    # 1. Pre-fetch Lookups (Robust Population)
    # We try to fetch everything regardless of version flag, catching KeyErrors if objects don't exist.

    zone_lists = {}
    try:
        zone_lists = {zl.Name.upper().strip(): zl for zl in building.idfobjects['ZONELIST']}
    except KeyError:
        pass

    space_lists = {}
    try:
        space_lists = {sl.Name.upper().strip(): sl for sl in building.idfobjects['SPACELIST']}
    except KeyError:
        pass

    space_to_zone = {}
    try:
        for s in building.idfobjects['SPACE']:
            space_to_zone[s.Name.upper().strip()] = s.Zone_Name
    except KeyError:
        pass

    def get_items_from_list(obj, field_prefix):
        items = []
        for i in range(1, 500):
            try:
                val = obj[f"{field_prefix}_{i}_Name"]
                if val:
                    items.append(val)
                else:
                    break
            except:
                break
        return items

    # 2. Iterate all People objects
    for people in building.idfobjects['PEOPLE']:
        container_name = ""
        try:
            container_name = people.Zone_or_ZoneList_Name
        except:
            try:
                container_name = people.Zone_or_ZoneList_or_Space_or_SpaceList_Name
            except:
                container_name = people.Zone_Name

        if not container_name: continue

        p_name = people.Name
        c_name_upper = container_name.upper().strip()

        # --- PRIORITY 1: SPACELIST ---
        if c_name_upper in space_lists:
            sl_obj = space_lists[c_name_upper]
            spaces_in_list = get_items_from_list(sl_obj, "Space")

            for s in spaces_in_list:
                s_upper = s.upper().strip()
                # Find parent zone for this space
                if s_upper in space_to_zone:
                    parent_zone = space_to_zone[s_upper]
                    # Pattern: "SpaceName PeopleName"
                    full_key = f"{s} {p_name}"
                    targets.append({
                        'df_key': full_key,
                        'ems_suffix': _sanitize_ems_name(f"{s}_{p_name}"),
                        'sensor_key': full_key,
                        'zone_name': parent_zone  # RAW Zone Name (for Schedule/Thermostat)
                    })
                else:
                    # Fallback: If space exists in list but mapping failed, try to use space name as zone?
                    # This usually implies a malformed IDF or missing Space objects.
                    warnings.warn(f"Space '{s}' found in SpaceList '{container_name}' but not found in SPACE objects. Skipping.")

        # --- PRIORITY 2: ZONELIST ---
        elif c_name_upper in zone_lists:
            zl_obj = zone_lists[c_name_upper]
            zones_in_list = get_items_from_list(zl_obj, "Zone")
            for z in zones_in_list:
                # Pattern: "ZoneName PeopleName"
                full_key = f"{z} {p_name}"
                targets.append({
                    'df_key': full_key,
                    'ems_suffix': _sanitize_ems_name(f"{z}_{p_name}"),
                    'sensor_key': full_key,
                    'zone_name': z  # RAW Zone Name
                })

        # --- PRIORITY 3: SPACE (Direct) ---
        elif c_name_upper in space_to_zone:
            parent_zone = space_to_zone[c_name_upper]
            # Pattern: "SpaceName PeopleName"
            full_key = f"{container_name} {p_name}"
            targets.append({
                'df_key': full_key,
                'ems_suffix': _sanitize_ems_name(f"{container_name}_{p_name}"),
                'sensor_key': full_key,
                'zone_name': parent_zone  # RAW Zone Name
            })

        # --- PRIORITY 4: ZONE (Direct) ---
        else:
            # Pattern: "ZoneName" (Legacy compatible) or just ZoneName for direct assignment
            targets.append({
                'df_key': container_name,
                'ems_suffix': _sanitize_ems_name(container_name),
                'sensor_key': p_name,
                'zone_name': container_name  # RAW Zone Name
            })

    return targets

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
    
    # 1. Resolve Targets
    target_data = _resolve_targets(building)
    
    # Extract lists
    ems_target_suffixes = [t['ems_suffix'] for t in target_data]
    ems_sensor_keys = [t['sensor_key'] for t in target_data]
    df_keys = [t['df_key'] for t in target_data]
    target_zones = [t['zone_name'] for t in target_data]
    
    unique_zones = list(set(target_zones))

    # 2. Prepare Data
    if isinstance(cooling_season_start, str):
        cooling_season_start = transform_ddmm_to_int(cooling_season_start)
    if isinstance(cooling_season_end, str):
        cooling_season_end = transform_ddmm_to_int(cooling_season_end)

    # 3. Ensure Infrastructure (Schedules & Thermostats)
    # IMPORTANT: We use RAW zone names here to match IDF objects
    _ensure_infrastructure(building, unique_zones, verboseMode)

    # 4. Generate DataFrame
    df_arguments = generate_df_from_args(
        target_keys_input=df_keys,
        ems_suffixes=ems_target_suffixes,
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

    # 5. EMS Generation
    _add_apmv_sensors(building, ems_sensor_keys, ems_target_suffixes, verboseMode)
    _add_apmv_global_variables(building, ems_target_suffixes, verboseMode)
    _add_apmv_actuators(building, target_data, verboseMode)
    _add_apmv_programs(building, ems_target_suffixes, df_arguments, cooling_season_start, cooling_season_end, verboseMode)
    _add_apmv_program_calling_managers(building, verboseMode)
    _add_apmv_outputs(building, outputs_freq, other_PMV_related_outputs, ems_target_suffixes, unique_zones, verboseMode)

    return building


# ==============================================================================
# INFRASTRUCTURE HELPERS (Restored & Robust)
# ==============================================================================

def _ensure_infrastructure(building, unique_zones, verboseMode):
    """
    Ensures Schedules and Thermostats exist for the target zones.
    Uses RAW zone names to ensure linkage.
    """
    sch_comp_objs = [i.Name for i in building.idfobjects['Schedule:Compact']]
    
    # 1. Create Schedules (Using RAW Zone Name)
    for i in ['PMV_H_SP', 'PMV_C_SP']:
        for zone in unique_zones:
            sch_name = f'{i}_{zone}'
            if sch_name not in sch_comp_objs:
                building.newidfobject(
                    'Schedule:Compact',
                    Name=sch_name,
                    Schedule_Type_Limits_Name="Any Number",
                    Field_1='Through: 12/31',
                    Field_2='For: AllDays',
                    Field_3='Until: 24:00,1'
                )
                if verboseMode: print(f"{sch_name} Schedule has been added")

    # 2. Ensure Thermostats (Logic from wip_3 restored)
    # We need to find the thermostat object for each zone and ensure it's a ThermalComfort one
    
    # Map existing thermostats by Zone Name
    existing_thermostats = {}
    for t in building.idfobjects['ZoneControl:Thermostat']:
        existing_thermostats[t.Zone_or_ZoneList_Name.upper()] = t
        
    existing_tc_thermostats = {}
    for t in building.idfobjects['ZoneControl:Thermostat:ThermalComfort']:
        existing_tc_thermostats[t.Zone_or_ZoneList_Name.upper()] = t

    for zone in unique_zones:
        z_upper = zone.upper()
        
        # Case A: No thermostat at all -> Create one
        if z_upper not in existing_thermostats and z_upper not in existing_tc_thermostats:
            _create_tc_thermostat(building, zone)
            if verboseMode: print(f"Created Thermal Comfort Thermostat for {zone}")

        # Case B: Standard Thermostat exists -> Convert/Replace
        elif z_upper in existing_thermostats and z_upper not in existing_tc_thermostats:
            old_t = existing_thermostats[z_upper]
            # We remove the old one and create a new ThermalComfort one
            # (Or we could try to modify it, but replacing is safer for type change)
            building.removeidfobject(old_t)
            _create_tc_thermostat(building, zone)
            if verboseMode: print(f"Replaced Standard Thermostat with Thermal Comfort for {zone}")

        # Case C: Thermal Comfort Thermostat exists -> Update Schedules
        elif z_upper in existing_tc_thermostats:
            tc_t = existing_tc_thermostats[z_upper]
            # Ensure it points to a Fanger object
            if tc_t.Thermal_Comfort_Control_1_Object_Type != 'ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint':
                tc_t.Thermal_Comfort_Control_1_Object_Type = 'ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint'
                tc_t.Thermal_Comfort_Control_1_Name = f'Fanger Setpoint {zone}'
            
            # Update/Create the Fanger object
            _update_fanger_object(building, f'Fanger Setpoint {zone}', zone)

def _create_tc_thermostat(building, zone):
    # 1. Control Type Schedule
    sch_name = f'Thermal Comfort Control Type Schedule Name {zone}'
    if not any(s.Name == sch_name for s in building.idfobjects['Schedule:Compact']):
        building.newidfobject(
            'Schedule:Compact',
            Name=sch_name,
            Schedule_Type_Limits_Name="Any Number",
            Field_1='Through: 12/31',
            Field_2='For: AllDays',
            Field_3='Until: 24:00,4' # 4 = Thermal Comfort
        )

    # 2. The Thermostat Object
    building.newidfobject(
        'ZoneControl:Thermostat:ThermalComfort',
        Name=f'Thermostat Setpoint Dual Setpoint {zone}',
        Zone_or_ZoneList_Name=zone,
        Thermal_Comfort_Control_Type_Schedule_Name=sch_name,
        Thermal_Comfort_Control_1_Object_Type='ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint',
        Thermal_Comfort_Control_1_Name=f'Fanger Setpoint {zone}'
    )

    # 3. The Fanger Object
    _update_fanger_object(building, f'Fanger Setpoint {zone}', zone)

def _update_fanger_object(building, obj_name, zone):
    # Check if exists
    fanger_obj = None
    for f in building.idfobjects['ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint']:
        if f.Name == obj_name:
            fanger_obj = f
            break
    
    if not fanger_obj:
        fanger_obj = building.newidfobject(
            'ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint',
            Name=obj_name
        )
    
    # Link to the PMV schedules we created
    fanger_obj.Fanger_Thermal_Comfort_Heating_Schedule_Name = f'PMV_H_SP_{zone}'
    fanger_obj.Fanger_Thermal_Comfort_Cooling_Schedule_Name = f'PMV_C_SP_{zone}'


def _add_apmv_actuators(building, target_data, verboseMode):
    actuatornamelist = [actuator.Name for actuator in building.idfobjects['EnergyManagementSystem:Actuator']]
    
    for target in target_data:
        suffix = target['ems_suffix'] # Sanitized
        zone = target['zone_name']    # Raw
        
        for i in ['H', 'C']:
            act_name = f'PMV_{i}_SP_act_{suffix}'
            sch_name = f'PMV_{i}_SP_{zone}' # Target the RAW schedule name
            
            if act_name not in actuatornamelist:
                building.newidfobject(
                    'EnergyManagementSystem:Actuator',
                    Name=act_name,
                    Actuated_Component_Unique_Name=sch_name,
                    Actuated_Component_Type='Schedule:Compact',
                    Actuated_Component_Control_Type='Schedule Value',
                )
                if verboseMode: print(f'Added - {act_name} Actuator')

# ==============================================================================
# EMS GENERATORS
# ==============================================================================

def _add_apmv_sensors(building, sensor_keys, suffixes, verboseMode):
    sensornamelist = [s.Name for s in building.idfobjects['EnergyManagementSystem:Sensor']]
    for i in range(len(suffixes)):
        if f'PMV_{suffixes[i]}' not in sensornamelist:
            building.newidfobject(
                'EnergyManagementSystem:Sensor',
                Name=f'PMV_{suffixes[i]}',
                OutputVariable_or_OutputMeter_Index_Key_Name=sensor_keys[i],
                OutputVariable_or_OutputMeter_Name='Zone Thermal Comfort Fanger Model PMV'
            )
        if f'People_Occupant_Count_{suffixes[i]}' not in sensornamelist:
            building.newidfobject(
                'EnergyManagementSystem:Sensor',
                Name=f'People_Occupant_Count_{suffixes[i]}',
                OutputVariable_or_OutputMeter_Index_Key_Name=sensor_keys[i],
                OutputVariable_or_OutputMeter_Name='People Occupant Count'
            )

def _add_apmv_global_variables(building, suffixes, verboseMode):
    prefixes = [
        'tolerance_cooling_sp', 'tolerance_cooling_sp_cooling_season', 'tolerance_cooling_sp_heating_season',
        'tolerance_heating_sp', 'tolerance_heating_sp_cooling_season', 'tolerance_heating_sp_heating_season',
        'adap_coeff', 'adap_coeff_heating', 'adap_coeff_cooling',
        'pmv_heating_sp', 'pmv_cooling_sp', 'aPMV',
        'comfhour', 'discomfhour', 'discomfhour_heat', 'discomfhour_cold', 'occupied_hour',
        'aPMV_H_SP', 'aPMV_C_SP', 'aPMV_H_SP_noTol', 'aPMV_C_SP_noTol'
    ]
    existing = {gv.Erl_Variable_1_Name for gv in building.idfobjects['EnergyManagementSystem:GlobalVariable']}
    
    for gv in ['CoolingSeason', 'CoolSeasonEnd', 'CoolSeasonStart']:
        if gv not in existing: building.newidfobject('EnergyManagementSystem:GlobalVariable', Erl_Variable_1_Name=gv)

    for prefix in prefixes:
        for suffix in suffixes:
            gv = f'{prefix}_{suffix}'
            if gv not in existing:
                building.newidfobject('EnergyManagementSystem:GlobalVariable', Erl_Variable_1_Name=gv)

def _add_apmv_programs(building, suffixes, df_arguments, cool_start, cool_end, verboseMode):
    programlist = [p.Name for p in building.idfobjects['EnergyManagementSystem:Program']]

    if 'set_cooling_season_input_data' not in programlist:
        building.newidfobject('EnergyManagementSystem:Program', Name='set_cooling_season_input_data',
            Program_Line_1=f'set CoolSeasonStart = {cool_start}', Program_Line_2=f'set CoolSeasonEnd = {cool_end}')
    
    if 'set_cooling_season' not in programlist:
        building.newidfobject('EnergyManagementSystem:Program', Name='set_cooling_season',
            Program_Line_1='if CoolSeasonEnd > CoolSeasonStart',
            Program_Line_2='if (DayOfYear >= CoolSeasonStart) && (DayOfYear < CoolSeasonEnd)',
            Program_Line_3='set CoolingSeason = 1',
            Program_Line_4='else', Program_Line_5='set CoolingSeason = 0', Program_Line_6='endif',
            Program_Line_7='elseif CoolSeasonStart > CoolSeasonEnd',
            Program_Line_8='if (DayOfYear >= CoolSeasonStart) || (DayOfYear < CoolSeasonEnd)',
            Program_Line_9='set CoolingSeason = 1',
            Program_Line_10='else', Program_Line_11='set CoolingSeason = 0', Program_Line_12='endif',
            Program_Line_13='endif')

    for suffix in suffixes:
        try:
            row_idx = df_arguments[df_arguments['underscore_zonename'] == suffix].index[0]
        except IndexError:
            continue

        if f'set_zone_input_data_{suffix}' not in programlist:
            building.newidfobject('EnergyManagementSystem:Program', Name=f'set_zone_input_data_{suffix}',
                Program_Line_1=f'set adap_coeff_cooling_{suffix} = {df_arguments.loc[row_idx, "adap_coeff_cooling"]}',
                Program_Line_2=f'set adap_coeff_heating_{suffix} = {df_arguments.loc[row_idx, "adap_coeff_heating"]}',
                Program_Line_3=f'set pmv_cooling_sp_{suffix} = {df_arguments.loc[row_idx, "pmv_cooling_sp"]}',
                Program_Line_4=f'set pmv_heating_sp_{suffix} = {df_arguments.loc[row_idx, "pmv_heating_sp"]}',
                Program_Line_5=f'set tolerance_cooling_sp_cooling_season_{suffix} = {df_arguments.loc[row_idx, "tolerance_cooling_sp_cooling_season"]}',
                Program_Line_6=f'set tolerance_cooling_sp_heating_season_{suffix} = {df_arguments.loc[row_idx, "tolerance_cooling_sp_heating_season"]}',
                Program_Line_7=f'set tolerance_heating_sp_cooling_season_{suffix} = {df_arguments.loc[row_idx, "tolerance_heating_sp_cooling_season"]}',
                Program_Line_8=f'set tolerance_heating_sp_heating_season_{suffix} = {df_arguments.loc[row_idx, "tolerance_heating_sp_heating_season"]}')

        if f'apply_aPMV_{suffix}' not in programlist:
            act_h = f'PMV_H_SP_act_{suffix}'
            act_c = f'PMV_C_SP_act_{suffix}'
            building.newidfobject('EnergyManagementSystem:Program', Name=f'apply_aPMV_{suffix}',
                Program_Line_1='if CoolingSeason == 1',
                Program_Line_2=f'set adap_coeff_{suffix} = adap_coeff_cooling_{suffix}',
                Program_Line_3=f'set tolerance_cooling_sp_{suffix} = tolerance_cooling_sp_cooling_season_{suffix}',
                Program_Line_4=f'set tolerance_heating_sp_{suffix} = tolerance_heating_sp_cooling_season_{suffix}',
                Program_Line_5='elseif CoolingSeason == 0',
                Program_Line_6=f'set adap_coeff_{suffix} = adap_coeff_heating_{suffix}',
                Program_Line_7=f'set tolerance_cooling_sp_{suffix} = tolerance_cooling_sp_heating_season_{suffix}',
                Program_Line_8=f'set tolerance_heating_sp_{suffix} = tolerance_heating_sp_heating_season_{suffix}',
                Program_Line_9='endif',
                Program_Line_10=f'set aPMV_H_SP_noTol_{suffix} = pmv_heating_sp_{suffix}/(1+adap_coeff_{suffix}*pmv_heating_sp_{suffix})',
                Program_Line_11=f'set aPMV_C_SP_noTol_{suffix} = pmv_cooling_sp_{suffix}/(1+adap_coeff_{suffix}*pmv_cooling_sp_{suffix})',
                Program_Line_12=f'set aPMV_H_SP_{suffix} = aPMV_H_SP_noTol_{suffix}+tolerance_heating_sp_{suffix}',
                Program_Line_13=f'set aPMV_C_SP_{suffix} = aPMV_C_SP_noTol_{suffix}+tolerance_cooling_sp_{suffix}',
                Program_Line_14=f'if People_Occupant_Count_{suffix} > 0',
                Program_Line_15=f'if aPMV_H_SP_{suffix} < 0',
                Program_Line_16=f'set {act_h} = aPMV_H_SP_{suffix}',
                Program_Line_17='else', Program_Line_18=f'set {act_h} = 0', Program_Line_19='endif',
                Program_Line_20=f'if aPMV_C_SP_{suffix} > 0',
                Program_Line_21=f'set {act_c} = aPMV_C_SP_{suffix}',
                Program_Line_22='else', Program_Line_23=f'set {act_c} = 0', Program_Line_24='endif',
                Program_Line_25='else',
                Program_Line_26=f'set {act_h} = -100', Program_Line_27=f'set {act_c} = 100',
                Program_Line_28='endif')

        if f'monitor_aPMV_{suffix}' not in programlist:
            building.newidfobject('EnergyManagementSystem:Program', Name=f'monitor_aPMV_{suffix}',
                Program_Line_1=f'set aPMV_{suffix} = PMV_{suffix}/(1+adap_coeff_{suffix}*PMV_{suffix})')

        if f'count_aPMV_comfort_hours_{suffix}' not in programlist:
            building.newidfobject('EnergyManagementSystem:Program', Name=f'count_aPMV_comfort_hours_{suffix}',
                Program_Line_1=f'if aPMV_{suffix} < aPMV_H_SP_noTol_{suffix}',
                Program_Line_2=f'set comfhour_{suffix} = 0',
                Program_Line_3=f'set discomfhour_cold_{suffix} = 1*ZoneTimeStep',
                Program_Line_4=f'set discomfhour_heat_{suffix} = 0',
                Program_Line_5=f'elseif aPMV_{suffix} > aPMV_C_SP_noTol_{suffix}',
                Program_Line_6=f'set comfhour_{suffix} = 0',
                Program_Line_7=f'set discomfhour_cold_{suffix} = 0',
                Program_Line_8=f'set discomfhour_heat_{suffix} = 1*ZoneTimeStep',
                Program_Line_9='else',
                Program_Line_10=f'set comfhour_{suffix} = 1*ZoneTimeStep',
                Program_Line_11=f'set discomfhour_cold_{suffix} = 0',
                Program_Line_12=f'set discomfhour_heat_{suffix} = 0',
                Program_Line_13='endif',
                Program_Line_14=f'if People_Occupant_Count_{suffix} > 0',
                Program_Line_15=f'set occupied_hour_{suffix} = 1*ZoneTimeStep',
                Program_Line_16='else', Program_Line_17=f'set occupied_hour_{suffix} = 0', Program_Line_18='endif',
                Program_Line_19=f'set discomfhour_{suffix} = discomfhour_cold_{suffix} + discomfhour_heat_{suffix}')

def _add_apmv_program_calling_managers(building, verboseMode):
    programlist = [p.Name for p in building.idfobjects['EnergyManagementSystem:Program']]
    pcmlist = [pcm.Name for pcm in building.idfobjects['EnergyManagementSystem:ProgramCallingManager']]
    for prog in programlist:
        if prog not in pcmlist:
            building.newidfobject('EnergyManagementSystem:ProgramCallingManager', Name=prog,
                EnergyPlus_Model_Calling_Point="BeginTimestepBeforePredictor", Program_Name_1=prog)

def _add_apmv_outputs(building, outputs_freq, other_PMV_related_outputs, suffixes, unique_zones, verboseMode):
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
        for suffix in suffixes:
            if f'{key}_{suffix}' not in outputvariablelist:
                building.newidfobject('EnergyManagementSystem:OutputVariable', Name=f'{key}_{suffix}',
                    EMS_Variable_Name=f'{val[0]}_{suffix}', Type_of_Data_in_Variable=val[2],
                    Update_Frequency='ZoneTimestep', Units=val[1])

    for freq in outputs_freq:
        current_outputs = [o.Variable_Name for o in building.idfobjects['Output:Variable'] if o.Reporting_Frequency == freq.capitalize()]
        for outvar in [v.Name for v in building.idfobjects['EnergyManagementSystem:OutputVariable']]:
            if outvar not in current_outputs and not outvar.startswith("WIP"):
                building.newidfobject('Output:Variable', Key_Value='*', Variable_Name=outvar, Reporting_Frequency=freq.capitalize())

        # Use RAW zone names for Schedule outputs
        for i in ['PMV_H_SP', 'PMV_C_SP']:
            for zone in unique_zones:
                sch_name = f'{i}_{zone}'
                building.newidfobject('Output:Variable', Key_Value=sch_name, Variable_Name='Schedule Value', Reporting_Frequency=freq.capitalize())

        if other_PMV_related_outputs:
            additional = ['Zone Operative Temperature', 'Zone Thermal Comfort Fanger Model PMV', 'Zone Thermal Comfort Fanger Model PPD', 'Zone Mean Air Temperature']
            for item in additional:
                if item not in current_outputs:
                    building.newidfobject('Output:Variable', Key_Value='*', Variable_Name=item, Reporting_Frequency=freq.capitalize())

    if not building.idfobjects['OutputControl:Files']:
        building.newidfobject('OutputControl:Files', Output_CSV='Yes', Output_MTR='Yes', Output_ESO='Yes')
    else:
        building.idfobjects['OutputControl:Files'][0].Output_CSV = 'Yes'
        building.idfobjects['OutputControl:Files'][0].Output_MTR = 'Yes'
        building.idfobjects['OutputControl:Files'][0].Output_ESO = 'Yes'

# ==============================================================================
# UTILS
# ==============================================================================

def generate_df_from_args(
        target_keys_input,
        ems_suffixes,
        adap_coeff_cooling, adap_coeff_heating,
        pmv_cooling_sp, pmv_heating_sp,
        tolerance_cooling_sp_cooling_season, tolerance_cooling_sp_heating_season,
        tolerance_heating_sp_cooling_season, tolerance_heating_sp_heating_season,
        dflt_for_adap_coeff_cooling, dflt_for_adap_coeff_heating,
        dflt_for_pmv_cooling_sp, dflt_for_pmv_heating_sp,
        dflt_for_tolerance_cooling_sp_cooling_season, dflt_for_tolerance_cooling_sp_heating_season,
        dflt_for_tolerance_heating_sp_cooling_season, dflt_for_tolerance_heating_sp_heating_season,
) -> pd.DataFrame:
    
    space_ppl_names = target_keys_input
    
    def process_arg(arg_val, arg_name, default_val):
        data = {}
        if isinstance(arg_val, dict):
            valid_keys = [k for k in arg_val if k in space_ppl_names]
            dropped = [k for k in arg_val if k not in space_ppl_names]
            if dropped: warnings.warn(f"Keys dropped from {arg_name}: {dropped}")
            for k in space_ppl_names:
                data[k] = arg_val.get(k, default_val)
        else:
            for k in space_ppl_names:
                data[k] = arg_val
        return pd.Series(data, name=arg_name)

    series_list = [
        process_arg(adap_coeff_cooling, 'adap_coeff_cooling', dflt_for_adap_coeff_cooling),
        process_arg(adap_coeff_heating, 'adap_coeff_heating', dflt_for_adap_coeff_heating),
        process_arg(pmv_cooling_sp, 'pmv_cooling_sp', dflt_for_pmv_cooling_sp),
        process_arg(pmv_heating_sp, 'pmv_heating_sp', dflt_for_pmv_heating_sp),
        process_arg(tolerance_cooling_sp_cooling_season, 'tolerance_cooling_sp_cooling_season', dflt_for_tolerance_cooling_sp_cooling_season),
        process_arg(tolerance_cooling_sp_heating_season, 'tolerance_cooling_sp_heating_season', dflt_for_tolerance_cooling_sp_heating_season),
        process_arg(tolerance_heating_sp_cooling_season, 'tolerance_heating_sp_cooling_season', dflt_for_tolerance_heating_sp_cooling_season),
        process_arg(tolerance_heating_sp_heating_season, 'tolerance_heating_sp_heating_season', dflt_for_tolerance_heating_sp_heating_season),
    ]

    df_arguments = pd.concat(series_list, axis=1)
    suffix_map = dict(zip(target_keys_input, ems_suffixes))
    df_arguments['underscore_zonename'] = df_arguments.index.map(suffix_map)

    return df_arguments

def get_available_target_names(building: besos.IDF_class) -> List[str]:
    targets = _resolve_targets(building)
    return [t['df_key'] for t in targets]

def get_input_template_dictionary(building: besos.IDF_class) -> Dict[str, str]:
    keys = get_available_target_names(building)
    return {key: "replace-me-with-float-value" for key in keys}

def set_zones_always_occupied(building, verboseMode: bool = True):
    sch_comp_objs = [i.Name for i in building.idfobjects['schedule:compact']]
    if 'On' not in sch_comp_objs:
        building.newidfobject('Schedule:Compact', Name='On', Schedule_Type_Limits_Name="Any Number",
            Field_1='Through: 12/31', Field_2='For: AllDays', Field_3='Until: 24:00,1')
    for i in building.idfobjects['people']:
        i.Number_of_People_Schedule_Name = 'On'

def add_vrf_system(building, SupplyAirTempInputMethod='supply air temperature', eer=2, cop=2.1, VRFschedule='On 24/7', verboseMode=True):
    EnergyPlus_version = f'{building.idd_version[0]}.{building.idd_version[1]}'
    z = accim_Main.accimJob(idf_class_instance=building, ScriptType='vrf_ac', EnergyPlus_version=EnergyPlus_version, TempCtrl='pmv', verboseMode=verboseMode)
    z.setComfFieldsPeople(EnergyPlus_version=EnergyPlus_version, TempCtrl='pmv', verboseMode=verboseMode)
    z.setPMVsetpoint(verboseMode=verboseMode)
    z.addBaseSchedules(verboseMode=verboseMode)
    z.setAvailSchOn(verboseMode=verboseMode)
    z.addVRFsystemSch(verboseMode=verboseMode)
    z.addCurveObj(verboseMode=verboseMode)
    z.addDetHVACobj(EnergyPlus_version=EnergyPlus_version, verboseMode=verboseMode, SupplyAirTempInputMethod=SupplyAirTempInputMethod, eer=eer, cop=cop, VRFschedule=VRFschedule)
    z.addForscriptSchVRFsystem(verboseMode=verboseMode)

def change_adaptive_coeff(building, df_arguments):
    for i in df_arguments.index:
        zonename = df_arguments.loc[i, 'underscore_zonename']
        program = [p for p in building.idfobjects['EnergyManagementSystem:Program']
                   if 'set_zone_input_data' in p.Name and zonename.lower() in p.Name.lower()]
        if program:
            program[0].Program_Line_1 = f'set adap_coeff_cooling_{zonename} = {df_arguments.loc[i, "adap_coeff_cooling"]}'
            program[0].Program_Line_2 = f'set adap_coeff_heating_{zonename} = {df_arguments.loc[i, "adap_coeff_heating"]}'