from accim.utils import read_eso_using_readvarseso

# Cargar datos
data = read_eso_using_readvarseso("eplusout.eso")
df_hourly = data['data']['Hourly']

# 1. Ver la estructura (Area, Variable, Units)
print(df_hourly.columns)

# 2. Obtener todas las variables de una Zona/Espacio específico
# Ejemplo: Todo lo de "SPACE 1-1"
df_space1 = df_hourly.xs('SPACE 1 - 1 189.1-2009 - OFFICE - OPENOFFICE - CZ4-8 PEOPLE', axis=1, level='Area')
print(df_space1.head())

# 3. Obtener una variable específica para TODAS las zonas
# Ejemplo: "Zone Air Temperature" de todo el edificio
temps = df_hourly.xs('Zone Air Temperature', axis=1, level='Variable')
print(temps.head())

# 4. Filtrar por unidades
# Ejemplo: Todas las columnas que sean watios [W]
power_cols = df_hourly.xs('W', axis=1, level='Units')


##
from read_eso_file_func_v05 import read_eso_using_readvarseso

# Llamada
results = read_eso_using_readvarseso("eplusout.eso")

# Acceder a datos
df_hourly = results['data']['Hourly']

# Acceder a metadata (tabla resumen)
meta_hourly = results['metadata']['Hourly']
print(meta_hourly)