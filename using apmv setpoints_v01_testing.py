import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from besos import eppy_funcs as ef
from besos import eplus_funcs as ep
import accim.sim.apmv_setpoints_wip_4_4_testing as apmv
wip = '_wip_4_4'
import os

# Visualization setup
plt.rcParams['figure.figsize'] = [15, 6]
sns.set_style("whitegrid")

# Define file paths
# idfname = 'TestModel_onlyGeometryForVRFsystem_2zones_CalcVent_V940.idf'
# idfname = 'TestModel_ALJARAFE CENTER_mod.idf'# not working yet, see zonename from apmv.get_available_target_names(building=building_pmv)
# idfname = 'TestModel_ALJARAFE CENTER_mod_zonelist.idf'


# idfname = 'TestModel_TestResidentialUnit_v01_VRF_2_air-veloc-mod.idf' # only spacelist, no zonelist; not working yet
idfname = 'TestModel_TestResidentialUnit_v01_VRF_2_air-veloc-mod_zonelist-and-spacelist.idf'
epwfile = "Seville.epw"

# print(f"IDF File: {idfname}")
# print(f"EPW File: {epwfile}")

# Load the building model using BESOS
building = ef.get_building(idfname)

zones = apmv._resolve_targets(building=building)
print(zones)

# Ensure zones are always occupied for the demonstration
# apmv.set_zones_always_occupied(building=building)

# zones = [i.Zone_or_ZoneList_Name for i in building.idfobjects['people']]
# zones = [i.Zone_or_ZoneList_or_Space_or_SpaceList_Name for i in building.idfobjects['people']]


# 'Zone_or_ZoneList_or_Space_or_SpaceList_Name'
# print("Building loaded successfully.")
# print(f"Occupied zones found: {zones}")


# Helper function to find columns dynamically (used in both parts)
# def get_columns(df, zone_name_part):
#     # Find aPMV value column
#     apmv_col = [i for i in df.columns if 'EMS:aPMV' in i and zone_name_part in i and 'Setpoint' not in i][0]
#     # Find cooling setpoint column (no tolerance)
#     cool_sp_col = [i for i in df.columns if 'EMS:aPMV Cooling Setpoint No Tolerance' in i and zone_name_part in i][0]
#     # Find heating setpoint column (no tolerance)
#     heat_sp_col = [i for i in df.columns if 'EMS:aPMV Heating Setpoint No Tolerance' in i and zone_name_part in i][0]
#
#     return apmv_col, cool_sp_col, heat_sp_col

# Create a copy of the building for the baseline simulation
building_pmv = ef.get_building(idfname)
# apmv.add_vrf_system(building=building_pmv, SupplyAirTempInputMethod='temperature difference')
#Continuar aqui: re-simular con ocupación constante siempre ocupado
# apmv.set_zones_always_occupied(building=building_pmv)

# saveas_name = idfname.split('.idf')[0] + '_debugging.idf'
# building_pmv.saveas(saveas_name)

# zones = apmv.get_available_target_names(building=building_pmv)
# zone_dict = apmv.get_input_template_dictionary(building=building_pmv)
# zones