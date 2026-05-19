import pyomo.environ as pyo
import mpisppy.utils.sputils as sputils
from mpisppy.opt.ef import ExtensiveForm
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import os

import seaborn as sns
from matplotlib.gridspec import GridSpec


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

def load_and_process_scenario_data(N, INTERVALO_HORAS, LOAD_MAX_W, GEN_MAX_W, pld_data, solar_data, wind_data, fixed_h2_price=25.0, fixed_ammonia_price=4.27):
    """
    Monta os dicionários de perfis para cada cenário (optimal, good, bad).
    AGORA UTILIZA PERFIS SOLARES E EÓLICOS DIFERENCIADOS POR CENÁRIO.
    """
    _, _, carga_w = gerar_perfis_realistas(N, INTERVALO_HORAS, 0, 0, LOAD_MAX_W)
    
    h2_price_venda_profile = [fixed_h2_price] * N
    ammonia_price_venda_profile = [fixed_ammonia_price] * N
    
    profiles = {
        'optimal': {
            # Cenário Ótimo: PLD baixo, Solar alto, Eólico alto
            'spot_prices_mwh': pld_data['low'],
            'solar_gen_w': solar_data['high'],
            'wind_gen_w': wind_data['high'],
            'load_w': carga_w,
            'h2_price_venda': h2_price_venda_profile,
            'ammonia_price_venda': ammonia_price_venda_profile,
        },
        'good': {
            # Cenário Bom: PLD médio, Solar médio, Eólico médio
            'spot_prices_mwh': pld_data['mean'],
            'solar_gen_w': solar_data['mean'],
            'wind_gen_w': wind_data['mean'],
            'load_w': carga_w,
            'h2_price_venda': h2_price_venda_profile,
            'ammonia_price_venda': ammonia_price_venda_profile,
        },
        'bad': {
            # Cenário Ruim: PLD alto, Solar baixo, Eólico baixo
            'spot_prices_mwh': pld_data['high'],
            'solar_gen_w': solar_data['low'],
            'wind_gen_w': wind_data['low'],
            'load_w': carga_w,
            'h2_price_venda': h2_price_venda_profile,
            'ammonia_price_venda': ammonia_price_venda_profile,
        }
    }
    
    return profiles
        
"""
def load_and_process_scenario_data(N,
                                   INTERVALO_HORAS,
                                   LOAD_MAX_W,
                                   GEN_MAX_W,
                                   pld_data,
                                   solar_mean_profile,
                                   wind_mean_profile,
                                   fixed_h2_price=25.0,
                                   fixed_ammonia_price=4.27):

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
"""

def plot_scenario_results(TIME_HORIZON, s_block, s_name, initial_soc_dict, fixed_h2_price, fixed_ammonia_price, 
                          AMMONIA_PLANT_ELEC_CONSUMPTION_WH_PER_KG, INTERVALO_HORAS, N,
                          h2_max_soc_kg, h2_min_soc_kg, ammonia_max_soc_kg, ammonia_min_soc_kg,
                          TX_H2_TO_AMMONIA_KG_PER_KG):

    # --- Aplica um tema profissional para os gráficos ---
    sns.set_theme(style="whitegrid", palette="colorblind")
    plt.rcParams.update({'font.family': 'serif', 'font.size': 12})

    # --- 1. Extração e Preparação dos Dados ---
    data = {
        'Solar': np.array([pyo.value(s_block.p_solar[t]) for t in TIME_HORIZON]) / 1e6,
        'Eólica': np.array([pyo.value(s_block.p_wind[t]) for t in TIME_HORIZON]) / 1e6,
        'Compra da Rede': np.array([pyo.value(s_block.GRID_BUY_POWER[t]) for t in TIME_HORIZON]) / 1e6,
        'Fuel Cell': np.array([pyo.value(s_block.P_FC_GEN[t]) for t in TIME_HORIZON]) / 1e6,
        'Carga Industrial': -np.array([pyo.value(s_block.p_load[t]) for t in TIME_HORIZON]) / 1e6,
        'Eletrolisador': -np.array([pyo.value(s_block.P_PROD[t] + s_block.P_START[t]) for t in TIME_HORIZON]) / 1e6,
        'Planta de Amônia': -(np.array([pyo.value(s_block.AMMONIA_PRODUCED_MASS[t]) for t in TIME_HORIZON]) * AMMONIA_PLANT_ELEC_CONSUMPTION_WH_PER_KG / INTERVALO_HORAS) / 1e6,
        'Venda para Rede': -np.array([pyo.value(s_block.GRID_SELL_POWER[t]) for t in TIME_HORIZON]) / 1e6,
        'SOC BESS': np.array([pyo.value(s_block.BESS_SOC[t]) for t in TIME_HORIZON]) / 1e6,
        'PLD': np.array([pyo.value(s_block.price[t]) for t in TIME_HORIZON]) * 1e6,
        'Estoque H2': np.array([pyo.value(s_block.H2_STORAGE_SOC[t]) for t in TIME_HORIZON]),
        'Estoque Amônia': np.array([pyo.value(s_block.AMMONIA_STORAGE_SOC[t]) for t in TIME_HORIZON])
    }
    
    bess_dispatch = np.diff(data['SOC BESS'], prepend=data['SOC BESS'][0]) / INTERVALO_HORAS

    # --- 2. Criação da Figura com 'constrained_layout' ---
    # A mudança principal está aqui: ativamos o novo gerenciador de layout.
    fig = plt.figure(figsize=(18, 16), constrained_layout=True)
    
    gs = GridSpec(3, 1, figure=fig, height_ratios=[3, 2, 2], hspace=0.1)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    
    fig.suptitle(f'Análise Operacional do Cenário: {s_name.upper()}', fontsize=20, fontweight='bold')

    # --- 3. Painel 1: Despacho de Potência ---
    generation_sources = ['Solar', 'Eólica', 'Compra da Rede', 'Fuel Cell']
    consumption_sources = ['Carga Industrial', 'Eletrolisador', 'Planta de Amônia', 'Venda para Rede']
    df_power = pd.DataFrame({k: v for k, v in data.items() if k in generation_sources + consumption_sources})
    
    ax1.stackplot(TIME_HORIZON, df_power[generation_sources].T, labels=generation_sources, colors=sns.color_palette("Greens_d", len(generation_sources)))
    ax1.stackplot(TIME_HORIZON, df_power[consumption_sources].T, labels=consumption_sources, colors=sns.color_palette("Reds_d", len(consumption_sources)))
    ax1.set_ylabel('Potência (MW)', fontsize=14, fontweight='bold')
    ax1.axhline(0, color='black', lw=1.5, linestyle='--')
    plt.setp(ax1.get_xticklabels(), visible=False)
    ax1.grid(axis='y', linestyle=':', alpha=0.7)

    # --- 4. Painel 2: Armazenamento de Energia e Preços ---
    ax2.plot(TIME_HORIZON, data['SOC BESS'], color='purple', label='SOC BESS (MWh)', lw=2.5)
    ax2.fill_between(TIME_HORIZON, ax2.get_ylim()[0], ax2.get_ylim()[1], where=bess_dispatch > 0.01, facecolor='mediumseagreen', alpha=0.2, label='BESS Carregando')
    ax2.fill_between(TIME_HORIZON, ax2.get_ylim()[0], ax2.get_ylim()[1], where=bess_dispatch < -0.01, facecolor='lightcoral', alpha=0.2, label='BESS Descarregando')
    ax2.set_ylabel('Energia no BESS (MWh)', fontsize=14, fontweight='bold')
    plt.setp(ax2.get_xticklabels(), visible=False)
    
    ax2_pld = ax2.twinx()
    ax2_pld.plot(TIME_HORIZON, data['PLD'], color='#333333', linestyle=':', label='PLD (R$/MWh)', alpha=0.9)
    ax2_pld.set_ylabel('Preço PLD (R$/MWh)', fontsize=14)
    
    # --- 5. Painel 3: Armazenamento de Hidrogênio e Amônia ---
    ax3.plot(TIME_HORIZON, data['Estoque H2'], color='dodgerblue', label='Estoque H2 (kg)', lw=2.5)
    ax3.axhline(y=h2_max_soc_kg, color='dodgerblue', ls='--', alpha=0.5)
    ax3.set_ylabel('Massa H2 (kg)', fontsize=14, fontweight='bold')

    ax3_am = ax3.twinx()
    ax3_am.plot(TIME_HORIZON, data['Estoque Amônia'], color='darkgreen', label='Estoque Amônia (kg)', lw=2.5)
    ax3_am.axhline(y=ammonia_max_soc_kg, color='darkgreen', ls='--', alpha=0.5)
    ax3_am.set_ylabel('Massa Amônia (kg)', fontsize=14)

    # --- 6. Formatação Final ---
    passos_por_hora = int(1 / INTERVALO_HORAS)
    x_ticks = np.arange(0, len(TIME_HORIZON) + 1, passos_por_hora * 24)
    x_labels = [f"Dia {int(t/(passos_por_hora*24))}" for t in x_ticks]
    ax3.set_xticks(x_ticks)
    ax3.set_xticklabels(x_labels, rotation=0, ha='center')
    ax3.set_xlabel('Horizonte de Simulação', fontsize=14, fontweight='bold')
    ax3.set_xlim(0, len(TIME_HORIZON))
    
    # Legenda unificada
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    lines2_pld, labels2_pld = ax2_pld.get_legend_handles_labels()
    lines3, labels3 = ax3.get_legend_handles_labels()
    lines3_am, labels3_am = ax3_am.get_legend_handles_labels()
    
    fig.legend(lines + lines2 + lines2_pld + lines3 + lines3_am,
               labels + labels2 + labels2_pld + labels3 + labels3_am,
               loc='lower center', bbox_to_anchor=(0.5, -0.05), ncol=5, fontsize=12, frameon=False)

    # A chamada a 'tight_layout' foi removida, pois 'constrained_layout=True' já cuida disso.
    plt.show()

"""
def plot_scenario_results(TIME_HORIZON, s_block, s_name, initial_soc_dict, fixed_h2_price, fixed_ammonia_price, 
                          AMMONIA_PLANT_ELEC_CONSUMPTION_WH_PER_KG, INTERVALO_HORAS, N,
                          h2_max_soc_kg, h2_min_soc_kg, ammonia_max_soc_kg, ammonia_min_soc_kg,

    res_solar = np.array([pyo.value(s_block.p_solar[t]) for t in TIME_HORIZON]) / 1e6
    res_wind = np.array([pyo.value(s_block.p_wind[t]) for t in TIME_HORIZON]) / 1e6
    res_load = np.array([pyo.value(s_block.p_load[t]) for t in TIME_HORIZON]) / 1e6
    res_grid_buy = np.array([pyo.value(s_block.GRID_BUY_POWER[t]) for t in TIME_HORIZON]) / 1e6
    res_grid_sell = np.array([pyo.value(s_block.GRID_SELL_POWER[t]) for t in TIME_HORIZON]) / 1e6
    res_electrolyzer_consumption = np.array([pyo.value(s_block.P_PROD[t] + s_block.P_START[t]) for t in TIME_HORIZON]) / 1e6
    res_fc_gen = np.array([pyo.value(s_block.P_FC_GEN[t]) for t in TIME_HORIZON]) / 1e6
    res_bess_soc = np.array([pyo.value(s_block.BESS_SOC[t]) for t in TIME_HORIZON]) / 1e6
    res_elec_price = np.array([pyo.value(s_block.price[t]) for t in TIME_HORIZON]) * 1e6
    res_h2_soc = np.array([pyo.value(s_block.H2_STORAGE_SOC[t]) for t in TIME_HORIZON])
    res_ammonia_soc = np.array([pyo.value(s_block.AMMONIA_STORAGE_SOC[t]) for t in TIME_HORIZON])
    res_ammonia_produced = np.array([pyo.value(s_block.AMMONIA_PRODUCED_MASS[t]) for t in TIME_HORIZON])
    res_ammonia_plant_elec_mw = (res_ammonia_produced * AMMONIA_PLANT_ELEC_CONSUMPTION_WH_PER_KG / INTERVALO_HORAS) / 1e6
    
    passos_por_hora = int(1 / INTERVALO_HORAS)
    x_ticks = np.arange(0, len(TIME_HORIZON), passos_por_hora * 24)
    x_labels = [f"Dia {int(t/(passos_por_hora*24)) + 1}" for t in x_ticks]
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 18), sharex=True)
    fig.suptitle(f'Resultados da Operação com Fuel Cell - Cenário: {s_name.upper()}', fontsize=16, fontweight='bold')
    
    ax1.plot(TIME_HORIZON, res_solar, label='Geração Solar', color='gold', alpha=0.7)
    ax1.plot(TIME_HORIZON, res_wind, label='Geração Eólica', color='skyblue', alpha=0.7)
    ax1.plot(TIME_HORIZON, res_grid_buy, label='Compra da Rede', color='orange', linestyle='--')
    ax1.plot(TIME_HORIZON, res_fc_gen, label='Geração Fuel Cell', color='lime', linewidth=2)
    ax1.plot(TIME_HORIZON, -res_load, label='Carga Industrial', color='red', linestyle=':')
    ax1.plot(TIME_HORIZON, -res_electrolyzer_consumption, label='Consumo Eletrolisador', color='magenta')
    ax1.plot(TIME_HORIZON, -res_ammonia_plant_elec_mw, label='Consumo Planta Amônia', color='brown')
    ax1.plot(TIME_HORIZON, -res_grid_sell, label='Venda para Rede', color='navy')
    ax1.set_ylabel('Potência (MW)')
    ax1.axhline(0, color='black', lw=1)
    ax1.legend(loc='upper left', bbox_to_anchor=(1.01, 1))
    ax1.grid(True, alpha=0.3)
    
    ax2.plot(TIME_HORIZON, res_bess_soc, color='purple', label='SOC BESS (MWh)')
    ax2_pld = ax2.twinx()
    ax2_pld.plot(TIME_HORIZON, res_elec_price, color='green', linestyle=':', label='PLD (R$/MWh)', alpha=0.6)
    ax2.set_ylabel('Energia no BESS (MWh)')
    ax2_pld.set_ylabel('Preço PLD (R$/MWh)')
    ax2.grid(True, alpha=0.3)
    lines, labels = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_pld.get_legend_handles_labels()
    ax2.legend(lines + lines2, labels + labels2, loc='upper left', bbox_to_anchor=(1.01, 1))
    
    ax3.plot(TIME_HORIZON, res_h2_soc, color='blue', label='Estoque H2 (kg)')
    ax3_am = ax3.twinx()
    ax3_am.plot(TIME_HORIZON, res_ammonia_soc, color='darkgreen', label='Estoque Amônia (kg)')
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
"""


def carregar_solar_real(arquivo, N, usar_ultimos_dias=True):
    """
    Carrega dados reais de geração solar de um arquivo Excel.
    Calcula automaticamente quantos dias do histórico são necessários
    com base em N (96 intervalos de 15min por dia).
    """
    df = pd.read_excel(arquivo, parse_dates=['time'])
    df = df[['time', 'psolar']].sort_values('time').reset_index(drop=True)
    
    n_dias = ceil(N / 96)
    pontos_horarios = int(n_dias * 24)
    
    if usar_ultimos_dias:
        df_sel = df.tail(pontos_horarios)
    else:
        df_sel = df.head(pontos_horarios)
    
    df_sel = df_sel.sort_values('time').reset_index(drop=True)
    
    if len(df_sel) == 0:
        raise ValueError("Dados insuficientes no arquivo para o período solicitado.")
    
    start_time = df_sel['time'].iloc[0]
    
    # Converte horas para um valor numérico (horas desde o início)
    horas_originais = ((df_sel['time'] - start_time).dt.total_seconds() / 3600.0).values
    psolar_vals = df_sel['psolar'].values.astype(float)
    
    # Cria o novo grid de tempo (N pontos de 15min)
    horas_novas = np.arange(N) * 0.25
    
    # Interpolação linear
    solar_interp = np.interp(horas_novas, horas_originais, psolar_vals)
    
    # Diagnóstico
    print(f"✓ Dados solares REAIS carregados")
    print(f"  Período do histórico usado: {start_time.strftime('%d/%m/%Y %H:%M')} a "
          f"{df_sel['time'].iloc[-1].strftime('%d/%m/%Y %H:%M')}")
    print(f"  {len(df_sel)} pontos horários -> {N} pontos de 15min ({n_dias} dia(s))")
    print(f"  Média: {solar_interp.mean():.2f} W, "
          f"Mín: {solar_interp.min():.2f} W, "
          f"Máx: {solar_interp.max():.2f} W")
    
    return solar_interp

