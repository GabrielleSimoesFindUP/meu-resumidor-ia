import streamlit as st
import whisper
import google.generativeai as genai
import os

# --- CONFIGURAÇÕES ---
# Coloque sua chave aqui
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
NOME_MODELO = 'models/gemini-2.5-flash'

# Cache para não precisar carregar o Whisper toda vez que apertar o botão
@st.cache_resource
def carregar_whisper():
    return whisper.load_model("tiny")

# --- INTERFACE WEB ---
st.title("🎙️ Analisador de Chamadas com IA")
st.write("Faça o upload da gravação e receba o relatório detalhado automaticamente.")

# Botão de Upload
arquivo_audio = st.file_uploader("Selecione o áudio (.wav, .mp3, .m4a)", type=["wav", "mp3", "m4a"])

if arquivo_audio is not None:
    # Mostra um player de áudio na tela para você poder ouvir!
    st.audio(arquivo_audio)
    
    if st.button("Gerar Relatório Analítico"):
        
        # Cria uma mensagem de carregamento bonita
        with st.spinner("Ouvindo o áudio e gerando o relatório... Isso pode levar um minutinho!"):
            try:
                # 1. Salvar o arquivo temporariamente para o Whisper conseguir ler
                caminho_temp = "audio_temporario." + arquivo_audio.name.split('.')[-1]
                with open(caminho_temp, "wb") as f:
                    f.write(arquivo_audio.getbuffer())
                
                # 2. Transcrição com Whisper
                model_w = carregar_whisper()
                result = model_w.transcribe(caminho_temp)
                
                # Pegando os tempos (o mesmo código que já funcionou pra você!)
                transcricao_com_tempo = ""
                for segmento in result["segments"]:
                    inicio = int(segmento["start"])
                    fim = int(segmento["end"])
                    transcricao_com_tempo += f"[{inicio}s - {fim}s]: {segmento['text']}\n"
                    
                tempo_total = int(result["segments"][-1]["end"]) if result["segments"] else 0
                minutos, segundos = tempo_total // 60, tempo_total % 60
                tempo_formatado = f"{minutos}m {segundos}s"

                # 3. Resumo com Gemini
                model_g = genai.GenerativeModel(NOME_MODELO)
                
                prompt = f"""
                Você é um Analista de Qualidade Sênior do Service Desk da FindUP, responsável por auditar os atendimentos prestados ao cliente Leo Madeiras.
                Analise a transcrição de áudio abaixo com rigor técnico. Cada linha possui o tempo em segundos [Início - Fim].
                Duração total da chamada: {tempo_formatado} ({tempo_total} segundos).

                Forneça um relatório detalhado, estruturado e direto ao ponto com os seguintes tópicos:

                1. **Contexto da Ligação:** Qual foi o problema, dúvida ou solicitação relatada pelo usuário da Leo Madeiras?
                
                2. **Registro (Ticket):** O analista repassou algum número de chamado, incidente, requisição, ticket ou protocolo para o usuário? 
                   - Se SIM, informe o número exato em negrito. 
                   - Se NÃO, escreva explicitamente: "Nenhum número de chamado foi repassado na gravação".
                
                3. **Termômetro de Sentimento do Cliente:** O cliente demonstrou estar Satisfeito, Neutro ou Frustrado/Irritado? 
                   - Identifique ativamente se o cliente usou palavras de alerta como: "demora", "muito tempo", "esperando", "atendimento ruim", "péssimo", "inaceitável", "absurdo", "urgente", "estou parado", "de novo", "ninguém resolve", "prejuízo", "loja cheia", "travado" ou similares.
                   - Justifique a sua escolha citando trechos ou o tom geral da conversa.
                
                4. **Desfecho da Chamada:** Como o atendimento foi finalizado? O problema foi resolvido em linha (First Call Resolution) ou foi escalonado/encaminhado para outra equipe?
                
                5. **Métricas de Tempo:**
                   - Tempo estimado na URA/Fila de espera:
                   - Tempo estimado de conversa com o analista humano:
                   - Tempo total da gravação: {tempo_formatado}

                Transcrição da chamada:
                {transcricao_com_tempo}
                """
                
                response = model_g.generate_content(prompt)
                
                # 4. Mostrar o resultado na tela
                st.success("Relatório gerado com sucesso!")
                
                # Mostra o texto formatado bonitinho na página web
                st.markdown("### 📊 Resultado da Análise")
                st.markdown(response.text)
                
                # Apaga o arquivo temporário por organização
                os.remove(caminho_temp)
                
            except Exception as e:

                st.error(f"Ops! Ocorreu um erro: {e}")

