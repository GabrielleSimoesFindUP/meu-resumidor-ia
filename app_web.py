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

# 🛑 COLE O ID DA SUA PASTA DO DRIVE AQUI:
ID_DA_PASTA = "1nCR3mW_pL57XGIX4R2N6NzrMv6ljK_ce"

# --- FUNÇÕES DO GOOGLE DRIVE ---
@st.cache_resource
def conectar_drive():
    # Lê a chave do robô que guardamos no cofre do Streamlit
    cred_json = st.secrets["GOOGLE_CREDENTIALS_JSON"]
    cred_dict = json.loads(cred_json)
    creds = service_account.Credentials.from_service_account_info(
        cred_dict, scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

def listar_arquivos_drive(service, folder_id):
    arquivos_audio = []
    extensoes_permitidas = ('.mp3', '.wav', '.m4a', '.ogg')
    
    # Busca tudo (arquivos e pastas) dentro da pasta atual
    query = f"'{folder_id}' in parents and trashed=false"
    
    # O loop 'while' garante que ele leia tudo, mesmo se tiver centenas de arquivos
    page_token = None
    while True:
        resultados = service.files().list(
            q=query, 
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token
        ).execute()
        
        itens = resultados.get('files', [])
        
        for item in itens:
            # Se o item for uma PASTA, o robô "entra" nela (recursão)
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                # Ele junta os áudios da subpasta com os que já encontrou
                arquivos_audio.extend(listar_arquivos_drive(service, item['id']))
            else:
                # Se for um arquivo normal, verifica se é áudio
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
st.title("☁️ Auditoria Automática - FindUP")
st.write("Selecione uma ligação diretamente do seu Google Drive para análise.")

try:
    # Conecta no Drive e lista os arquivos
    service = conectar_drive()
    arquivos = listar_arquivos_drive(service, ID_DA_PASTA)
    
    if not arquivos:
        st.warning("Nenhum arquivo de áudio encontrado na pasta do Drive.")
    else:
        # Cria um menu (dropdown) com os nomes dos arquivos
        opcoes = {arq['name']: arq['id'] for arq in arquivos}
        nome_selecionado = st.selectbox("Selecione a gravação (Leo Madeiras):", ["-- Escolha uma gravação --"] + list(opcoes.keys()))

        if nome_selecionado != "-- Escolha uma gravação --":
            
            if st.button("Puxar do Drive e Analisar"):
                file_id = opcoes[nome_selecionado]
                
                with st.spinner("📥 Baixando áudio do Google Drive..."):
                    conteudo_audio = baixar_audio_drive(service, file_id)
                    
                    # Identifica a extensão do arquivo (.mp3, .wav)
                    extensao = os.path.splitext(nome_selecionado)[1]
                    if not extensao: extensao = ".mp3"
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=extensao) as tmp:
                        tmp.write(conteudo_audio)
                        caminho_temp = tmp.name
                        
                with st.spinner("🧠 Analisando com a IA do Google..."):
                    audio_enviado = genai.upload_file(path=caminho_temp)
                    
                    prompt = """
                    Você é um Analista de Qualidade Sênior do Service Desk da FindUP, responsável por auditar atendimentos do cliente Leo Madeiras.
                    Ouça a gravação anexada com rigor técnico.
                    
                    Forneça um relatório detalhado com os seguintes tópicos:

                    1. **Contexto da Ligação:** Qual foi o problema, dúvida ou solicitação?
                    2. **Registro (Ticket):** O analista repassou algum número de chamado/incidente? Se sim, coloque em negrito. Se não, escreva "Nenhum número repassado".
                    3. **Termômetro de Sentimento:** Satisfeito, Neutro ou Frustrado? (Identifique palavras de alerta como: demora, muito tempo, ruim, inaceitável, urgente, travado, prejuízo).
                    4. **Desfecho da Chamada:** Como foi finalizado? Resolvido em linha ou escalonado?
                    """
                    
                    model = genai.GenerativeModel(NOME_MODELO)
                    response = model.generate_content([audio_enviado, prompt])
                    
                    st.success("Auditoria concluída com sucesso!")
                    st.markdown("### 📊 Relatório FindUP")
                    st.markdown(response.text)
                    
                    # Limpeza
                    genai.delete_file(audio_enviado.name)
                    os.remove(caminho_temp)

except Exception as e:
    st.error(f"Erro de conexão com o Drive: {e}")


