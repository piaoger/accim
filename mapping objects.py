from accim.utils import inspect_thermostat_objects, get_available_fields
import besos.eppy_funcs as ef



# building = ef.get_building("Test_VRF_mult-spa-in-zone_v02.idf")
# building = ef.get_building("TestModel_TestResidentialUnit_v01_VRF_2.idf")
building = ef.get_building("TestModel_TestResidentialUnit_v01_VRF_2_with_tc_objs.idf")


fields = get_available_fields(idf_instance=building,object_name='ZoneControl:Thermostat:ThermalComfort')
fields = get_available_fields(idf_instance=building,object_name='ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint')

fields

instance = inspect_thermostat_objects(idf=building)


# idf_zones = [i for i in building.idfobjects['zone']]
for i in range(len(instance['ZoneControl:Thermostat'])):
    zone_name = instance['ZoneControl:Thermostat'][i]['Zone_or_ZoneList_Name']
    for mode, value in (['Heating', -0.5], ['Cooling', 0.5]):
        building.newidfobject(
            key='Schedule:Compact',
            Name=f'Fanger {mode} Setpoint {zone_name}',
            Schedule_Type_Limits_Name="Any Number",
            Field_1='Through: 12/31',
            Field_2='For: AllDays',
            Field_3=f'Until: 24:00, {value}'
        )

# Si todos los thermostats tienen un control de temperatura, pero no tiene un control de thermal comfort:
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
            Thermal_Comfort_Control_1_Object_Type='ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint',
            Thermal_Comfort_Control_1_Name=f'Fanger Setpoint {zone_name}'
        )

        building.newidfobject(
            key='ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint',
            Name=f'Fanger Setpoint {zone_name}',
            Fanger_Thermal_Comfort_Heating_Schedule_Name=f'Fanger Heating Setpoint {zone_name}',
            Fanger_Thermal_Comfort_Cooling_Schedule_Name=f'Fanger Cooling Setpoint {zone_name}',
        )
        for obj_type in ['ZoneControl:Thermostat', 'ThermostatSetpoint:DualSetpoint']:
            # building.removeidfobject(building.idfobjects[obj_type][-1])
            for i in range(len(building.idfobjects[obj_type])):
                first_object = building.idfobjects[obj_type][-1]
                building.removeidfobject(first_object)

# Si hay mezcla de termostatos de temperatura y confort térmico:
elif len(instance['ZoneControl:Thermostat:ThermalComfort']) > 0:
    # tc_obj_zones = [i['Zone_or_ZoneList_Name'] for i in instance['ZoneControl:Thermostat:ThermalComfort']]
    zc_ts_tc_objs = [i for i in building.idfobjects['ZoneControl:Thermostat:ThermalComfort']]
    # zc_ts_tc_objs_old_names = [i.Name for i in building.idfobjects['ZoneControl:Thermostat:ThermalComfort']]
    zc_ts_tc_objs_dict_names = {}
    # for i in range(len(instance['ZoneControl:Thermostat:ThermalComfort'])):
    for ob in zc_ts_tc_objs:
        temp_dict = {'old_name': ob.Name}

        zone_name = ob.Zone_or_ZoneList_Name
        ob.Name = f'Thermostat Setpoint Dual Setpoint {zone_name}'
        ob.Thermal_Comfort_Control_1_Object_Type = 'ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint'
        ob.Thermal_Comfort_Control_1_Name = f'Fanger Setpoint {zone_name}'

        temp_dict.update({'new_name': ob.Name})
        zc_ts_tc_objs_dict_names.update({zone_name: temp_dict})

    # zc_ts_tc_objs_new_names = [i.Name for i in building.idfobjects['ZoneControl:Thermostat:ThermalComfort']]
    thsp_tc_objs = [i for i in building.idfobjects['ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint']]
    for ob in thsp_tc_objs:
        for zone_name, temp_dict in zc_ts_tc_objs_dict_names.items():
            if temp_dict['old_name'] == ob.Name:
                ob.Name = temp_dict['new_name']
                ob.Fanger_Thermal_Comfort_Heating_Schedule_Name = f'Fanger Heating Setpoint {zone_name}'
                ob.Fanger_Thermal_Comfort_Cooling_Schedule_Name = f'Fanger Cooling Setpoint {zone_name}'

instance_after = inspect_thermostat_objects(idf=building)
schs = [i for i in building.idfobjects['Schedule:compact'] if 'Fanger' in i.Name]

building.savecopy('TestModel_TestResidentialUnit_v01_VRF_2_with_tc_objs_renamed.idf')