import streamlit as st
import google.generativeai as genai
import os
import tempfile
import json
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- CONFIGURAÇÕES GERAIS ---
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
# Usando o modelo PRO para ter a audição máxima em áudios difíceis e baixos:
NOME_MODELO = 'models/gemini-2.5-flash'

# 🛑 O ID DA SUA PASTA DO DRIVE:
ID_DA_PASTA = "1nCR3mW_pL57XGIX4R2N6NzrMv6ljK_ce"

# --- FUNÇÕES DO GOOGLE DRIVE ---
@st.cache_resource
def conectar_drive():
    cred_json = st.secrets["GOOGLE_CREDENTIALS_JSON"]
    cred_dict = json.loads(cred_json)
    creds = service_account.Credentials.from_service_account_info(
        cred_dict, scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

def listar_arquivos_drive(service, folder_id):
    arquivos_audio = []
    extensoes_permitidas = ('.mp3', '.wav', '.m4a', '.ogg')
    
    query = f"'{folder_id}' in parents and trashed=false"
    
    page_token = None
    while True:
        resultados = service.files().list(
            q=query, 
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token
        ).execute()
        
        itens = resultados.get('files', [])
        
        for item in itens:
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                arquivos_audio.extend(listar_arquivos_drive(service, item['id']))
            else:
                if item['name'].lower().endswith(extensoes_permitidas):
                    arquivos_audio.append(item)
                    
        page_token = resultados.get('nextPageToken', None)
        if page_token is None:
            break
            
    return arquivos_audio

def baixar_audio_drive(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh.read()

# --- INTERFACE WEB ---
st.set_page_config(layout="wide")
st.title("☁️ Auditoria Automática - FindUP")
st.write("Selecione uma ligação diretamente do seu Google Drive para análise.")

try:
    service = conectar_drive()
    arquivos = listar_arquivos_drive(service, ID_DA_PASTA)
    
    if not arquivos:
        st.warning("Nenhum arquivo de áudio encontrado na pasta do Drive.")
    else:
        opcoes = {arq['name']: arq['id'] for arq in arquivos}
        nome_selecionado = st.selectbox("Selecione a gravação (Leo Madeiras):", ["-- Escolha uma gravação --"] + list(opcoes.keys()))

        if nome_selecionado != "-- Escolha uma gravação --":
            
            coluna_esquerda, coluna_direita = st.columns(2)
            
            with coluna_esquerda:
                st.markdown("### 🎵 Gravação Selecionada")
                st.info(f"Arquivo: **{nome_selecionado}**")
                btn_analisar = st.button("▶️ Ouvir e Analisar com IA", use_container_width=True)
            
            if btn_analisar:
                with coluna_esquerda:
                    file_id = opcoes[nome_selecionado]
                    
                    with st.spinner("📥 Baixando áudio do Google Drive..."):
                        conteudo_audio = baixar_audio_drive(service, file_id)
                        
                        extensao = os.path.splitext(nome_selecionado)[1]
                        if not extensao: extensao = ".mp3"
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix=extensao) as tmp:
                            tmp.write(conteudo_audio)
                            caminho_temp = tmp.name
                        
                        st.audio(conteudo_audio, format=f"audio/{extensao.replace('.', '')}")
                            
                    with st.spinner("🧠 A IA está ouvindo a ligação (Modelo PRO)..."):
                        audio_enviado = genai.upload_file(path=caminho_temp)
                        
                        prompt = """
                        Você é um Analista de Qualidade Sênior do Service Desk de TI da FindUP. Você audita chamados técnicos das lojas "Leo Madeiras".
                        
                        🚨 REGRA ABSOLUTA DE INÍCIO DE CHAMADA: A ligação REAL SÓ COMEÇA quando você ouvir a frase exata: "Leo madeiras...". TUDO antes dessa frase é tempo de espera da URA (mesmo que a voz da URA pareça humana dizendo "Aguarde ser atendido"). 
                        O atendimento humano só inicia na palavra "Leo madeiras". A voz do analista que fala isso estará MUITO BAIXA.

                        1. **⏱️ Início do Atendimento:** Avance o áudio ignorando todas as repetições de "aguarde". Encontre o momento EXATO em que a palavra "Leo madeiras" é dita pela primeira vez por uma voz humana muito baixa. Informe essa minutagem exata (ex: 03:45). Se você não ouvir "Leo madeiras", a ligação é apenas abandono na fila.
                        2. **🧑‍💻 Analista Responsável:** Imediatamente após falar "Leo madeiras", o analista vai dizer o nome dele (geralmente duas vezes). Escreva esse nome. Se inaudível devido ao áudio baixo, escreva: "Não identificado".
                        3. **📝 Contexto da Ligação (Problema de TI):** Qual é a falha TÉCNICA ou de SISTEMA (PDV, impressora, internet, senha) que a loja está enfrentando? O cliente pode falar termos de loja (carnê, pallet), mas o seu foco é o problema do sistema de TI.
                        4. **🎫 Registro (Ticket):** O analista repassou algum número de chamado? Se sim, coloque em negrito.
                        5. **🌡️ Termômetro de Sentimento:** O cliente estava Satisfeito, Neutro ou Frustrado/Irritado com a falha?
                        6. **✅ Desfecho da Chamada:** O problema de TI foi resolvido na hora (FCR) ou precisou ser escalonado?
                        """
                        
                        model = genai.GenerativeModel(NOME_MODELO)
                        response = model.generate_content([audio_enviado, prompt])
                        
                        try:
                            relatorio_final = response.text
                        except ValueError:
                            motivo = response.candidates[0].finish_reason if response.candidates else "Desconhecido"
                            relatorio_final = f"⚠️ **A IA não conseguiu gerar o texto para este áudio.**\n\nIsso geralmente acontece se o áudio estiver corrompido ou bloqueado por filtros de segurança. Código: {motivo}"
                        
                        genai.delete_file(audio_enviado.name)
                        os.remove(caminho_temp)
                
                with coluna_direita:
                    st.success("Auditoria concluída com sucesso!")
                    st.markdown("### 📋 Ficha de Monitoria (QA)")
                    st.markdown(relatorio_final)

except Exception as e:
    st.error(f"Erro no sistema: {e}")





