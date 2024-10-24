# %%
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import pyomo.environ as pyo
from load_data import get_load_data, get_gen_data, get_spot_prices_data

# %%
# Algumas configurações dos valores de carga, geração e armazenamento a serem carregados

load_max = 5e3
gen_max = 50e3
node_index = 45
N = 96

# Sistema de armazenamento de hidrogênio

h2_storage_size_kg = 4.0 # unidade em Kg
h2_storage_rate = 0.2
h2_storage_min_soc = 0.00 * h2_storage_size_kg
h2_storage_max_soc = 1.00 * h2_storage_size_kg

elec_storage_size_wh = 20.0e3 # unidade em wh
elec_storage_rate = 0.1
elec_storage_min_soc = 0.05 * elec_storage_size_wh
elec_storage_max_soc = 0.95 * elec_storage_size_wh

# Eficiencia das conversões
efi_elec_to_h2 = 0.5
efi_h2_to_elec = 0.5
efi_h2_storage_in = 0.9
efi_h2_storage_out = 0.9
efi_elec_in = 0.9
efi_elec_out = 0.9

# Taxa de conversão de H2 para Eletricidade
tx_elec_to_h2 = 55.62e3 # kWh / kg de H2


# inverso de tx_elec_to_h2 --> 1.79e-05
# referencia para tx_h2_to_elec --> 7.6e-5

# tx_h2_to_elec = 1.0 / tx_elec_to_h2 # kg de H2 / kWh
# tx_h2_to_elec = 0.076 * 1e-3 # kg / kWh * (1kwh/1000 wh)
tx_h2_to_elec = 20e-6

# Preço de comercialização do H2
h2_price = 5e6

# Capacidade máxima de potência elétrica do eletrolisador

max_elec_to_h2_power = 10e3

# Capacidade máxima de potência elétrica da usina térmica
max_gas_power = 5e3
max_h2_to_elec_power = max_gas_power * 0.25 * tx_h2_to_elec

# Minimum Up-Time
min_uptime = 6 * 4

# %%
time = np.arange(N)

load = get_load_data(node_index)[:96] * load_max
sload = np.sqrt(load.pload**2 + load.qload**2)
pv_gen = get_gen_data(node_index)[:96] * gen_max
spot_price = get_spot_prices_data(30)[:96]

# %%
model = pyo.ConcreteModel(name='H2V')

model.time_set = pyo.Set(initialize=time)

# Parâmetros de entrada
model.param_load = pyo.Param(model.time_set, initialize=load.pload.values, mutable=False)
model.param_pv_gen = pyo.Param(model.time_set, initialize=pv_gen.pgen.values, mutable=False)
model.param_spot_prices = pyo.Param(model.time_set, initialize=spot_price.Price, mutable=False)

# Parâmetros do módulo de armazenamento de eletricidade
model.max_elec_charge = pyo.Param(initialize=elec_storage_rate * elec_storage_size_wh)
model.max_elec_discharge = pyo.Param(initialize=elec_storage_rate * elec_storage_size_wh)
model.elec_storage_size = pyo.Param(initialize=elec_storage_size_wh)
model.elec_min_soc = pyo.Param(initialize=elec_storage_min_soc)
model.elec_max_soc = pyo.Param(initialize=elec_storage_max_soc)

# Parâmetros do módulo de armazenamento de H2
model.max_h2_charge = pyo.Param(initialize=h2_storage_rate * h2_storage_size_kg)
model.max_h2_discharge = pyo.Param(initialize=h2_storage_rate * h2_storage_size_kg)
model.h2_storage_size = pyo.Param(initialize=h2_storage_size_kg)
model.h2_min_soc = pyo.Param(initialize=h2_storage_min_soc)
model.h2_max_soc = pyo.Param(initialize=h2_storage_max_soc)

# Variáveis de compra/venda de energia
model.var_power_purchase = pyo.Var(model.time_set, domain=pyo.Reals)

# Variáveis de armazenamento de eletricidade
model.var_elec_charging = pyo.Var(time, within=pyo.Binary)
model.var_elec_discharging = pyo.Var(time, within=pyo.Binary)
model.var_elec_charge = pyo.Var(time,
                                initialize={i: j for i, j in zip(time, np.zeros(len(time)))},
                                domain=pyo.NonNegativeReals)
model.var_elec_discharge = pyo.Var(time,
                                   initialize={i: j for i, j in zip(time, np.zeros(len(time)))},
                                   domain=pyo.NonNegativeReals)
model.var_elec_soc = pyo.Var(time,
                             domain=pyo.NonNegativeReals,
                             bounds=(model.elec_min_soc, model.elec_max_soc))

# Variável de quantidade de eletricidade utilizada para produção de H2
model.var_elet_on_off = pyo.Var(time, within=pyo.Binary)

model.var_elec_to_h2_mass = pyo.Var(time,
                                    initialize={i: j for i, j in zip(time, np.zeros(len(time)))},
                                    domain=pyo.NonNegativeReals)

# Variável de quantidade de massa de H2 produzida pelo eletrolisador 
model.var_h2_mass_from_elet = pyo.Var(time,
                                      initialize={i: j for i, j in zip(time, np.zeros(len(time)))},
                                      domain=pyo.NonNegativeReals)

# Variável de quantidade de massa de H2 produzida pelo eletrolisador e destinada ao armazenamento
model.var_h2_mass_to_storage = pyo.Var(time,
                                       initialize={i: j for i, j in zip(time, np.zeros(len(time)))},
                                       domain=pyo.NonNegativeReals)

# Variável de quantidade de massa de H2 proveniente do armazenamento para ??
model.var_h2_mass_from_storage = pyo.Var(time,
                                         initialize={i: j for i, j in zip(time, np.zeros(len(time)))},
                                         domain=pyo.NonNegativeReals)

# Variável de quantidade de massa de H2 destinada à queima para produção de eletricidade
model.var_h2_mass_to_elec = pyo.Var(time,
                                       initialize={i: j for i, j in zip(time, np.zeros(len(time)))},
                                       domain=pyo.NonNegativeReals)

# Variável de quantidade de massa de H2 destinada para  comercialização direta
model.var_h2_mass_to_market = pyo.Var(time,
                                      initialize={i: j for i, j in zip(time, np.zeros(len(time)))},
                                      domain=pyo.NonNegativeReals)

model.var_gas_power_on_off = pyo.Var(time, domain=pyo.Binary)

model.var_gas_start_up = pyo.Var(time, domain=pyo.Binary)

model.var_gas_shut_down = pyo.Var(time, domain=pyo.Binary)

model.var_elec_from_gas = pyo.Var(time,
                                  initialize={i: j for i, j in zip(time, np.zeros(len(time)))},
                                  domain=pyo.NonNegativeReals)

# TODO: model.var_gn_mass_to_plant

# Variáveis de armazenamento de H2
model.var_h2_charging = pyo.Var(time, within=pyo.Binary)
model.var_h2_discharging = pyo.Var(time, within=pyo.Binary)
model.var_h2_charge = pyo.Var(time,
                              initialize={i: j for i, j in zip(time, np.zeros(len(time)))},
                              domain=pyo.NonNegativeReals)
model.var_h2_discharge = pyo.Var(time,
                                 initialize={i: j for i, j in zip(time, np.zeros(len(time)))},
                                 domain=pyo.NonNegativeReals)
model.var_h2_soc = pyo.Var(time,
                           domain=pyo.NonNegativeReals,
                           bounds=(model.h2_min_soc, model.h2_max_soc))


# %%
# Restrição de conversão Eletricidade -> H2

def max_eletroliser_power(model, t):
    return model.var_elec_to_h2_mass[t] == max_elec_to_h2_power * model.var_elet_on_off[t]

model.max_eletroliser_power_constraint = pyo.Constraint(time, rule=max_eletroliser_power)

def elec_to_h2_constraint(model, t):
    return (model.var_h2_mass_from_elet[t] == 1.0 / tx_elec_to_h2 * model.var_elec_to_h2_mass[t] * 0.25)

model.elec_to_h2_constraint = pyo.Constraint(time, rule=elec_to_h2_constraint)

# Restrição de conversão H2 -> Eletricidade
def max_gas_power(model, t):
    return model.var_h2_mass_to_elec[t] == max_h2_to_elec_power * model.var_gas_power_on_off[t]

model.max_gas_power_constraint = pyo.Constraint(time, rule=max_gas_power)

# Restrição Liga-Desliga ao mesmo tempo
def start_up_shut_down_constraint(model, t):
    return model.var_gas_start_up[t] + model.var_gas_shut_down[t] <= 1

model.start_up_shut_down_constraint = pyo.Constraint(time, rule=start_up_shut_down_constraint)

# Restrição de causalidade entre estado da usina (ligado/desligado) e 
# instante de ligamento e instante de deligamento
def state_startup_shutdown(model, t):
    return model.var_gas_start_up[t] - model.var_gas_shut_down[t] == model.var_gas_power_on_off[t] - model.var_gas_power_on_off[t-1]
model.state_startup_shutdown_constraint = pyo.Constraint(time[1:], rule=state_startup_shutdown)

# Restrição de Tempo mínimo de funcionamento da usina
model.min_time_work_power_plant_constraint = pyo.ConstraintList()
time_window = np.arange(1, len(time) - min_uptime + 1)
for k in time_window:
    states = [model.var_gas_power_on_off[i] for i in range(k, k + min_uptime - 1)]
    model.min_time_work_power_plant_constraint.add(sum(states) >= min_uptime * model.var_gas_start_up[k])

# Restrição de Tempo mínimo de funcionamento da usina para a última janela de tempo 
model.last_min_time_work_power_plant_constraint = pyo.ConstraintList()
last_time_window = np.arange(len(time) - min_uptime + 2, len(time))
for k in last_time_window:
    states = [model.var_gas_power_on_off[i] - model.var_gas_start_up[k] for i in range(k, len(time))]
    model.last_min_time_work_power_plant_constraint.add(sum(states) >= 0.0)


def h2_to_elec_constraint(model, t):
    return (model.var_elec_from_gas[t] == (1.0 / tx_h2_to_elec) * model.var_h2_mass_to_elec[t] * (1.0/0.25))

model.h2_to_elec_constraint = pyo.Constraint(time, rule=h2_to_elec_constraint)

# conexão eletrolisador com armazenamento de H2
def h2_mass_to_storage_constraint(model, t):
    return model.var_h2_charge[t] == model.var_h2_mass_to_storage[t]

model.h2_mass_to_storage_constraint = pyo.Constraint(time, rule=h2_mass_to_storage_constraint)

# conexão armazenamento de H2 com plata de geração e mercado de H2
def h2_mass_from_storage_constraint(model, t):
    return model.var_h2_discharge[t] == model.var_h2_mass_from_storage[t]

model.h2_mass_from_storage_constraint = pyo.Constraint(time, rule=h2_mass_from_storage_constraint)

# Restrição de Balanço de Potência Elétrica
def elec_power_balance_constraint(model, t):
    return (model.param_pv_gen[t] + model.var_elec_from_gas[t] + model.var_elec_discharge[t] + model.var_power_purchase[t] == model.var_elec_to_h2_mass[t] + model.param_load[t] + model.var_elec_charge[t])

model.elec_power_balance_constraint = pyo.Constraint(time, rule=elec_power_balance_constraint)

# Restrição de Balanço de Gás 1: Saída do Eletrolisador
def h2_mass_balance_constraint_1(model, t):
    return (model.var_h2_mass_to_storage[t] == model.var_h2_mass_from_elet[t])

model.h2_mass_balance_constraint_1 = pyo.Constraint(time, rule=h2_mass_balance_constraint_1)

# Restrição de Balanço de Gás 2: Saída do tanque de Armazenamento
def h2_mass_balance_constraint_2(model, t):
    return (model.var_h2_mass_from_storage[t] == model.var_h2_mass_to_elec[t] + model.var_h2_mass_to_market[t])

model.h2_mass_balance_constraint_2 = pyo.Constraint(time, rule=h2_mass_balance_constraint_2)

# %%
# Restrições de Armazenamento de Eletricidade

# restrição que impossibilita a bateria de carregar e descarregar ao mesmo tempo
def charging_discharging_elec_constraint(model, t):
    return model.var_elec_charging[t] + model.var_elec_discharging[t] <= 1

model.charge_discharge_elec_constraint = pyo.Constraint(time, rule=charging_discharging_elec_constraint)

# def charging_discharging_energy_constraint(model, t):
#     return model.var_elec_charge[t] * model.var_elec_discharge[t] == 0.0

# model.charge_discharge_energy_constraint = pyo.Constraint(time, rule=charging_discharging_energy_constraint)

####

# restrição de potência máxima de carga 
def max_charge_rate_constraint(model, t):
    return model.var_elec_charge[t] <= model.max_elec_charge

model.max_charge_rate_constraint = pyo.Constraint(time, rule=max_charge_rate_constraint)

####

# restrição de potência máxima de descarga
def max_discharge_rate_constraint(model, t):
    return model.var_elec_discharge[t] <= model.max_elec_discharge

model.max_discharge_rate_constraint = pyo.Constraint(time, rule=max_discharge_rate_constraint)

####

# restrição de carga inicial da bateria
model.init_soc_constraint = pyo.Constraint(expr=model.var_elec_soc[0] == 0.1 * elec_storage_size_wh)

####

# restrição que modela o armazenamento gradual do dispositivo
model.soc_memory_constraint = pyo.ConstraintList()
for t_m, t in zip(time[:-1], time[1:]):
    rule_ = (model.var_elec_soc[t] == model.var_elec_soc[t_m] + (model.var_elec_charge[t_m] - model.var_elec_discharge[t_m]) * 0.25)
    model.soc_memory_constraint.add(rule_)

# %%
# Restrições de Armazenamento de H2

# restrição que impossibilita o tanque de carregar e descarregar ao mesmo tempo
def charging_discharging_h2_constraint(model, t):
    return model.var_h2_charging[t] + model.var_h2_discharging[t] <= 1

model.charge_discharge_h2_constraint = pyo.Constraint(time, rule=charging_discharging_h2_constraint)

# def charging_discharging_h2_constraint(model, t):
#     return model.var_h2_charge[t] * model.var_h2_discharge[t] == 0.0

# model.charge_discharge_h2_constraint = pyo.Constraint(time, rule=charging_discharging_h2_constraint)

####

# restrição de potência máxima de carga 
def max_h2_charge_rate_constraint(model, t):
    return model.var_h2_charge[t] <= model.max_h2_charge

model.max_h2_charge_rate_constraint = pyo.Constraint(time, rule=max_h2_charge_rate_constraint)

####

# restrição de potência máxima de descarga
def max_h2_discharge_rate_constraint(model, t):
    return model.var_h2_discharge[t] <= model.max_h2_discharge

model.max_h2_discharge_rate_constraint = pyo.Constraint(time, rule=max_h2_discharge_rate_constraint)

####

# restrição de carga inicial do armazenamento de h2
model.init_h2_soc_constraint = pyo.Constraint(expr=model.var_h2_soc[0] == 0.01 * h2_storage_size_kg)

####

# restrição que modela o armazenamento gradual do dispositivo
model.h2_soc_memory_constraint = pyo.ConstraintList()
for t_m, t in zip(time[:-1], time[1:]):
    rule_ = (model.var_h2_soc[t] == model.var_h2_soc[t_m] + (model.var_h2_charge[t_m] - model.var_h2_discharge[t_m]) * 0.25)
    model.h2_soc_memory_constraint.add(rule_)

# %%
# Função Objetivo
def obj_function(model):
    y = list() 
    for t in time:
        aux = model.param_spot_prices[t] * (-model.var_power_purchase[t]) + h2_price * (model.var_h2_mass_to_market[t])
        y.append(aux)
    return sum(y)
model.cost_function = pyo.Objective(rule=obj_function, sense=pyo.maximize)

# %%
# ----------------------------------
# Solving the model
# ----------------------------------
solver = pyo.SolverFactory('cplex')
results = solver.solve(model)
if (results.solver.status == pyo.SolverStatus.ok) and (results.solver.termination_condition == pyo.TerminationCondition.optimal):
    print ("This is feasible and optimal")
elif results.solver.termination_condition == pyo.TerminationCondition.infeasible:
    print ("This is infeasible")
else:
    # something else is wrong
    print (str(results.solver))

# %%
# Análise de Resultados
pyo.value(model.cost_function)

# %%
elec_storage_discharge = np.array([i.value for i in model.var_elec_discharge.values()])
# %%
elec_storage_charge = np.array([i.value for i in model.var_elec_charge.values()])
# %%
elec_to_h2_mass = np.array([i.value for i in model.var_elec_to_h2_mass.values()])
# %%
elec_from_gas = np.array([i.value for i in model.var_elec_from_gas.values()])
# %%
power_to_purchase = np.array([i.value for i in model.var_power_purchase.values()])
power_buy= np.array([i if i > 0.0 else 0.0 for i in power_to_purchase])
power_sell = np.array([-i if i < 0.0 else 0.0 for i in power_to_purchase])
plt.bar(time, power_to_purchase)
# %%
soc_elec = np.array([i.value for i in model.var_elec_soc.values()])
plt.bar(time, soc_elec)
# %%
soc_h2 = np.array([i.value for i in model.var_h2_soc.values()])
plt.bar(time, soc_h2)
# %%
power_plant = np.array([i.value for i in model.var_elec_from_gas.values()])
plt.bar(time, power_plant)
# %%
h2_to_market = np.array([i.value for i in model.var_h2_mass_to_market.values()])
plt.bar(time, h2_to_market)

# %%
plt.bar(time, load.pload.values)
plt.bar(time, elec_storage_charge, bottom=load.pload.values)
plt.bar(time, elec_to_h2_mass, bottom=load.pload.values+elec_storage_charge)
plt.bar(time, power_sell, bottom=load.pload.values+elec_storage_charge+elec_to_h2_mass)
plt.bar(time, -pv_gen.pgen.values)
plt.bar(time, -elec_storage_discharge, bottom=-pv_gen.pgen.values)
plt.bar(time, -elec_from_gas, bottom=-elec_storage_discharge-pv_gen.pgen.values)
plt.bar(time, -power_buy, bottom=-elec_storage_discharge-pv_gen.pgen.values-elec_from_gas)
plt.legend(['load', 'storage-charge', 'power-2-h2', 'power-sell', 'pv-gen', 'storage-discharge', 'h2-2-power', 'power-buy'])
plt.grid(True)
# %%