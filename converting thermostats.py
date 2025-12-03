from accim.utils import convert_standard_to_comfort_thermostats
import besos.eppy_funcs as ef

building = ef.get_building("TestModel_V940_VRFsystem_thermostat_to_convert.idf")
converted = convert_standard_to_comfort_thermostats(
    idf=building,
    pmv_heating_schedule_name='Heating Fanger comfort setpoint: Always -0.5',
    pmv_cooling_schedule_name='Cooling Fanger comfort setpoint: Always  0.1',
    comfort_control_type_schedule_name="Zone Comfort Control Type Sched",
)

