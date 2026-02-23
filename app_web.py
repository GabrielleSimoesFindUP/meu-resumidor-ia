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
                            
                    with st.spinner("🧠 A IA está ouvindo a ligação..."):
                        audio_enviado = genai.upload_file(path=caminho_temp)
                        
                       prompt = """
                        Você é um Analista de Qualidade Sênior do Service Desk da FindUP, focado no cliente Leo Madeiras.
                        Ouça a gravação anexada com extremo rigor técnico e forneça um relatório estruturado.
                        
                        🚨 ALERTA CRÍTICO DE AUDIÇÃO: A gravação possui um longo tempo de espera na URA ("Sua chamada é a número..."). O analista humano VAI falar depois da URA, mas a voz dele pode estar MUITO BAIXA em comparação com a música. Você DEVE ouvir o áudio inteiro até o último segundo e focar ao máximo para captar a voz humana, ignorando a repetição da URA.

                        REGRAS DE OURO: 
                        1. Nunca invente ou suponha informações. 
                        2. Procure ativamente pela voz baixa do analista após a URA.

                        1. **⏱️ Início do Atendimento:** Informe o tempo exato da gravação (em minutos e segundos) em que a URA termina e o analista humano começa a falar (mesmo que a voz esteja baixa).
                        2. **🧑‍💻 Analista Responsável:** Identifique o nome do atendente. O roteiro é "Leo madeiras, [NOME DO ANALISTA], bom dia/boa tarde/boa noite". Ele fala o nome duas vezes. Preste muita atenção na voz baixa e extraia o nome. Se totalmente inaudível, escreva: "Não identificado".
                        3. **📝 Contexto da Ligação:** Qual foi o problema, dúvida ou solicitação do usuário?
                        4. **🎫 Registro (Ticket):** O analista repassou algum número de chamado ou incidente? Se sim, coloque em negrito.
                        5. **🌡️ Termômetro de Sentimento:** O cliente estava Satisfeito, Neutro ou Frustrado/Irritado? Justifique.
                        6. **✅ Desfecho da Chamada:** Como foi finalizado? Resolvido em linha (FCR) ou escalonado?
                        """
                        
                        model = genai.GenerativeModel(NOME_MODELO)
                        response = model.generate_content([audio_enviado, prompt])
                        
                        try:
                            relatorio_final = response.text
                        except ValueError:
                            motivo = response.candidates[0].finish_reason if response.candidates else "Desconhecido"
                            relatorio_final = f"⚠️ **A IA não conseguiu gerar o texto para este áudio.**\n\nIsso geralmente acontece se o áudio estiver completamente mudo, corrompido, ou se a IA bloqueou a transcrição por conter dados muito sensíveis (Filtro de Segurança). Código do bloqueio: {motivo}"
                        
                        genai.delete_file(audio_enviado.name)
                        os.remove(caminho_temp)
                
                with coluna_direita:
                    st.success("Auditoria concluída com sucesso!")
                    st.markdown("### 📋 Ficha de Monitoria (QA)")
                    st.markdown(relatorio_final)

except Exception as e:
    st.error(f"Erro no sistema: {e}")


