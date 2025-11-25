import pandas as pd
import matplotlib.pyplot as plt
from eppy.modeleditor import IDF
# import accim.sim.apmv_setpoints_wip as apmv
import accim.sim.apmv_setpoints as apmv

import besos.eppy_funcs as ef


# iddfile = 'C:\EnergyPlusV25-1-0\Energy+.idd'
iddfile = 'C:\EnergyPlusV9-4-0\Energy+.idd'

IDF.setiddname(iddfile)

idfname = 'TestModel_onlyGeometryForVRFsystem_2zones_CalcVent_V940.idf'
epwfile = "Seville.epw"

# idf = IDF(idfname, epwfile)
idf = ef.get_building(idfname)

apmv.add_vrf_system(building=idf)
apmv.set_zones_always_occupied(building=idf)

idf.saveas('TestModel_V940_VRFsystem.idf')
##
args_df = apmv.generate_df_from_args(building=idf)



idf_pmv = apmv.apply_apmv_setpoints(
    building=idf,
    adap_coeff_cooling=0,
    adap_coeff_heating=0,
)
idf_pmv.epw = epwfile
idf_pmv.run(output_directory='sim_results_pmv')

##
# import besos.eppy_funcs as ef
#
# idf = ef.get_building('TestModel_V940_VRFsystem_mod_v02.idf')
# epwfile = "Seville.epw"
# idf.epw = epwfile
# idf.run(output_directory='sim_results_pmv_mod')
