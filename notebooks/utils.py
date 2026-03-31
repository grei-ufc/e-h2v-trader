import pyomo.environ as pyo
import mpisppy.utils.sputils as sputils
from mpisppy.opt.ef import ExtensiveForm
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import os


def carregar_pld_12m(caminho_arquivo, sheet=0):
    """
    Carrega e processa o arquivo de PLD, renomeando colunas e tratando tipos de dados.
    """
    if not os.path.exists(caminho_arquivo):
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho_arquivo}")
    df = pd.read_excel(caminho_arquivo, sheet_name=sheet, header=0)
    df.columns = df.columns.map(lambda c: str(c).strip().lower())
    if not {"hour", "spotpricebrl"}.issubset(df.columns):
        raise ValueError(f"Esperava colunas {{'hour', 'spotpricebrl'}}, mas encontrei {set(df.columns)}.")
    df["hour"] = pd.to_datetime(df["hour"], errors="coerce")
    df["spotpricebrl"] = pd.to_numeric(df["spotpricebrl"], errors="coerce")
    if df["hour"].isna().any() or df["spotpricebrl"].isna().any():
        raise ValueError("Valores nulos ou inválidos encontrados no arquivo de PLD após a conversão.")
    df = df.rename(columns={"hour": "data", "spotpricebrl": "pld"})
    return df.sort_values("data").reset_index(drop=True)


def gerar_perfis_realistas(N, intervalo_horas, pot_solar_max_w, pot_eolica_max_w, pot_carga_max_w):
    """
    Gera perfis sintéticos de solar, eólica e carga.
    Esta função será usada apenas para a carga, a menos que dados reais de carga sejam fornecidos.
    """
    horas = np.arange(0, 24, intervalo_horas)
    perfil_solar_unitario = np.maximum(0, np.sin(np.pi * (horas - 6) / 12))**1.5
    solar_gen_w = perfil_solar_unitario * pot_solar_max_w
    perfil_eolico_unitario = (0.5 + 0.2 * np.sin(np.pi * horas / 6) + 0.3 * np.cos(np.pi * horas / 12 + np.pi/4) + 0.1 * np.random.rand(N))
    perfil_eolico_unitario = np.clip(perfil_eolico_unitario, 0, 1)
    eolica_gen_w = perfil_eolico_unitario * pot_eolica_max_w
    perfil_carga_unitario = (0.55 - 0.25 * np.cos(2 * np.pi * (horas - 4) / 24) + 0.4 * np.exp(-0.5 * ((horas - 15) / 3.5)**2))
    carga_w = perfil_carga_unitario * pot_carga_max_w
    return solar_gen_w.tolist(), eolica_gen_w.tolist(), carga_w.tolist()

    
def carregar_geracao_data(caminho_arquivo, N_intervals, unit_conversion_factor=1e6, sheet_name=0):

    if not os.path.exists(caminho_arquivo):
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho_arquivo}")

    df = pd.read_excel(caminho_arquivo, sheet_name=sheet_name, header=None) # Lê sem cabeçalho inicialmente

    generation_data = []
 
    if df.shape[0] == N_intervals: # Assume que os dados começam na linha 0
        generation_data = df.iloc[:, 1].values # Assume que a geração está na segunda coluna (índice 1)
    elif df.shape[0] == N_intervals + 1: # Assume que há um cabeçalho na linha 0, dados começam na linha 1
        generation_data = df.iloc[1:, 1].values # Assume que a geração está na segunda coluna (índice 1)
    else:
        raise ValueError(f"O arquivo {caminho_arquivo} não contém {N_intervals} ou {N_intervals+1} linhas de dados esperadas para 96 intervalos. Encontradas {df.shape[0]} linhas.")

    # Converte para numérico, tratando valores não numéricos (NaN) como 0.0
    generation_profile = [float(x) if pd.notna(x) else 0.0 for x in generation_data]

    if len(generation_profile) != N_intervals:
        raise ValueError(f"O perfil de geração lido do arquivo {caminho_arquivo} tem {len(generation_profile)} pontos, mas {N_intervals} eram esperados.")

    # Aplica o fator de conversão de unidade (MW para W)
    converted_profile = [val * unit_conversion_factor for val in generation_profile]

    return converted_profile


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
  #  print(f"\n--- Gerando gráficos para o Cenário: {s_name.upper()} ---")
    
    # Extração de resultados
    res_solar = np.array([pyo.value(s_block.p_solar[t]) for t in TIME_HORIZON]) / 1e6
    res_wind = np.array([pyo.value(s_block.p_wind[t]) for t in TIME_HORIZON]) / 1e6
    res_load = np.array([pyo.value(s_block.p_load[t]) for t in TIME_HORIZON]) / 1e6
    res_elec_price = np.array([pyo.value(s_block.price[t]) for t in TIME_HORIZON]) * 1e6
    res_grid_buy = np.array([pyo.value(s_block.GRID_BUY_POWER[t]) for t in TIME_HORIZON]) / 1e6
    res_grid_sell = np.array([pyo.value(s_block.GRID_SELL_POWER[t]) for t in TIME_HORIZON]) / 1e6
    res_bess_charge = np.array([pyo.value(s_block.BESS_CHARGE_POWER[t]) for t in TIME_HORIZON]) / 1e6
    res_bess_discharge = np.array([pyo.value(s_block.BESS_DISCHARGE_POWER[t]) for t in TIME_HORIZON]) / 1e6
    res_bess_soc = np.array([pyo.value(s_block.BESS_SOC[t]) for t in TIME_HORIZON]) / 1e6
    res_electrolyzer_consumption = np.array([pyo.value(s_block.ELECTROLYZER_ELEC_CONSUMPTION[t]) for t in TIME_HORIZON]) / 1e6
    res_thermal_generation = np.array([pyo.value(s_block.THERMAL_ELEC_GENERATION[t]) for t in TIME_HORIZON]) / 1e6
    res_h2_produced = np.array([pyo.value(s_block.H2_PRODUCED[t]) for t in TIME_HORIZON])
    res_h2_soc = np.array([pyo.value(s_block.H2_STORAGE_SOC[t]) for t in TIME_HORIZON])
    res_h2_to_market = np.array([pyo.value(s_block.H2_TO_MARKET_MASS[t]) for t in TIME_HORIZON])
    res_h2_to_thermal = np.array([pyo.value(s_block.H2_TO_THERMAL_MASS[t]) for t in TIME_HORIZON])
    res_h2_to_ammonia = np.array([pyo.value(s_block.H2_TO_AMMONIA_PLANT_MASS[t]) for t in TIME_HORIZON])
    res_ammonia_produced = np.array([pyo.value(s_block.AMMONIA_PRODUCED_MASS[t]) for t in TIME_HORIZON])
    res_ammonia_soc = np.array([pyo.value(s_block.AMMONIA_STORAGE_SOC[t]) for t in TIME_HORIZON])
    res_ammonia_to_market = np.array([pyo.value(s_block.AMMONIA_TO_MARKET_MASS[t]) for t in TIME_HORIZON])
    
    # NOVO: Calcular consumo elétrico da planta de amônia (em MW)
    res_ammonia_plant_elec_consumption_mw = np.array([
        pyo.value(s_block.AMMONIA_PRODUCED_MASS[t]) * AMMONIA_PLANT_ELEC_CONSUMPTION_WH_PER_KG / INTERVALO_HORAS
        for t in TIME_HORIZON
    ]) / 1e6 # Converter para MW

    passos_por_hora = int(1 / INTERVALO_HORAS)
    x_ticks = np.arange(0, N + 1, passos_por_hora * 4)
    x_labels = [f"{int(t/passos_por_hora):02d}:00" for t in x_ticks]
    
    filename_base = f"resultados_h2_{fixed_h2_price:.2f}_amonia_{fixed_ammonia_price:.2f}_pld_{s_name}"

    # --- Gráfico 1: Elétrico ---
    fig1, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 16), sharex=True, gridspec_kw={'height_ratios': [2, 1, 1.5]})
    fig1.suptitle(f'Despacho Elétrico | Cenário PLD: {s_name.upper()}', fontsize=16)

    # AX1 - Balanço Geral de Potência
    ax1.set_title('Balanço Geral de Potência')
    ax1.plot(TIME_HORIZON, res_solar, label='Solar', color='gold')
    ax1.plot(TIME_HORIZON, res_wind, label='Eólica', color='deepskyblue')
    ax1.plot(TIME_HORIZON, res_thermal_generation, label='Térmica H₂', color='darkviolet')
    ax1.plot(TIME_HORIZON, res_grid_buy, label='Rede (Compra)', color='darkorange')
    ax1.plot(TIME_HORIZON, -res_load, label='Carga (Demanda)', color='red', linestyle='--')
    # ALTERAÇÃO AQUI: Legenda do Eletrolisador mais explícita
    ax1.plot(TIME_HORIZON, -res_electrolyzer_consumption, label='Eletrolisador (p/ H₂ da Amônia)', color='magenta', linestyle='--')
    # NOVO: Adicionar consumo elétrico da planta de amônia
    ax1.plot(TIME_HORIZON, -res_ammonia_plant_elec_consumption_mw, label='Consumo Elétrico Planta Amônia', color='darkred', linestyle=':')
    ax1.plot(TIME_HORIZON, -res_grid_sell, label='Rede (Venda)', color='navy', linestyle='--')
    
    # Potência do BESS unificada (descarga é positiva, carga é negativa)
    res_bess_net_power = res_bess_discharge - res_bess_charge
    ax1.plot(TIME_HORIZON, res_bess_net_power, label='BESS (Líquido)', color='limegreen', linewidth=2)
    
    ax1.axhline(0, color='black', linewidth=0.8)
    ax1.set_ylabel('Potência (MW)')
    ax1.grid(True, linestyle=':', alpha=0.7)
    ax1.legend(loc='upper left', bbox_to_anchor=(1.02, 1), borderaxespad=0.)

    # AX2 - Gráfico Focado na Potência de Carga e Descarga do BESS
    ax2.set_title('Potência de Carga e Descarga do BESS')
    # Usando área preenchida para melhor visualização
    ax2.fill_between(TIME_HORIZON, res_bess_net_power, where=res_bess_net_power>=0, color='limegreen', alpha=0.7, interpolate=True, label='Descarga')
    ax2.fill_between(TIME_HORIZON, res_bess_net_power, where=res_bess_net_power<=0, color='dodgerblue', alpha=0.7, interpolate=True, label='Carga')
    ax2.axhline(0, color='black', linewidth=0.8)
    ax2.set_ylabel('Potência (MW)')
    ax2.grid(True, linestyle=':', alpha=0.7)
    ax2.legend(loc='best')

    # --- ADIÇÃO PARA AJUSTE DE ESCALA DO AX2 ---
    # Verifica se há alguma atividade significativa no BESS para ajustar a escala
    if np.any(res_bess_net_power != 0):
        min_bess_power = np.min(res_bess_net_power)
        max_bess_power = np.max(res_bess_net_power)
        # Adiciona uma pequena margem para melhor visualização
        margin = max(abs(min_bess_power), abs(max_bess_power)) * 0.1
        if margin == 0: # Caso todos os valores sejam zero, mas não queremos erro
            margin = 0.1 # Define uma margem mínima para evitar divisão por zero ou range zero
        ax2.set_ylim(min_bess_power - margin, max_bess_power + margin)
    else:
        # Se o BESS não atua, define um limite padrão pequeno para mostrar que está plano
        ax2.set_ylim(-0.5, 0.5) # Exemplo: +/- 0.5 MW
    # --- FIM DA ADIÇÃO PARA AJUSTE DE ESCALA DO AX2 ---

    # --- ADIÇÃO PARA DEBUG: IMPRIMIR VALORES DE BESS ---
   # print(f"--- Valores de BESS para Cenário: {s_name.upper()} ---")
   # print("Potência de Carga do BESS (MW):")
   # print(res_bess_charge)
   # print("Potência de Descarga do BESS (MW):")
   # print(res_bess_discharge)
   # print("Potência Líquida do BESS (MW):")
   # print(res_bess_net_power)
  #  print("SOC do BESS (MWh):")
   # print(res_bess_soc)
    # --- FIM DA ADIÇÃO PARA DEBUG ---
    
    # AX3 - SOC do BESS vs PLD
    ax3.set_title('Energia Armazenada (SOC) vs. Preço da Eletricidade (PLD)')
    ax3_twin = ax3.twinx()
    ax3.plot(TIME_HORIZON, res_bess_soc, color='purple', linewidth=2, label='SOC da BESS (MWh)')
    ax3.set_ylabel('Energia (MWh)', color='purple')
    ax3.tick_params(axis='y', labelcolor='purple')
    ax3.set_ylim(bottom=0)
    ax3_twin.plot(TIME_HORIZON, res_elec_price, color='darkgreen', linestyle=':', label='PLD (R$/MWh)')
    ax3_twin.set_ylabel('Preço (R$/MWh)', color='darkgreen')
    ax3_twin.tick_params(axis='y', labelcolor='darkgreen')
    ax3.set_xlabel('Hora do Dia')
    ax3.set_xticks(x_ticks)
    ax3.set_xticklabels(x_labels)
    ax3.grid(True, linestyle=':', alpha=0.5)
    lines, labels = ax3.get_legend_handles_labels()
    lines2, labels2 = ax3_twin.get_legend_handles_labels()
    ax3.legend(lines + lines2, labels + labels2, loc='best')

    plt.tight_layout(rect=[0, 0, 0.88, 0.96])
    # plt.savefig(f"{filename_base}_eletrico_final.png", dpi=300, bbox_inches='tight')
    plt.show()

    # --- Gráficos de H2 e Amônia ---
    fig2, (ax4, ax5) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)
    fig2.suptitle(f'Despacho de H₂ | Preço Venda: R$ {fixed_h2_price:.2f}/kg', fontsize=16)
    ax4.plot(TIME_HORIZON, res_h2_produced, label='H₂ Produzido', color='cyan', linestyle='-')
    ax4.plot(TIME_HORIZON, -res_h2_to_market, label='H₂ (Venda)', color='firebrick', linestyle='--')
    ax4.plot(TIME_HORIZON, -res_h2_to_thermal, label='H₂ p/ Térmica', color='saddlebrown', linestyle=':')
    ax4.plot(TIME_HORIZON, -res_h2_to_ammonia, label='H₂ p/ Amônia', color='darkgreen', linestyle='--')
    ax4.axhline(0, color='gray', linestyle='-', linewidth=0.8)
    ax4.set_ylabel('Massa de H₂ (kg)')
    ax4.legend(loc='best')
    ax4.grid(True, linestyle='--', alpha=0.6)
    ax4.set_title('Balanço de Massa de H₂ (Produção > 0, Usos < 0)')
    ax5.plot(TIME_HORIZON, res_h2_soc, label='SOC do Tanque de H₂', color='blue', linewidth=2)
    ax5.axhline(h2_max_soc_kg, color='r', linestyle='--', label='SOC Máximo H₂')
    ax5.axhline(h2_min_soc_kg, color='r', linestyle=':', label='SOC Mínimo H₂')
    ax5.axhline(initial_soc_dict['h2'], color='g', linestyle='-.', label='SOC Inicial Ótimo', linewidth=2, alpha=0.8)
    ax5.set_ylabel('Massa de H₂ (kg)')
    ax5.set_xlabel('Hora do Dia')
    ax5.set_xticks(x_ticks)
    ax5.set_xticklabels(x_labels)
    ax5.legend(loc='best')
    ax5.grid(True, linestyle='--', alpha=0.6)
    ax5.set_title('Operação do Armazenamento de H₂')
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    # plt.savefig(f"{filename_base}_h2.png", dpi=300, bbox_inches='tight')
    plt.show()

    fig3, (ax7, ax8) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)
    rendimento_h2_nh3 = 1 / TX_H2_TO_AMMONIA_KG_PER_KG
    fig3.suptitle(f'Despacho de Amônia (NH₃) | Preço: R$ {fixed_ammonia_price:.2f}/kg | Rendimento: {rendimento_h2_nh3:.2f} kg NH₃ por kg H₂', fontsize=16)
    ax7.plot(TIME_HORIZON, res_ammonia_produced, label='Amônia Produzida', color='green', linestyle='-')
    ax7.plot(TIME_HORIZON, -res_ammonia_to_market, label='Amônia (Venda)', color='darkred', linestyle='--')
    ax7.axhline(0, color='gray', linestyle='-', linewidth=0.8)
    ax7.set_ylabel('Massa (kg)')
    ax7.legend(loc='best')
    ax7.grid(True, linestyle='--', alpha=0.7)
    ax7.set_title('Balanço de Massa de Amônia (Produção > 0, Usos < 0)')
    ax8.plot(TIME_HORIZON, res_ammonia_soc, label='SOC do Tanque de Amônia', color='darkgreen', linewidth=2)
    ax8.axhline(ammonia_max_soc_kg, color='r', linestyle='--', label='SOC Máximo NH₃')
    ax8.axhline(ammonia_min_soc_kg, color='r', linestyle=':', label='SOC Mínimo NH₃')
    ax8.axhline(initial_soc_dict['ammonia'], color='b', linestyle='-.', label='SOC Inicial Ótimo', linewidth=2, alpha=0.8)
    ax8.set_ylabel('Massa de Amônia (kg)')
    ax8.set_xlabel('Hora do Dia')
    ax8.set_xticks(x_ticks)
    ax8.set_xticklabels(x_labels)
    ax8.legend(loc='best')
    ax8.grid(True, linestyle='--', alpha=0.7)
    ax8.set_title('Operação do Armazenamento de Amônia')
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    # plt.savefig(f"{filename_base}_amonia.png", dpi=300, bbox_inches='tight')
    plt.show()

    # --- NOVO GRÁFICO: Detalhes do Processo de Amônia ---
    fig4, (ax9, ax10) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)
    fig4.suptitle(f'Detalhes do Processo de Produção de Amônia | Cenário: {s_name.upper()}', fontsize=16)

    # AX9 - Consumo Elétrico para Amônia (com eixo secundário para planta de amônia)
    ax9.set_title('Consumo Elétrico para Eletrolisador e Planta de Amônia')
    ax9.plot(TIME_HORIZON, res_electrolyzer_consumption, label='Eletrolisador (MW)', color='magenta', linewidth=2)
    ax9.set_ylabel('Potência Eletrolisador (MW)', color='magenta')
    ax9.tick_params(axis='y', labelcolor='magenta')
    ax9.grid(True, linestyle=':', alpha=0.7)
    
    ax9_twin = ax9.twinx() # Cria um eixo Y secundário
    ax9_twin.plot(TIME_HORIZON, res_ammonia_plant_elec_consumption_mw, label='Planta de Amônia (MW)', color='darkred', linestyle='--', linewidth=2)
    ax9_twin.set_ylabel('Potência Planta Amônia (MW)', color='darkred')
    ax9_twin.tick_params(axis='y', labelcolor='darkred')

    # Combinar legendas de ambos os eixos
    lines, labels = ax9.get_legend_handles_labels()
    lines2, labels2 = ax9_twin.get_legend_handles_labels()
    ax9.legend(lines + lines2, labels + labels2, loc='best')


    # AX10 - Balanço de Massa de H2 e Amônia no Processo
    ax10.set_title('Massa de H₂ Consumida e Amônia Produzida')
    ax10.plot(TIME_HORIZON, res_h2_to_ammonia, label='H₂ Consumido pela Planta Amônia (kg)', color='blue', linewidth=2)
    ax10.plot(TIME_HORIZON, res_ammonia_produced, label='Amônia Produzida (kg)', color='green', linewidth=2)
    ax10.set_ylabel('Massa (kg)')
    ax10.set_xlabel('Hora do Dia')
    ax10.set_xticks(x_ticks)
    ax10.set_xticklabels(x_labels)
    ax10.grid(True, linestyle=':', alpha=0.7)
    ax10.legend(loc='best')

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    # plt.savefig(f"{filename_base}_ammonia_process.png", dpi=300, bbox_inches='tight')
    plt.show()

    # --- ADIÇÃO PARA DEBUG: IMPRIMIR VALORES DE CONSUMO DA PLANTA DE AMÔNIA ---
  #   print(f"--- Valores de Consumo Elétrico da Planta de Amônia para Cenário: {s_name.upper()} ---")
  #   print("Consumo Elétrico Planta Amônia (MW):")
  #   print(res_ammonia_plant_elec_consumption_mw)
  #   print("Valor máximo de Consumo Elétrico Planta Amônia (MW):", np.max(res_ammonia_plant_elec_consumption_mw))
    # --- FIM DA ADIÇÃO PARA DEBUG ---

 
    # --- FIM DO NOVO INDICADOR ---