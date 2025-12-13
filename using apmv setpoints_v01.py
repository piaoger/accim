import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from besos import eppy_funcs as ef
from besos import eplus_funcs as ep
import accim.sim.apmv_setpoints_wip_4_3_testing as apmv
wip = '_wip_4_2'
import os

# Visualization setup
plt.rcParams['figure.figsize'] = [15, 6]
sns.set_style("whitegrid")

# Define file paths
# idfname = 'TestModel_onlyGeometryForVRFsystem_2zones_CalcVent_V940.idf'
# idfname = 'TestModel_ALJARAFE CENTER_mod.idf'# not working yet, see zonename from apmv.get_available_target_names(building=building_pmv)
idfname = 'TestModel_ALJARAFE CENTER_mod_zonelist.idf'


# idfname = 'TestModel_TestResidentialUnit_v01_VRF_2_air-veloc-mod.idf' # only spacelist, no zonelist; not working yet
# idfname = 'TestModel_TestResidentialUnit_v01_VRF_2_air-veloc-mod_zonelist-and-spacelist.idf'
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



##
csp_dict = {'Floor_1 Residential Living Occupants': 0.6, 'Floor_2 Residential Living Occupants': 0.3}
# Apply setpoints with coefficients set to 0
building_with_pmv = apmv.apply_apmv_setpoints(
    building=building_pmv,
    adap_coeff_cooling=0,
    adap_coeff_heating=0,
    pmv_cooling_sp=csp_dict,
    # pmv_cooling_sp=0.5,
    pmv_heating_sp=-0.5,
    cooling_season_start='01/04',  # April 1st
    cooling_season_end='01/10',    # October 1st
    # verboseMode=True,
    # tolerance_cooling_sp_cooling_season=-0.15,
    # tolerance_cooling_sp_heating_season=-0.15
)

saveas_name = idfname.split('.idf')[0] + '_debugging'+wip+'.idf'
building_with_pmv.savecopy(saveas_name)

# building_with_pmv.savecopy('TestModel_TestResidentialUnit_v01_VRF_2_with_EMS.idf')

## Run simulation

# output_dir_base = 'sim_results_pmv_wip_always_occupied_air-veloc-mod_unified_zonelist'
# output_dir_base = 'sim_results_pmv_wip_aljarafe_zonelist'
output_dir_base = 'results_'+idfname.split('.idf')[0]+wip
print(f"Running baseline simulation in: {output_dir_base}...")

ep.run_building(
    building=building_with_pmv,
    out_dir=output_dir_base,
    epw=epwfile
)
print("Baseline simulation finished.")


## Load Baseline results
# results_path_base = os.path.join(output_dir_base, 'eplusout.csv')
# df_base = pd.read_csv(results_path_base)
# df_base['Hour'] = df_base.index
#
# # Get columns
#
# z1_apmv_b, z1_cool_b, z1_heat_b = get_columns(df_base, 'Block1_Zone2')
#
# # Visualize Baseline
# plt.figure()
# sns.lineplot(data=df_base, x='Hour', y=z1_apmv_b, color='gray', linewidth=0.5, label='PMV (Lambda=0)')
# sns.lineplot(data=df_base, x='Hour', y=z1_cool_b, color='blue', linestyle='--', label='Cooling SP (0.5)')
# sns.lineplot(data=df_base, x='Hour', y=z1_heat_b, color='red', linestyle='--', label='Heating SP (-0.5)')
#
# plt.title('Zone 1: Baseline (Standard Fanger)')
# plt.ylabel('PMV / aPMV')
# plt.xlabel('Hours of the Year')
# plt.legend(loc='upper center', bbox_to_anchor=(0.5, -0.12), frameon=True)
# plt.show()

##
# import besos.eppy_funcs as ef
# import besos.eplus_funcs as ep
# epwfile = "Seville.epw"
#
# # building = ef.get_building("TestModel_TestResidentialUnit_v01_VRF_2_air-veloc-mod_zonelist-and-spacelist.idf")
# building = ef.get_building("TestModel_ALJARAFE CENTER_mod_zonelist.idf")
#
#
# # output_dir_base = 'sim_results_pmv_wip_always_occupied_air-veloc-mod_unified_zonelist'
# output_dir_base = 'sim_results_pmv_wip_aljarafe_zonelist'
# print(f"Running baseline simulation in: {output_dir_base}...")
#
# ep.run_building(
#     building=building,
#     out_dir=output_dir_base,
#     epw=epwfile
# )
# print("Baseline simulation finished.")
