from accim.utils import get_available_fields
from besos import eppy_funcs as ef

# building = ef.get_building("TestModel_TestResidentialUnit_v01_VRF_2.idf")
building = ef.get_building('TestModel_V940_VRFsystem_working.idf')
# fields = get_available_fields(building, "ThermostatSetpoint:ThermalComfort:Fanger:DualSetpoint")
fields = get_available_fields(building, "THERMOSTATSETPOINT:THERMALCOMFORT:FANGER:DUALSETPOINT", separator="_")
fields