import streamlit as st
import google.generativeai as genai
import os
import tempfile
import json
import io
import datetime
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- CONFIGURAÇÕES GERAIS ---
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
NOME_MODELO = 'models/gemini-2.5-flash-lite'

# 🛑 IDs DO GOOGLE (Não esqueça de preencher a planilha!):
ID_DA_PASTA = "1nCR3mW_pL57XGIX4R2N6NzrMv6ljK_ce"
ID_DA_PLANILHA = "1mjtN76sLF861TRKjOYel3mtyTO18xUrzLzxJsSb8_ic" # <--- PREENCHA SEU ID AQUI!

# --- FUNÇÕES DO GOOGLE (DRIVE E SHEETS) ---
@st.cache_resource
def conectar_drive():
    cred_json = st.secrets["GOOGLE_CREDENTIALS_JSON"]
    cred_dict = json.loads(cred_json)
    creds = service_account.Credentials.from_service_account_info(
        cred_dict, scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

def conectar_planilha():
    cred_json = st.secrets["GOOGLE_CREDENTIALS_JSON"]
    cred_dict = json.loads(cred_json)
    gc = gspread.service_account_from_dict(cred_dict)
    planilha = gc.open_by_key(ID_DA_PLANILHA).sheet1
    return planilha

def listar_arquivos_drive(service, folder_id):
    arquivos_audio = []
    extensoes_permitidas = ('.mp3', '.wav', '.m4a', '.ogg')
    query = f"'{folder_id}' in parents and trashed=false"
    page_token = None
    while True:
        resultados = service.files().list(q=query, fields="nextPageToken, files(id, name, mimeType)", pageToken=page_token).execute()
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

# --- MEMÓRIA DA PÁGINA (SESSION STATE) ---
if 'relatorio_gerado' not in st.session_state:
    st.session_state['relatorio_gerado'] = ""
if 'arquivo_analisado' not in st.session_state:
    st.session_state['arquivo_analisado'] = ""
if 'dropdown_atual' not in st.session_state:
    st.session_state['dropdown_atual'] = ""

# --- INTERFACE WEB ---
st.set_page_config(layout="wide")
st.title("☁️ Auditoria Automática - FindUP")
st.write("Selecione uma ligação do Google Drive, analise com a IA e salve o QA na sua planilha.")

try:
    service = conectar_drive()
    arquivos = listar_arquivos_drive(service, ID_DA_PASTA)
    
    if not arquivos:
        st.warning("Nenhum arquivo de áudio encontrado na pasta do Drive.")
    else:
        opcoes = {arq['name']: arq['id'] for arq in arquivos}
        nome_selecionado = st.selectbox("Selecione a gravação (Leo Madeiras):", ["-- Escolha uma gravação --"] + list(opcoes.keys()))

        if nome_selecionado != st.session_state['dropdown_atual']:
            st.session_state['relatorio_gerado'] = ""
            st.session_state['dropdown_atual'] = nome_selecionado

        if nome_selecionado != "-- Escolha uma gravação --":
            
            coluna_esquerda, coluna_direita = st.columns(2)
            
            with coluna_esquerda:
                st.markdown("### 🎵 Gravação Selecionada")
                st.info(f"Arquivo (Unique ID): **{nome_selecionado}**")
                btn_analisar = st.button("▶️ Ouvir e Analisar com IA", use_container_width=True)
            
            if btn_analisar:
                with coluna_esquerda:
                    file_id = opcoes[nome_selecionado]
                    
                    with st.spinner("📥 Baixando áudio do Google Drive..."):
                        conteudo_audio = baixar_audio_drive(service, file_id)
                        extensao = os.path.splitext(nome_selecionado)[1] or ".mp3"
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix=extensao) as tmp:
                            tmp.write(conteudo_audio)
                            caminho_temp = tmp.name
                        
                        st.audio(conteudo_audio, format=f"audio/{extensao.replace('.', '')}")
                            
                    with st.spinner("🧠 A IA está ouvindo a ligação..."):
                        audio_enviado = genai.upload_file(path=caminho_temp)
                        
                        prompt = """
                        Você é um Analista de Qualidade Sênior do Service Desk de TI da FindUP. Você audita chamados técnicos das lojas "Leo Madeiras".
                        
                        🚨 REGRA ABSOLUTA DE INÍCIO DE CHAMADA: A ligação REAL SÓ COMEÇA quando você ouvir a frase exata: "Leo madeiras...". TUDO antes dessa frase é tempo de espera da URA. O atendimento humano só inicia na palavra "Leo madeiras". A voz do analista que fala isso estará MUITO BAIXA.

                        1. **⏱️ Início do Atendimento:** Avance o áudio ignorando a URA. Encontre o momento EXATO em que a palavra "Leo madeiras" é dita pela primeira vez por uma voz humana muito baixa. Informe essa minutagem exata (ex: 03:45). Se você não ouvir "Leo madeiras", a ligação é apenas abandono na fila.
                        2. **🧑‍💻 Analista Responsável:** Imediatamente após falar "Leo madeiras", o analista vai dizer o nome dele. Escreva esse nome. Se inaudível devido ao áudio baixo, escreva: "Não identificado".
                        3. **📝 Contexto da Ligação (Problema de TI):** Qual é a falha TÉCNICA ou de SISTEMA que a loja está enfrentando? Ignore a parte de logística/produtos e foque no problema de TI.
                        4. **🎫 Registro (Ticket):** O analista repassou algum número de chamado? Se sim, coloque em negrito.
                        5. **🌡️ Termômetro de Sentimento:** O cliente estava Satisfeito, Neutro ou Frustrado/Irritado com a falha?
                        6. **✅ Desfecho da Chamada:** O problema de TI foi resolvido na hora (FCR) ou precisou ser escalonado?
                        """
                        
                        model = genai.GenerativeModel(NOME_MODELO)
                        response = model.generate_content([audio_enviado, prompt])
                        
                        try:
                            st.session_state['relatorio_gerado'] = response.text
                            st.session_state['arquivo_analisado'] = nome_selecionado
                        except ValueError:
                            st.session_state['relatorio_gerado'] = "⚠️ A IA devolveu um relatório vazio."
                        
                        genai.delete_file(audio_enviado.name)
                        os.remove(caminho_temp)

            if st.session_state['relatorio_gerado'] != "":
                with coluna_direita:
                    st.success("Auditoria concluída com sucesso!")
                    st.markdown("### 📋 Ficha de Monitoria (QA)")
                    st.markdown(st.session_state['relatorio_gerado'])
                    
                    st.markdown("---")
                    st.markdown("### ✍️ Preencha os Dados Finais")
                    
                    # Campos baseados na sua planilha
                    status_ligacao = st.selectbox("Status:", ["Auditado", "Em Revisão", "Crítico", "Abandono na Fila"])
                    obs_manuais = st.text_area("Observações do QA:")
                    
                    if st.button("💾 Salvar na Planilha", type="primary"):
                        with st.spinner("Conectando ao Google Sheets..."):
                            aba = conectar_planilha()
                            data_hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                            
                            # 🚨 A MÁGICA ACONTECE AQUI! Mapeamento exato das suas 8 colunas:
                            # id | id_ura_cdr | data_criacao | resposta | id_humano | uniqueId | Status | Observações
                            linha_para_salvar = [
                                "-",                                      # 1. id (Vazio/Traço)
                                "-",                                      # 2. id_ura_cdr (Vazio/Traço)
                                data_hora,                                # 3. data_criacao
                                st.session_state['relatorio_gerado'],     # 4. resposta (Relatório da IA)
                                "-",                                      # 5. id_humano (Vazio/Traço)
                                st.session_state['arquivo_analisado'],    # 6. uniqueId (Nome do Arquivo)
                                status_ligacao,                           # 7. Status
                                obs_manuais                               # 8. Observações
                            ]
                            
                            aba.append_row(linha_para_salvar)
                            st.success("✅ Avaliação salva perfeitamente nas 8 colunas da planilha!")

except Exception as e:
    st.error(f"Erro no sistema: {e}")

