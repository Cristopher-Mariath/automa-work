import cv2
import pyautogui
from cvzone.HandTrackingModule import HandDetector
from cvzone.PoseModule import PoseDetector

# Inicializa a câmera
cap = cv2.VideoCapture(0)

# Inicializa os detectores (Mão e Corpo) de forma leve
detector_mao = HandDetector(detectionCon=0.7, maxHands=1)
detector_corpo = PoseDetector(detectionCon=0.7)

comando_executado = False

# Criando os padrões de dedos para o sistema não bugar na resposta do robô
MAO_ABERTA       = [1, 1, 1, 1, 1]
S_INDICADOR      = [0, 1, 0, 0, 0]
SINAL_DE_DOIS    = [0, 1, 1, 0, 0]
MAO_FECHADA      = [0, 0, 0, 0, 0]

print("AutomaHouse Iniciada!")

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break

    # Inverte a imagem para efeito espelho
    frame = cv2.flip(frame, 1)

    # 1. CAPTURA DOS MOVIMENTOS DO CORPO
    frame = detector_corpo.findPose(frame, draw=True)
    lmList_corpo, bboxInfo = detector_corpo.findPosition(frame, draw=False)
    
    # 2. CAPTURA DOS MOVIMENTOS DOS DEDOS
    hands, frame = detector_mao.findHands(frame, draw=True)

    # =========================================================================
    # DETECÇÃO E SEPARAÇÃO DE FUNÇÕES: MÃO ESQUERDA VS MÃO DIREITA
    # =========================================================================
    if hands:
        # Pegamos a primeira mão que aparece na tela
        mao_detectada = hands[0]
        
        # Descobre se a mão na tela é a esquerda ou a direita
        tipo_mao = mao_detectada["type"]  # Retorna "Left" ou "Right"
        
        # Pega a lista de dedos levantados
        dedos = detector_mao.fingersUp(mao_detectada)

        # ---------------------------------------------------------------------
        # SE FOR A SUA MÃO DIREITA REAL (A IA lê como "Left" por causa do espelho)
        # FUNCIONALIDADE: CONTROLE DO MOUSE (PINÇA)
        # ---------------------------------------------------------------------
        if tipo_mao == "Rigth":
            lmList = mao_detectada["lmList"]
            
            # Coordenadas X e Y do indicador (ponto 8) e polegar (ponto 4)
            x_indicador, y_indicador = lmList[8][0], lmList[8][1]
            x_polegar, y_polegar = lmList[4][0], lmList[4][1]
            
            # Calcula a distância da pinça
            distancia, info_linha, frame = detector_mao.findDistance((x_indicador, y_indicador), (x_polegar, y_polegar), frame)
            
            # Se fechar a pinça, move o mouse continuamente (Limiar de 40 pixels)
            if distancia < 40:
                cv2.putText(frame, "MAO DIREITA: MOVENDO MOUSE", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
                largura_tela, altura_tela = pyautogui.size()
                
                # Mapeamento do tamanho da imagem da câmera para a tela inteira do monitor
                mouse_x = int((x_indicador / 640) * largura_tela)
                mouse_y = int((y_indicador / 480) * altura_tela)
                
                pyautogui.moveTo(mouse_x, mouse_y, _pause=False)

        # ---------------------------------------------------------------------
        # SE FOR A SUA MÃO ESQUERDA REAL (A IA lê como "Right" por causa do espelho)
        # FUNCIONALIDADE: COMANDOS DO SISTEMA (ABRIR CHROME, NOTEPAD, ABAS)
        # ---------------------------------------------------------------------
        elif tipo_mao == "Left":
            cv2.putText(frame, "MAO ESQUERDA: CAPTURANDO GESTO", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            if not comando_executado:
                # Gesto 1: Mão Esquerda Aberta -> Abre o Chrome
                if dedos == MAO_ABERTA:
                    print("Mão Esquerda Aberta -> Abrindo Chrome")
                    pyautogui.hotkey('win', 'r')
                    pyautogui.sleep(0.3)
                    pyautogui.write('opera')
                    pyautogui.press('enter')
                    comando_executado = True

                # Gesto 2: Mão Esquerda só o Indicador -> Abre o Bloco de Notas
                elif dedos == S_INDICADOR:
                    print("Mão Esquerda com Indicador -> Abrindo Bloco de Notas")
                    pyautogui.hotkey('win', 'r')
                    pyautogui.sleep(0.3)
                    pyautogui.write('notepad')
                    pyautogui.press('enter')
                    comando_executado = True
                    
                # Gesto 3: Mão Esquerda com Sinal de 2 -> Abre Nova Aba (Ctrl + T)
                elif dedos == SINAL_DE_DOIS:
                    print("Mão Esquerda com Sinal de 2 -> Abrindo Nova Aba no Programa")
                    pyautogui.hotkey('ctrl', 't')
                    comando_executado = True

    # =========================================================================
    # LUGAR 2: COMANDOS DO CORPO
    # =========================================================================
    if lmList_corpo and not comando_executado:
        nariz_y = lmList_corpo[0][2]
        pulso_direito_y = lmList_corpo[10][2]

        # Braço Direito Levantado acima do nariz -> Aumenta o volume
        if pulso_direito_y < nariz_y:
            print("Braço Direito Levantado -> Aumentando Volume")
            pyautogui.press("volumeup", presses=5)
            comando_executado = True

    # =========================================================================
    # CONDIÇÃO DE RESET: LIBERA PARA O PRÓXIMO COMANDO
    # =========================================================================
    if hands:
        dedos = detector_mao.fingersUp(hands[0])
        # Se fechar a mão inteira, reseta a trava do comando
        if dedos == MAO_FECHADA:
            comando_executado = False
    
    elif lmList_corpo:
        # Se o pulso direito estiver abaixo do ombro (ponto 6), reseta do mesmo jeito
        if lmList_corpo[10][2] > lmList_corpo[6][2]:
            comando_executado = False

    # Mostra o resultado na tela
    # cv2.imshow("AutomaHouse - Multi-Comandos", frame)

    # Fecha o programa ao apertar 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
