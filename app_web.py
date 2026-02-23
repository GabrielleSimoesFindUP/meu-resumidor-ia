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

# 🛑 O ID DA SUA PASTA DO DRIVE (JÁ PREENCHIDO):
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
    
    page_token = None
    while True:
        resultados = service.files().list(
            q=query, 
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token
        ).execute()
        
        itens = resultados.get('files', [])
        
        for item in itens:
            # Se for PASTA, entra nela (recursão)
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                arquivos_audio.extend(listar_arquivos_drive(service, item['id']))
            else:
                # Se for ARQUIVO, verifica se é áudio
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
st.set_page_config(layout="wide") # Deixa a página mais larga para caber o Dashboard
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
            
            # Divide a tela em duas colunas
            coluna_esquerda, coluna_direita = st.columns(2)
            
            with coluna_esquerda:
                st.markdown("### 🎵 Gravação Selecionada")
                st.info(f"Arquivo: **{nome_selecionado}**")
                btn_analisar = st.button("▶️ Ouvir e Analisar com IA", use_container_width=True)
            
            # Quando o botão for apertado, a mágica acontece
            if btn_analisar:
                with coluna_esquerda: # Mantém os avisos de carregamento na esquerda
                    file_id = opcoes[nome_selecionado]
                    
                    with st.spinner("📥 Baixando áudio do Google Drive..."):
                        conteudo_audio = baixar_audio_drive(service, file_id)
                        
                        extensao = os.path.splitext(nome_selecionado)[1]
                        if not extensao: extensao = ".mp3"
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix=extensao) as tmp:
                            tmp.write(conteudo_audio)
                            caminho_temp = tmp.name
                        
                        # Mostra o player para você poder ouvir o áudio também!
                        st.audio(conteudo_audio, format=f"audio/{extensao.replace('.', '')}")
                            
                    with st.spinner("🧠 A IA está ouvindo a ligação..."):
                        audio_enviado = genai.upload_file(path=caminho_temp)
                        
                        # --- O NOVO PROMPT EXIGINDO O NOME DO ANALISTA ---
                        prompt = """
                        Você é um Analista de Qualidade Sênior do Service Desk da FindUP, focado no cliente Leo Madeiras.
                        Ouça a gravação anexada com rigor técnico e forneça um relatório estruturado:

                        1. **🧑‍💻 Analista Responsável:** Identifique o nome do atendente que realizou o suporte (preste atenção na saudação inicial, ex: "FindUP, [Nome] bom dia"). Se não for possível escutar o nome, escreva "Não identificado".
                        2. **📝 Contexto da Ligação:** Qual foi o problema, dúvida ou solicitação do usuário?
                        3. **🎫 Registro (Ticket):** O analista repassou algum número de chamado ou incidente? Se sim, coloque em negrito. Se não, escreva "Nenhum número repassado".
                        4. **🌡️ Termômetro de Sentimento:** O cliente estava Satisfeito, Neutro ou Frustrado/Irritado? (Identifique palavras de alerta como: demora, muito tempo, ruim, inaceitável, urgente, travado, prejuízo). Justifique.
                        5. **✅ Desfecho da Chamada:** Como foi finalizado? O problema foi resolvido em linha (FCR) ou escalonado para outra equipe?
                        """
                        
                        model = genai.GenerativeModel(NOME_MODELO)
                        response = model.generate_content([audio_enviado, prompt])
                        
                        # Limpeza dos arquivos temporários
                        genai.delete_file(audio_enviado.name)
                        os.remove(caminho_temp)
                
                # Joga o resultado pronto na coluna da direita!
                with coluna_direita:
                    st.success("Auditoria concluída com sucesso!")
                    st.markdown("### 📋 Ficha de Monitoria (QA)")
                    st.markdown(response.text)

# O bendito "except" que tinha sumido:
except Exception as e:
    st.error(f"Erro no sistema: {e}")
