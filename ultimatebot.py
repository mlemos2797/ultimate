import sys
import time
import pandas as pd
import numpy as np
import joblib
import streamlit as st  # Para criar a interface
from iqoptionapi.stable_api import IQ_Option
from configobj import ConfigObj

# Configuração do Streamlit
st.title("Robô de Trading IQ Option")
st.sidebar.header("Configurações")

# Definir variáveis de configuração através da interface
email = st.sidebar.text_input("Email IQ Option", value="seu_email@example.com")
senha = st.sidebar.text_input("Senha IQ Option", type="password")
ativo = st.sidebar.text_input("Ativo (Ex: EURUSD)", value="EURUSD")
tipo = st.sidebar.selectbox("Tipo de Conta", ['demo', 'real'])
valor_entrada = st.sidebar.number_input("Valor de Entrada (USD)", min_value=1.0, value=10.0)
stop_win = st.sidebar.number_input("Stop Win (USD)", min_value=1.0, value=100.0)
stop_loss = st.sidebar.number_input("Stop Loss (USD)", min_value=1.0, value=50.0)

# Carregar modelo treinado com Joblib
st.sidebar.write("Carregando o modelo...")
modelo = joblib.load(r'C:\Users\miguel.lemos\Documents\CFI\Miguel\Robot Iq Option\layamodel2.pkl')

# Inicializar variáveis de controle
conectado = False
lucro_total = 0
stop = True

# Função para conectar à API do IQ Option (executada ao clicar no botão)
def conectar_iq_option(email, senha, tipo):
    global API, conectado
    try:
        API = IQ_Option(email, senha)
        check, reason = API.connect()

        if not check:
            st.error(f"Problema na conexão: {reason}")
            return False
        else:
            st.success("Conectado com sucesso à IQ Option!")
            # Escolher tipo de conta (demo ou real)
            conta = 'PRACTICE' if tipo == 'demo' else 'REAL'
            API.change_balance(conta)
            st.sidebar.write(f"Conectado à conta {conta}")
            conectado = True
            return True
    except Exception as e:
        st.error(f"Erro ao conectar: {str(e)}")
        return False

# Função para verificar stop win e stop loss
def check_stop():
    global stop, lucro_total
    if lucro_total <= -abs(stop_loss):
        stop = False
        st.error(f"STOP LOSS ATINGIDO: {lucro_total}")
        sys.exit()

    if lucro_total >= abs(stop_win):
        stop = False
        st.success(f"STOP WIN ATINGIDO: {lucro_total}")
        sys.exit()

# Função para coletar dados históricos (últimos 1000 candles de 1 minuto)
def collect_historical_data(asset, duration, count):
    candles = API.get_candles(asset, duration, count, time.time())
    df = pd.DataFrame(candles)
    df['close'] = df['close'].astype(float)
    df['open'] = df['open'].astype(float)
    df['high'] = df['max'].astype(float)
    df['low'] = df['min'].astype(float)
    return df

# Função para calcular as 10 variáveis utilizadas no treinamento do modelo
def calcular_variaveis(df):
    df['body_size'] = abs(df['close'] - df['open'])  # Tamanho do corpo da vela
    df['upper_wick'] = df['high'] - np.maximum(df['close'], df['open'])  # Pavio superior
    df['lower_wick'] = np.minimum(df['close'], df['open']) - df['low']  # Pavio inferior
    df['price_change'] = df['close'] - df['open']  # Mudança de preço
    df['price_range'] = df['high'] - df['low']  # Faixa de preço
    df['price_change_pct'] = (df['price_change'] / df['open']) * 100  # Percentual de mudança de preço
    return df

# Função para prever a próxima vela usando o modelo pré-treinado
def prever_direcao(df):
    # Coletar as variáveis de entrada do modelo
    df = calcular_variaveis(df)
    X = df[['open', 'close', 'high', 'low', 'body_size', 'upper_wick', 'lower_wick', 'price_change', 'price_range', 'price_change_pct']].iloc[-1:].values
    previsao = modelo.predict(X)[0]  # Previsão: 1 para "CALL", 0 para "PUT"
    return 'call' if previsao == 1 else 'put'

# Função para executar a compra
def compra(ativo, valor_entrada, direcao, exp, tipo):
    global stop, lucro_total
    if stop:
        if tipo == 'digital':
            check, id = API.buy_digital_spot_v2(ativo, valor_entrada, direcao, exp)
        else:
            check, id = API.buy(valor_entrada, ativo, direcao, exp)

        if check:
            st.write(f'Ordem colocada no ativo {ativo} com direção {direcao}')
            while True:
                time.sleep(1)
                status, resultado = API.check_win_digital_v2(id) if tipo == 'digital' else API.check_win_v4(id)
                if status:
                    lucro_total += round(resultado, 2)
                    return resultado
        else:
            st.error(f"Erro ao abrir ordem: {id}")
            return None

# Estratégia de SorosGale
def estrategia_sorosgale(ativo, modelo, tipo):
    global lucro_total, perdas_acumuladas, nivel
    perdas_acumuladas = 0
    max_nivel = 17
    valor_entrada_inicial = valor_entrada
    progress_bar = st.progress(0)

    while stop:
        for nivel in range(1, max_nivel + 1):
            st.write(f"Iniciando Nível {nivel} com perdas acumuladas de {perdas_acumuladas}")
            df = collect_historical_data(ativo, 60, 5)
            direcao = prever_direcao(df)

            if nivel == 1:
                entrada = valor_entrada_inicial
            else:
                entrada = entrada * 1.4

            st.write(f"Entrada 1 do nível {nivel}: {entrada}")
            resultado_primeira = compra(ativo, entrada, direcao, 1, tipo)

            if resultado_primeira > 0:
                st.write(f"Vitória na primeira entrada do nível {nivel}.")
                entrada_segunda = entrada * 1.89
                resultado_segunda = compra(ativo, entrada_segunda, direcao, 1, tipo)
                if resultado_segunda > 0:
                    lucro_total += resultado_primeira + resultado_segunda
                    st.success(f"Vitória consecutiva no nível {nivel}. Lucro total: {lucro_total}. Reiniciando.")
                    break
                else:
                    st.write(f"Perda na segunda entrada do nível {nivel}. Continuando.")
            else:
                perdas_acumuladas += entrada
                st.write(f"Perda na primeira entrada do nível {nivel}. Avançando para o próximo nível.")

            check_stop()

# Botão para conectar e iniciar a estratégia
if st.button('Iniciar Estratégia'):
    if conectar_iq_option(email, senha, tipo):
        estrategia_sorosgale(ativo, modelo, tipo)