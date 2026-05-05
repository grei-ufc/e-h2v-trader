import pyomo.environ as pyo
import mpisppy.utils.sputils as sputils
from mpisppy.opt.ef import ExtensiveForm
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import os


def carregar_pld_12m(caminho_excel, n_periodos=1440):
    """
    Carrega PLD, interpola para 15min e retorna colunas ['data', 'pld'].
    """
    try:
        df = pd.read_excel(caminho_excel)
        
        # Força a renomeação para o que o seu notebook espera
        # Assume-se: Coluna 0 = Data/Hora, Coluna 1 = Preço
        df.columns = ['data', 'pld']
        
        df['data'] = pd.to_datetime(df['data'])
        df['pld'] = pd.to_numeric(df['pld'], errors='coerce')
        
        # Define a data como índice para interpolar
        df.set_index('data', inplace=True)
        df_15min = df.resample('15min').interpolate(method='linear')
        
        # Ajusta para o horizonte de n_periodos (15 dias)
        current_len = len(df_15min)
        if current_len < n_periodos:
            repeats = int(np.ceil(n_periodos / current_len))
            new_values = np.tile(df_15min['pld'].values, repeats)[:n_periodos]
            
            # Cria novo índice de tempo começando do início do arquivo
            new_index = pd.date_range(start=df_15min.index[0], periods=n_periodos, freq='15min')
            df_result = pd.DataFrame({'pld': new_values}, index=new_index)
        else:
            df_result = df_15min.iloc[:n_periodos].copy()
        
        # IMPORTANTE: Reseta o índice para que 'data' volte a ser uma coluna
        df_result = df_result.reset_index().rename(columns={'index': 'data'})
        
        return df_result

    except Exception as e:
        raise RuntimeError(f"Erro ao carregar PLD 12m: {str(e)}")


def gerar_perfis_realistas(N, intervalo_horas, pot_solar_max_w, pot_eolica_max_w, pot_carga_max_w):
    """
    Gera perfis sintéticos de solar, eólica e carga para o horizonte total N.
    Esta função será usada apenas para a carga, a menos que dados reais de carga sejam fornecidos.
    """
    # CORREÇÃO: O vetor de horas deve cobrir todo o horizonte N (15 dias)
    # N * intervalo_horas (1440 * 0.25) resulta em 360 horas totais.
    horas = np.arange(0, N * intervalo_horas, intervalo_horas)

    # Perfil Solar Unitário
    # O seno garante a repetição diária (ciclo de 24h) ao longo dos 15 dias.
    perfil_solar_unitario = np.maximum(0, np.sin(np.pi * (horas - 6) / 12))**1.5
    solar_gen_w = perfil_solar_unitario * pot_solar_max_w

    # Perfil Eólico Unitário
    # Agora o ruído aleatório np.random.rand(N) tem o mesmo tamanho (1440) que o vetor 'horas'.
    perfil_eolico_unitario = (0.5 + 
                              0.2 * np.sin(np.pi * horas / 6) + 
                              0.3 * np.cos(np.pi * horas / 12 + np.pi/4) + 
                              0.1 * np.random.rand(N))
    
    # Garante que os valores fiquem entre 0 e 1
    perfil_eolico_unitario = np.clip(perfil_eolico_unitario, 0, 1)
    eolica_gen_w = perfil_eolico_unitario * pot_eolica_max_w

    # Perfil de Carga Unitário
    # O cosseno e a exponencial criam o comportamento de picos de consumo diários.
    perfil_carga_unitario = (0.55 - 
                             0.25 * np.cos(2 * np.pi * (horas - 4) / 24) + 
                             0.4 * np.exp(-0.5 * ((horas - 15) / 3.5)**2))
    
    carga_w = perfil_carga_unitario * pot_carga_max_w

    # Retorna as listas convertidas para o formato esperado pelo modelo
    return solar_gen_w.tolist(), eolica_gen_w.tolist(), carga_w.tolist()


def carregar_geracao_data(arquivo, N_intervals=1440, unit_conversion_factor=1e6, sheet_name=0):
    """
    Carrega dados de geração, ignora colunas de tempo/texto e replica para N_intervals.
    """
    if not os.path.exists(arquivo):
        raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")

    try:
        # Lê o arquivo Excel completo
        df = pd.read_excel(arquivo, sheet_name=sheet_name, header=None)
        
        # Se houver mais de uma coluna, assume que a geração está na segunda (índice 1)
        # A primeira coluna (índice 0) geralmente contém os horários que causaram o erro.
        coluna_alvo = 1 if df.shape[1] > 1 else 0
        
        # Extrai a coluna e converte para numérico
        # O 'errors=coerce' transforma horários (datetime.time) e textos em NaN
        dados_numericos = pd.to_numeric(df.iloc[:, coluna_alvo], errors='coerce')
        
        # Remove os valores nulos (cabeçalhos, horários ou linhas vazias)
        data = dados_numericos.dropna().values

        if len(data) == 0:
            raise ValueError(f"O arquivo {arquivo} não contém dados numéricos válidos na coluna {coluna_alvo}.")

        # Aplica o fator de conversão (ex: MW para W)
        data = data * unit_conversion_factor

        # Lógica de repetição (tile) para atingir exatamente N_intervals (1440 pontos)
        n_repeats = int(np.ceil(N_intervals / len(data)))
        perfil = np.tile(data, n_repeats)[:N_intervals]

        return perfil

    except Exception as e:
        raise ValueError(f"Erro ao processar arquivo de geração '{arquivo}': {str(e)}")

def load_and_process_scenario_data(N,
                                   INTERVALO_HORAS,
                                   LOAD_MAX_W,
                                   GEN_MAX_W,
                                   pld_data,
                                   solar_mean_profile,
                                   wind_mean_profile,
                                   fixed_h2_price=25.0,
                                   fixed_ammonia_price=4.27):
    """
    Carrega e processa os dados para os diferentes cenários de otimização.
    A geração solar e eólica utiliza sempre o perfil de média agregada.
    A variabilidade dos cenários é definida pelos dados de PLD.
    """
    print(f"--- Construindo perfis: Preço H₂ (Venda) = R$ {fixed_h2_price:.2f}/kg | Preço Amônia (Venda) = R$ {fixed_ammonia_price:.2f}/kg ---")
    
    # A carga (load_w) ainda será gerada sinteticamente, pois não há dados de carga real fornecidos.
    _, _, load_w = gerar_perfis_realistas(N, INTERVALO_HORAS, GEN_MAX_W, GEN_MAX_W, LOAD_MAX_W)

    profiles = {
        'optimal': {
            'wind_gen_w': wind_mean_profile,  # Cenário 'optimal' usa geração eólica média agregada
            'solar_gen_w': solar_mean_profile  # Cenário 'optimal' usa geração solar média agregada
        },
        'good': {
            'wind_gen_w': wind_mean_profile, # Cenário 'good' usa geração eólica média agregada
            'solar_gen_w': solar_mean_profile # Cenário 'good' usa geração solar média agregada
        },
        'bad': {
            'wind_gen_w': wind_mean_profile,  # Cenário 'bad' usa geração eólica média agregada
            'solar_gen_w': solar_mean_profile  # Cenário 'bad' usa geração solar média agregada
        }
    }
    
    # Atribui os preços de PLD aos cenários
    profiles['optimal']['spot_prices_mwh'] = pld_data['low']  # PLD baixo para cenário 'optimal' (custo de compra menor)
    profiles['good']['spot_prices_mwh'] = pld_data['mean']   # PLD médio para cenário 'good'
    profiles['bad']['spot_prices_mwh'] = pld_data['high']    # PLD alto para cenário 'bad' (custo de compra maior)

    h2_price_per_kg_venda = [fixed_h2_price] * N
    ammonia_price_per_kg_venda = [fixed_ammonia_price] * N
    
    for p_name in profiles:
        profiles[p_name]['load_w'] = load_w # A carga é a mesma para todos os cenários por enquanto
        profiles[p_name]['h2_price_venda'] = h2_price_per_kg_venda
        profiles[p_name]['ammonia_price_venda'] = ammonia_price_per_kg_venda
    return profiles


def plot_scenario_results(TIME_HORIZON, s_block, s_name, initial_soc_dict, fixed_h2_price, fixed_ammonia_price, 
                          AMMONIA_PLANT_ELEC_CONSUMPTION_WH_PER_KG, INTERVALO_HORAS, N,
                          h2_max_soc_kg, h2_min_soc_kg, ammonia_max_soc_kg, ammonia_min_soc_kg,
                          TX_H2_TO_AMMONIA_KG_PER_KG):
    
    import matplotlib.pyplot as plt
    import numpy as np
    import pyomo.environ as pyo

    # --- 1. EXTRAÇÃO DE RESULTADOS ---
    # Potências (Convertidas para MW)
    res_solar = np.array([pyo.value(s_block.p_solar[t]) for t in TIME_HORIZON]) / 1e6
    res_wind = np.array([pyo.value(s_block.p_wind[t]) for t in TIME_HORIZON]) / 1e6
    res_load = np.array([pyo.value(s_block.p_load[t]) for t in TIME_HORIZON]) / 1e6
    res_grid_buy = np.array([pyo.value(s_block.GRID_BUY_POWER[t]) for t in TIME_HORIZON]) / 1e6
    res_grid_sell = np.array([pyo.value(s_block.GRID_SELL_POWER[t]) for t in TIME_HORIZON]) / 1e6
    
    # Eletrolisador (Soma das variáveis lineares)
    res_electrolyzer_consumption = np.array([pyo.value(s_block.P_PROD[t] + s_block.P_START[t]) for t in TIME_HORIZON]) / 1e6
    
    # Fuel Cell (Nova Geração de Energia)
    res_fc_gen = np.array([pyo.value(s_block.P_FC_GEN[t]) for t in TIME_HORIZON]) / 1e6
    
    # BESS e Preços
    res_bess_soc = np.array([pyo.value(s_block.BESS_SOC[t]) for t in TIME_HORIZON]) / 1e6
    res_elec_price = np.array([pyo.value(s_block.price[t]) for t in TIME_HORIZON]) * 1e6 # R$/MWh
    
    # Estoques e Amônia
    res_h2_soc = np.array([pyo.value(s_block.H2_STORAGE_SOC[t]) for t in TIME_HORIZON])
    res_ammonia_soc = np.array([pyo.value(s_block.AMMONIA_STORAGE_SOC[t]) for t in TIME_HORIZON])
    res_ammonia_produced = np.array([pyo.value(s_block.AMMONIA_PRODUCED_MASS[t]) for t in TIME_HORIZON])
    res_ammonia_plant_elec_mw = (res_ammonia_produced * AMMONIA_PLANT_ELEC_CONSUMPTION_WH_PER_KG / INTERVALO_HORAS) / 1e6

    # --- 2. CONFIGURAÇÃO DO EIXO X (DIAS) ---
    passos_por_hora = int(1 / INTERVALO_HORAS)
    x_ticks = np.arange(0, len(TIME_HORIZON), passos_por_hora * 24)
    x_labels = [f"Dia {int(t/(passos_por_hora*24)) + 1}" for t in x_ticks]

    # --- 3. PLOTAGEM ---
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 18), sharex=True)
    fig.suptitle(f'Resultados da Operação com Fuel Cell - Cenário: {s_name.upper()}', fontsize=16, fontweight='bold')

    # PAINEL 1: Balanço de Potência (MW)
    ax1.plot(TIME_HORIZON, res_solar, label='Geração Solar', color='gold', alpha=0.7)
    ax1.plot(TIME_HORIZON, res_wind, label='Geração Eólica', color='skyblue', alpha=0.7)
    ax1.plot(TIME_HORIZON, res_grid_buy, label='Compra da Rede', color='orange', linestyle='--')
    ax1.plot(TIME_HORIZON, res_fc_gen, label='Geração Fuel Cell', color='lime', linewidth=2) # DESTAQUE FC
    
    ax1.plot(TIME_HORIZON, -res_load, label='Carga Industrial', color='red', linestyle=':')
    ax1.plot(TIME_HORIZON, -res_electrolyzer_consumption, label='Consumo Eletrolisador', color='magenta')
    ax1.plot(TIME_HORIZON, -res_ammonia_plant_elec_mw, label='Consumo Planta Amônia', color='brown')
    ax1.plot(TIME_HORIZON, -res_grid_sell, label='Venda para Rede', color='navy')
    
    ax1.set_ylabel('Potência (MW)')
    ax1.axhline(0, color='black', lw=1)
    ax1.legend(loc='upper left', bbox_to_anchor=(1.01, 1))
    ax1.grid(True, alpha=0.3)

    # PAINEL 2: SOC BESS vs Preço da Energia (PLD)
    ax2.plot(TIME_HORIZON, res_bess_soc, color='purple', label='SOC BESS (MWh)')
    ax2_pld = ax2.twinx()
    ax2_pld.plot(TIME_HORIZON, res_elec_price, color='green', linestyle=':', label='PLD (R$/MWh)', alpha=0.6)
    ax2.set_ylabel('Energia no BESS (MWh)')
    ax2_pld.set_ylabel('Preço PLD (R$/MWh)')
    ax2.grid(True, alpha=0.3)
    
    lines, labels = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_pld.get_legend_handles_labels()
    ax2.legend(lines + lines2, labels + labels2, loc='upper left', bbox_to_anchor=(1.01, 1))

    # PAINEL 3: Estoques de Hidrogênio e Amônia (kg)
    ax3.plot(TIME_HORIZON, res_h2_soc, color='blue', label='Estoque H2 (kg)')
    ax3_am = ax3.twinx()
    ax3_am.plot(TIME_HORIZON, res_ammonia_soc, color='darkgreen', label='Estoque Amônia (kg)')
    
    # Linhas de limite de tanque
    ax3.axhline(y=h2_max_soc_kg, color='blue', ls='--', alpha=0.3)
    ax3_am.axhline(y=ammonia_max_soc_kg, color='darkgreen', ls='--', alpha=0.3)
    
    ax3.set_ylabel('Massa H2 (kg)')
    ax3_am.set_ylabel('Massa Amônia (kg)')
    ax3.set_xticks(x_ticks)
    ax3.set_xticklabels(x_labels, rotation=45)
    ax3.grid(True, alpha=0.3)
    
    lines3, labels3 = ax3.get_legend_handles_labels()
    lines4, labels4 = ax3_am.get_legend_handles_labels()
    ax3.legend(lines3 + lines4, labels3 + labels4, loc='upper left', bbox_to_anchor=(1.01, 1))

    plt.tight_layout()
    plt.show()