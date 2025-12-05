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

"""
Contains the functions to apply setpoints based on the Adaptive Predicted Mean Vote (aPMV) index
"""

import sys
import warnings
from typing import Dict, Any, List, Union

import pandas as pd
import besos.IDF_class
from eppy.modeleditor import IDF
import accim.sim.accim_Main_single_idf as accim_Main
from accim.utils import (
    get_idf_hierarchy,
    get_spaces_from_spacelist,
    get_people_names_for_ems,
    inspect_thermostat_objects,
    get_people_hierarchy,
    get_idf_hierarchy_with_people,
    transform_ddmm_to_int
)


def _ensure_thermostat_control(building: besos.IDF_class, instance: Dict[str, Any]):
    """
    Ensures that proper thermostat controls and schedules are in place.
    """
    # Create Schedule:Compact for PMV setpoints
    for i in range(len(instance['ZoneControl:Thermostat'])):
        zone_name = instance['ZoneControl:Thermostat'][i]['Zone_or_ZoneList_Name']
        for mode, value in (['H', -0.5], ['C', 0.5]):
            building.newidfobject(
                key='Schedule:Compact',
                Name=f'PMV_{mode}_SP_{zone_name}',
                Schedule_Type_Limits_Name="Any Number",
                Field_1='Through: 12/31',
                Field_2='For: AllDays',
                Field_3=f'Until: 24:00, {value}'
            )

    # Convert basic thermostats to thermal comfort thermostats
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
            for obj_type in ['ZoneControl:Thermostat', 'ThermostatSetpoint:DualSetpoint']:
                for i in range(len(building.idfobjects[obj_type])):
                    first_object = building.idfobjects[obj_type][-1]
                    building.removeidfobject(first_object)

    # Handle existing mixture of temperature and thermal comfort thermostats
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


def _add_apmv_sensors(building: besos.IDF_class, space_ppl_names: List[str], space_ppl_names_underscore: List[str], verboseMode: bool):
    """
    Adds EMS sensors for PMV and Occupant Count.
    """
    sensornamelist = ([sensor.Name for sensor in building.idfobjects['EnergyManagementSystem:Sensor']])

    for i in range(len(space_ppl_names_underscore)):
        if f'PMV_{space_ppl_names_underscore[i]}' in sensornamelist:
            if verboseMode:
                print(f'Not added - PMV_{space_ppl_names_underscore[i]} Sensor')
        else:
            building.newidfobject(
                'EnergyManagementSystem:Sensor',
                Name=f'PMV_{space_ppl_names_underscore[i]}',
                OutputVariable_or_OutputMeter_Index_Key_Name=space_ppl_names[i],
                OutputVariable_or_OutputMeter_Name='Zone Thermal Comfort Fanger Model PMV'
            )
            if verboseMode:
                print(f'Added - PMV_{space_ppl_names_underscore[i]} Sensor')

        if f'People_Occupant_Count_{space_ppl_names_underscore[i]}' in sensornamelist:
            if verboseMode:
                print(f'Not added - People_Occupant_Count_{space_ppl_names_underscore[i]} Sensor')
        else:
            building.newidfobject(
                'EnergyManagementSystem:Sensor',
                Name=f'People_Occupant_Count_{space_ppl_names_underscore[i]}',
                OutputVariable_or_OutputMeter_Index_Key_Name=space_ppl_names[i],
                OutputVariable_or_OutputMeter_Name='People Occupant Count'
            )
            if verboseMode:
                print(f'Added - People_Occupant_Count_{space_ppl_names_underscore[i]} Sensor')


def _add_apmv_actuators(building: besos.IDF_class, hierarchy_dict: Dict, verboseMode: bool):
    """
    Adds EMS actuators for PMV setpoints.
    """
    actuatornamelist = [actuator.Name for actuator in building.idfobjects['EnergyManagementSystem:Actuator']]

    for zone in hierarchy_dict['zones'].keys():
        for space in hierarchy_dict['zones'][zone]['spaces']:
            for i in ['H', 'C']:
                temp_name = f'PMV_{i}_SP_act_{space["name"]}_{space["people"].replace(" ", "_")}'
                if temp_name in actuatornamelist:
                    if verboseMode:
                        print(f'Not added - {temp_name} Actuator')
                else:
                    building.newidfobject(
                        'EnergyManagementSystem:Actuator',
                        Name=temp_name,
                        Actuated_Component_Unique_Name=f'PMV_{i}_SP_{zone}',
                        Actuated_Component_Type='Schedule:Compact',
                        Actuated_Component_Control_Type='Schedule Value',
                    )


def _add_apmv_global_variables(building: besos.IDF_class, space_ppl_names_underscore: List[str], verboseMode: bool):
    """
    Adds EMS global variables.
    """
    globalvariablenames = [
        'CoolingSeason',
        'CoolSeasonEnd',
        'CoolSeasonStart'
    ]

    globalvariablezonenames = []

    for i in [
        'tolerance_cooling_sp',
        'tolerance_cooling_sp_cooling_season',
        'tolerance_cooling_sp_heating_season',
        'tolerance_heating_sp',
        'tolerance_heating_sp_cooling_season',
        'tolerance_heating_sp_heating_season',
        'adap_coeff',
        'adap_coeff_heating',
        'adap_coeff_cooling',
        'pmv_heating_sp',
        'pmv_cooling_sp',
        'aPMV',
        'comfhour',
        'discomfhour',
        'discomfhour_heat',
        'discomfhour_cold',
        'occupied_hour',
        'aPMV_H_SP',
        'aPMV_C_SP',
        'aPMV_H_SP_noTol',
        'aPMV_C_SP_noTol',
    ]:
        for spaceppl in space_ppl_names_underscore:
            globalvariablezonenames.append(f'{i}_{spaceppl}')

    allgvs = globalvariablenames + globalvariablezonenames

    for gv in allgvs:
        building.newidfobject(
            'EnergyManagementSystem:GlobalVariable',
            Erl_Variable_1_Name=gv,
        )
        if verboseMode:
            print(f'Added - {gv} GlobalVariable object')


def _add_apmv_programs(
        building: besos.IDF_class,
        space_ppl_names: List[str],
        space_ppl_names_underscore: List[str],
        df_arguments: pd.DataFrame,
        cooling_season_start: int,
        cooling_season_end: int,
        verboseMode: bool
):
    """
    Adds EMS programs for aPMV logic.
    """
    programlist = [
        program.Name
        for program
        in building.idfobjects['EnergyManagementSystem:Program']
    ]

    if f'set_cooling_season_input_data' in programlist:
        if verboseMode:
            print(f'Not added - set_cooling_season_input_data Program')
    else:
        building.newidfobject(
            'EnergyManagementSystem:Program',
            Name=f'set_cooling_season_input_data',
            Program_Line_1=f'set CoolSeasonStart = {cooling_season_start}',
            Program_Line_2=f'set CoolSeasonEnd = {cooling_season_end}'
        )
        if verboseMode:
            print(f'Added - set_cooling_season_input_data Program')

    if f'set_cooling_season' in programlist:
        if verboseMode:
            print(f'Not added - set_cooling_season Program')
    else:
        building.newidfobject(
            'EnergyManagementSystem:Program',
            Name=f'set_cooling_season',
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
        if verboseMode:
            print(f'Added - set_cooling_season Program')

    for i in space_ppl_names:
        zonename = df_arguments.loc[i, 'underscore_zonename']

        if f'set_zone_input_data_{zonename}' in programlist:
            if verboseMode:
                print(f'Not added - set_zone_input_data_{zonename} Program')
        else:
            building.newidfobject(
                'EnergyManagementSystem:Program',
                Name=f'set_zone_input_data_{zonename}',
                Program_Line_1=f'set adap_coeff_cooling_{zonename} = {df_arguments.loc[i, "adap_coeff_cooling"]}',
                Program_Line_2=f'set adap_coeff_heating_{zonename} = {df_arguments.loc[i, "adap_coeff_heating"]}',
                Program_Line_3=f'set pmv_cooling_sp_{zonename} = {df_arguments.loc[i, "pmv_cooling_sp"]}',
                Program_Line_4=f'set pmv_heating_sp_{zonename} = {df_arguments.loc[i, "pmv_heating_sp"]}',
                Program_Line_5=f'set tolerance_cooling_sp_cooling_season_{zonename} = {df_arguments.loc[i, "tolerance_cooling_sp_cooling_season"]}',
                Program_Line_6=f'set tolerance_cooling_sp_heating_season_{zonename} = {df_arguments.loc[i, "tolerance_cooling_sp_heating_season"]}',
                Program_Line_7=f'set tolerance_heating_sp_cooling_season_{zonename} = {df_arguments.loc[i, "tolerance_heating_sp_cooling_season"]}',
                Program_Line_8=f'set tolerance_heating_sp_heating_season_{zonename} = {df_arguments.loc[i, "tolerance_heating_sp_heating_season"]}',
            )
            if verboseMode:
                print(f'Added - set_zone_input_data_{zonename} Program')

        if f'apply_aPMV_{zonename}' in programlist:
            if verboseMode:
                print(f'Not added - apply_aPMV_{zonename} Program')
        else:
            building.newidfobject(
                'EnergyManagementSystem:Program',
                Name=f'apply_aPMV_{zonename}',
                Program_Line_1='if CoolingSeason == 1',
                Program_Line_2='set adap_coeff_' + zonename + ' = adap_coeff_cooling_' + zonename + '',
                Program_Line_3='set tolerance_cooling_sp_' + zonename + ' = tolerance_cooling_sp_cooling_season_' + zonename + '',
                Program_Line_4='set tolerance_heating_sp_' + zonename + ' = tolerance_heating_sp_cooling_season_' + zonename + '',
                Program_Line_5='elseif CoolingSeason == 0',
                Program_Line_6='set adap_coeff_' + zonename + ' = adap_coeff_heating_' + zonename + '',
                Program_Line_7='set tolerance_cooling_sp_' + zonename + ' = tolerance_cooling_sp_heating_season_' + zonename + '',
                Program_Line_8='set tolerance_heating_sp_' + zonename + ' = tolerance_heating_sp_heating_season_' + zonename + '',
                Program_Line_9='endif',
                Program_Line_10='set aPMV_H_SP_noTol_' + zonename + ' = pmv_heating_sp_' + zonename + '/(1+adap_coeff_' + zonename + '*pmv_heating_sp_' + zonename + ')',
                Program_Line_11='set aPMV_C_SP_noTol_' + zonename + ' = pmv_cooling_sp_' + zonename + '/(1+adap_coeff_' + zonename + '*pmv_cooling_sp_' + zonename + ')',
                Program_Line_12='set aPMV_H_SP_' + zonename + ' = aPMV_H_SP_noTol_' + zonename + '+tolerance_heating_sp_' + zonename + '',
                Program_Line_13='set aPMV_C_SP_' + zonename + ' = aPMV_C_SP_noTol_' + zonename + '+tolerance_cooling_sp_' + zonename + '',
                Program_Line_14='if People_Occupant_Count_' + zonename + ' > 0',
                Program_Line_15='if aPMV_H_SP_' + zonename + ' < 0',
                Program_Line_16='set PMV_H_SP_act_' + zonename + ' = aPMV_H_SP_' + zonename + '',
                Program_Line_17='else',
                Program_Line_18='set PMV_H_SP_act_' + zonename + ' = 0',
                Program_Line_19='endif',
                Program_Line_20='if aPMV_C_SP_' + zonename + ' > 0',
                Program_Line_21='set PMV_C_SP_act_' + zonename + ' = aPMV_C_SP_' + zonename + '',
                Program_Line_22='else',
                Program_Line_23='set PMV_C_SP_act_' + zonename + ' = 0',
                Program_Line_24='endif',
                Program_Line_25='else',
                Program_Line_26='set PMV_H_SP_act_' + zonename + ' = -100',
                Program_Line_27='set PMV_C_SP_act_' + zonename + ' = 100',
                Program_Line_28='endif',
            )
            if verboseMode:
                print(f'Added - apply_aPMV_{zonename} Program')

    for zonename in space_ppl_names_underscore:
        if 'monitor_aPMV_' + zonename in programlist:
            if verboseMode:
                print('Not added - monitor_aPMV_' + zonename + ' Program')
        else:
            building.newidfobject(
                'EnergyManagementSystem:Program',
                Name='monitor_aPMV_' + zonename,
                Program_Line_1='set aPMV_' + zonename + ' = PMV_' + zonename + '/(1+adap_coeff_' + zonename + '*PMV_' + zonename + ')',
            )
            if verboseMode:
                print('Added - monitor_aPMV_' + zonename + ' Program')

        if 'count_aPMV_comfort_hours_' + zonename in programlist:
            if verboseMode:
                print('Not added - count_aPMV_comfort_hours_' + zonename + ' Program')
        else:
            building.newidfobject(
                'EnergyManagementSystem:Program',
                Name='count_aPMV_comfort_hours_' + zonename,
                Program_Line_1='if aPMV_' + zonename + ' < aPMV_H_SP_noTol_' + zonename + '',
                Program_Line_2='set comfhour_' + zonename + ' = 0',
                Program_Line_3='set discomfhour_cold_' + zonename + ' = 1*ZoneTimeStep',
                Program_Line_4='set discomfhour_heat_' + zonename + ' = 0',
                Program_Line_5='elseif aPMV_' + zonename + ' > aPMV_C_SP_noTol_' + zonename + '',
                Program_Line_6='set comfhour_' + zonename + ' = 0',
                Program_Line_7='set discomfhour_cold_' + zonename + ' = 0',
                Program_Line_8='set discomfhour_heat_' + zonename + ' = 1*ZoneTimeStep',
                Program_Line_9='else',
                Program_Line_10='set comfhour_' + zonename + ' = 1*ZoneTimeStep',
                Program_Line_11='set discomfhour_cold_' + zonename + ' = 0',
                Program_Line_12='set discomfhour_heat_' + zonename + ' = 0',
                Program_Line_13='endif',
                Program_Line_14='if People_Occupant_Count_' + zonename + ' > 0',
                Program_Line_15='set occupied_hour_' + zonename + ' = 1*ZoneTimeStep',
                Program_Line_16='else',
                Program_Line_17='set occupied_hour_' + zonename + ' = 0',
                Program_Line_18='endif',
                Program_Line_19='set discomfhour_' + zonename + ' = discomfhour_cold_' + zonename + ' + discomfhour_heat_' + zonename + '',
            )
            if verboseMode:
                print('Added - count_aPMV_comfort_hours_' + zonename + ' Program')


def _add_apmv_program_calling_managers(building: besos.IDF_class, verboseMode: bool):
    """
    Adds Program Calling Managers to execute the EMS programs.
    """
    programlist = ([program.Name
                    for program
                    in building.idfobjects['EnergyManagementSystem:Program']])
    pcmlist = ([pcm.Name
                for pcm
                in building.idfobjects['EnergyManagementSystem:ProgramCallingManager']])

    for i in programlist:
        if i in pcmlist:
            if verboseMode:
                print('Not added - ' + i + ' Program Calling Manager')
        else:
            building.newidfobject(
                'EnergyManagementSystem:ProgramCallingManager',
                Name=i,
                EnergyPlus_Model_Calling_Point="BeginTimestepBeforePredictor",
                Program_Name_1=i
            )
            if verboseMode:
                print('Added - ' + i + ' Program Calling Manager')


def _add_apmv_outputs(
        building: besos.IDF_class,
        outputs_freq: List[str],
        other_PMV_related_outputs: bool,
        space_ppl_names_underscore: List[str],
        hierarchy_dict: Dict,
        verboseMode: bool
):
    """
    Adds Output:Variable and OutputControl:Files objects.
    """
    # EMS:OutputVariable
    outputvariablelist = [
        outvar.Name
        for outvar
        in building.idfobjects['EnergyManagementSystem:OutputVariable']
    ]

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

    for i in EMSOutputVariableZone_dict:
        for zonename in space_ppl_names_underscore:
            if i + '_' + zonename in outputvariablelist:
                if verboseMode:
                    print('Not added - ' + i + '_' + zonename + ' Output Variable')
            else:
                building.newidfobject(
                    'EnergyManagementSystem:OutputVariable',
                    Name=i + '_' + zonename,
                    EMS_Variable_Name=EMSOutputVariableZone_dict[i][0] + '_' + zonename,
                    Type_of_Data_in_Variable=EMSOutputVariableZone_dict[i][2],
                    Update_Frequency='ZoneTimestep',
                    EMS_Program_or_Subroutine_Name='',
                    Units=EMSOutputVariableZone_dict[i][1]
                )
                if verboseMode:
                    print('Added - ' + i + '_' + zonename + ' Output Variable')

    # Output:Variable
    EMSoutputvariablenamelist = [
        outputvariable.Name
        for outputvariable
        in building.idfobjects['EnergyManagementSystem:OutputVariable']
    ]

    for freq in outputs_freq:
        outputnamelist = (
            [
                output.Variable_Name
                for output
                in building.idfobjects['Output:Variable']
                if output.Reporting_Frequency == freq.capitalize()
            ]
        )
        for outputvariable in EMSoutputvariablenamelist:
            if outputvariable in outputnamelist:
                if verboseMode:
                    print('Not added - ' + outputvariable + ' Reporting Frequency ' + freq.capitalize() + ' Output:Variable data')
            elif outputvariable.startswith("WIP"):
                if verboseMode:
                    print('Not added - ' + outputvariable + ' Output:Variable data because its WIP')
            else:
                building.newidfobject(
                    'Output:Variable',
                    Key_Value='*',
                    Variable_Name=outputvariable,
                    Reporting_Frequency=freq.capitalize(),
                    Schedule_Name=''
                )
                if verboseMode:
                    print('Added - ' + outputvariable + ' Reporting Frequency ' + freq.capitalize() + ' Output:Variable data')

    if other_PMV_related_outputs:
        addittionaloutputs = [
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

        for freq in outputs_freq:
            # Need to re-fetch outputnamelist for each freq logic or reuse.
            # The original logic looped freq then outputs.
            outputnamelist = (
                [
                    output.Variable_Name
                    for output
                    in building.idfobjects['Output:Variable']
                    if output.Reporting_Frequency == freq.capitalize()
                ]
            )
            for addittionaloutput in addittionaloutputs:
                if addittionaloutput in outputnamelist:
                    if verboseMode:
                        print('Not added - ' + addittionaloutput + ' Reporting Frequency ' + freq.capitalize() + ' Output:Variable data')
                else:
                    building.newidfobject(
                        'Output:Variable',
                        Key_Value='*',
                        Variable_Name=addittionaloutput,
                        Reporting_Frequency=freq.capitalize(),
                        Schedule_Name=''
                    )
                    if verboseMode:
                        print('Added - ' + addittionaloutput + ' Reporting Frequency ' + freq.capitalize() + ' Output:Variable data')

            for i in ['H', 'C']:
                for zone in hierarchy_dict['zones'].keys():
                    temp_name = f'PMV_{i}_SP_{zone}'
                    building.newidfobject(
                        'Output:Variable',
                        Key_Value=temp_name,
                        Variable_Name='Schedule Value',
                        Reporting_Frequency=freq.capitalize(),
                        Schedule_Name=''
                    )
                    if verboseMode:
                         print(f'Added - {temp_name}' + ' Reporting Frequency ' + freq.capitalize() + ' Output:Variable data')

            air_velocity_schs = list(set([i.Air_Velocity_Schedule_Name for i in building.idfobjects['people']]))

            for i in air_velocity_schs:
                if i in outputnamelist:
                    if verboseMode:
                        print('Not added - ' + i + ' Reporting Frequency ' + freq.capitalize() + ' Output:Variable data')
                else:
                    building.newidfobject(
                        'Output:Variable',
                        Key_Value=i,
                        Variable_Name='Schedule Value',
                        Reporting_Frequency=freq.capitalize(),
                        Schedule_Name=''
                    )
                    if verboseMode:
                        print(f'Added - {i}' + ' Reporting Frequency ' + freq.capitalize() + ' Output:Variable data')

    outputcontrolfiles = [i for i in building.idfobjects['OutputControl:Files']]
    if len(outputcontrolfiles) == 0:
        building.newidfobject(
            'OutputControl:Files',
            Output_CSV='Yes',
            Output_MTR='Yes',
            Output_ESO='Yes'
        )
        if verboseMode:
            print(f'Added - OutputControl:Files object')
    else:
        outputcontrolfiles[0].Output_CSV='Yes'
        outputcontrolfiles[0].Output_MTR='Yes'
        outputcontrolfiles[0].Output_ESO='Yes'
        if verboseMode:
            print(f'Not added - OutputControl:Files object - Output CSV, MTR and ESO fields set to Yes')


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
    """
    instance = inspect_thermostat_objects(idf=building)

    _ensure_thermostat_control(building, instance)

    hierarchy_dict = get_idf_hierarchy_with_people(idf=building)
    space_ppl_names = get_people_names_for_ems(idf=building)
    space_ppl_names_underscore = [i.replace(' ', '_') for i in space_ppl_names]

    # Managing cooling season start user input
    if type(cooling_season_start) is str:
        cooling_season_start = transform_ddmm_to_int(cooling_season_start)
    if type(cooling_season_end) is str:
        cooling_season_end = transform_ddmm_to_int(cooling_season_end)

    # Gathering arguments into df
    df_arguments = generate_df_from_args(
        building=building,
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

    # EMS
    _add_apmv_sensors(building, space_ppl_names, space_ppl_names_underscore, verboseMode)
    _add_apmv_actuators(building, hierarchy_dict, verboseMode)
    _add_apmv_global_variables(building, space_ppl_names_underscore, verboseMode)
    _add_apmv_programs(building, space_ppl_names, space_ppl_names_underscore, df_arguments, cooling_season_start, cooling_season_end, verboseMode)
    _add_apmv_program_calling_managers(building, verboseMode)
    _add_apmv_outputs(building, outputs_freq, other_PMV_related_outputs, space_ppl_names_underscore, hierarchy_dict, verboseMode)

    return building


def set_zones_always_occupied(
        building,
        verboseMode: bool = True
):
    """
    This function sets the schedule for zones to always be occupied.
    """
    sch_comp_objs = [i.Name for i in building.idfobjects['schedule:compact']]

    if 'On' in sch_comp_objs:
        if verboseMode:
            print(f"On Schedule already was in the model")
    else:
        building.newidfobject(
            'Schedule:Compact',
            Name='On',
            Schedule_Type_Limits_Name="Any Number",
            Field_1='Through: 12/31',
            Field_2='For: AllDays',
            Field_3='Until: 24:00,1'
        )
        if verboseMode:
            print(f"On Schedule has been added")

    for i in [j for j in building.idfobjects['people']]:
        i.Number_of_People_Schedule_Name = 'On'

    return


def generate_df_from_args(
        building: besos.IDF_class,
        adap_coeff_cooling: Union[float, dict] = 0.293,
        adap_coeff_heating: Union[float, dict] = -0.293,
        pmv_cooling_sp: Union[float, dict] = -0.5,
        pmv_heating_sp: Union[float, dict] = 0.5,
        tolerance_cooling_sp_cooling_season: Union[float, dict] = -0.1,
        tolerance_cooling_sp_heating_season: Union[float, dict] = -0.1,
        tolerance_heating_sp_cooling_season: Union[float, dict] = 0.1,
        tolerance_heating_sp_heating_season: Union[float, dict] = 0.1,
        dflt_for_adap_coeff_cooling: float = 0.4,
        dflt_for_adap_coeff_heating: float = -0.4,
        dflt_for_pmv_cooling_sp: float = 0.5,
        dflt_for_pmv_heating_sp: float = -0.5,
        dflt_for_tolerance_cooling_sp_cooling_season: float = -0.1,
        dflt_for_tolerance_cooling_sp_heating_season: float = -0.1,
        dflt_for_tolerance_heating_sp_cooling_season: float = 0.1,
        dflt_for_tolerance_heating_sp_heating_season: float = 0.1,
) -> pd.DataFrame:
    """
    Maps the arguments input by the user in a pandas.DataFrame instance.
    """
    space_ppl_names = get_people_names_for_ems(idf=building)

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
            # setting default value in case the zone is missing
            j.update({'zone list': [x for x in i]})
            j.update({'dropped keys': []})
            for zone in j['zone list']:
                if zone not in space_ppl_names:
                    i.pop(zone)
                    j['dropped keys'].append(zone)
            if len(j['dropped keys']) > 0:
                warnings.warn(
                    f'the following zones you entered at the {k} argument were not found, '
                    f'and therefore have been removed: {j["dropped keys"]}'
                )
            j.update({'default values': {}})
            for zone in space_ppl_names:
                if zone not in j['zone list']:
                    i.update({zone: l})
                    j['default values'].update({zone: l})
            if len(j['default values']) > 0:
                warnings.warn(
                    f'the following zones you entered at the {k} argument were not found, '
                    f'and therefore, considering these are occupied, default values have been set: '
                    f'{j["default values"]}'
                )
            j.update({'series': pd.Series(i, name=k)})
        elif type(i) is float or int:
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
    df_arguments['underscore_zonename'] = [i.replace(' ', '_') for i in df_arguments.index]

    return df_arguments


def change_adaptive_coeff(building, df_arguments):
    ppl_temp = [[people.Zone_or_ZoneList_Name, people.Name] for people in building.idfobjects['People']]
    zones_with_ppl_colon = [ppl[0] for ppl in ppl_temp]

    for i in zones_with_ppl_colon:
        zonename = df_arguments.loc[i, 'underscore_zonename']
        program = [p
                   for p
                   in building.idfobjects['EnergyManagementSystem:Program']
                   if 'set_zone_input_data' in p.Name
                   and zonename.lower() in p.Name.lower()
                   ][0]
        program.Program_Line_1 = f'set adap_coeff_cooling_{zonename} = {df_arguments.loc[i, "adap_coeff_cooling"]}',
        program.Program_Line_2 = f'set adap_coeff_heating_{zonename} = {df_arguments.loc[i, "adap_coeff_heating"]}',
    return


def change_pmv_setpoints(building, df_arguments):
    ppl_temp = [[people.Zone_or_ZoneList_Name, people.Name] for people in building.idfobjects['People']]
    zones_with_ppl_colon = [ppl[0] for ppl in ppl_temp]

    for i in zones_with_ppl_colon:
        zonename = df_arguments.loc[i, 'underscore_zonename']
        program = [p
                   for p
                   in building.idfobjects['EnergyManagementSystem:Program']
                   if 'set_zone_input_data' in p.Name
                   and zonename.lower() in p.Name.lower()
                   ][0]
        program.Program_Line_3 = f'set pmv_cooling_sp_{zonename} = {df_arguments.loc[i, "pmv_cooling_sp"]}',
        program.Program_Line_4 = f'set pmv_heating_sp_{zonename} = {df_arguments.loc[i, "pmv_heating_sp"]}',
    return


def change_pmv_heating_setpoint(building, df_arguments):
    ppl_temp = [[people.Zone_or_ZoneList_Name, people.Name] for people in building.idfobjects['People']]
    zones_with_ppl_colon = [ppl[0] for ppl in ppl_temp]

    for i in zones_with_ppl_colon:
        zonename = df_arguments.loc[i, 'underscore_zonename']
        program = [p
                   for p
                   in building.idfobjects['EnergyManagementSystem:Program']
                   if 'set_zone_input_data' in p.Name
                   and zonename.lower() in p.Name.lower()
                   ][0]
        program.Program_Line_4 = f'set pmv_heating_sp_{zonename} = {df_arguments.loc[i, "pmv_heating_sp"]}',
    return


def change_pmv_cooling_setpoint(building, df_arguments):
    ppl_temp = [[people.Zone_or_ZoneList_Name, people.Name] for people in building.idfobjects['People']]
    zones_with_ppl_colon = [ppl[0] for ppl in ppl_temp]

    for i in zones_with_ppl_colon:
        zonename = df_arguments.loc[i, 'underscore_zonename']
        program = [p
                   for p
                   in building.idfobjects['EnergyManagementSystem:Program']
                   if 'set_zone_input_data' in p.Name
                   and zonename.lower() in p.Name.lower()
                   ][0]
        program.Program_Line_3 = f'set pmv_cooling_sp_{zonename} = {df_arguments.loc[i, "pmv_cooling_sp"]}',
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

