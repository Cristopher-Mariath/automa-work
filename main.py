import os
import math
import time
import shutil
import subprocess

import cv2
import numpy as np
import pyautogui
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# =====================================================================
# CONFIGURAÇÕES
# =====================================================================
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

CAM_W, CAM_H = 640, 480
SCREEN_W, SCREEN_H = pyautogui.size()

MARGEM = 100
SUAVIZACAO = 5
FRAMES_ESTAVEIS = 6
COOLDOWN_GESTO = 1.0
DIST_CLIQUE = 40
COOLDOWN_CLIQUE = 0.4

# Se esquerda/direita aparecerem trocadas na tela, mude para True
INVERTER_MAOS = False

MODELO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")

OPERA_PATHS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera GX\opera.exe"),
    r"C:\Program Files\Opera\opera.exe",
    r"C:\Program Files (x86)\Opera\opera.exe",
]

CONEXOES = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]


# =====================================================================
# AÇÕES
# =====================================================================
def abrir_opera():
    caminho = next((p for p in OPERA_PATHS if os.path.exists(p)), None) or shutil.which("opera")
    if caminho:
        subprocess.Popen([caminho])
    else:
        print("Opera não encontrado. Ajuste OPERA_PATHS no início do código.")


def nova_aba():
    pyautogui.hotkey("ctrl", "t")


def fechar_aba():
    pyautogui.hotkey("ctrl", "w")


def proxima_aba():
    pyautogui.hotkey("ctrl", "tab")


def aba_anterior():
    pyautogui.hotkey("ctrl", "shift", "tab")


# Chave = (polegar, indicador, médio, anelar, mindinho)  1 = levantado
GESTOS_DIREITA = {

    #existe 32 combinações possiveis de mao ou seja tem 32 atalhos possiveis

    (1, 1, 1, 1, 1): ("Abrir Opera", abrir_opera),
    (0, 1, 1, 1, 1): ("Abrir Opera", abrir_opera),   # mesmo gesto, polegar meio dobrado
    #(0, 1, 1, 0, 0): ("Nova aba", nova_aba),
    (0, 1, 0, 0, 0): ("Nova aba", nova_aba),
    (0, 1, 1, 1, 0): ("Fechar aba", fechar_aba),
    (0, 1, 1, 0, 0): ("Proxima aba", proxima_aba),
    (0, 0, 0, 0, 1): ("Aba anterior", aba_anterior),
}


# =====================================================================
# DETECÇÃO DE DEDOS 
# =====================================================================
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def dedos_levantados(lm):
    """lm = lista de 21 pontos (x, y) em pixels. Retorna (polegar, ind, med, anel, mind)."""
    # Polegar: ponta mais longe da base do mindinho do que a articulação IP
    polegar = 1 if dist(lm[4], lm[17]) > dist(lm[3], lm[17]) else 0

    # Demais dedos: ponta mais longe do pulso do que a articulação PIP
    resultado = [polegar]
    for ponta, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        resultado.append(1 if dist(lm[ponta], lm[0]) > dist(lm[pip], lm[0]) * 1.15 else 0)
    return tuple(resultado)


# =====================================================================
# GERENCIADOR DE GESTOS
# =====================================================================
class GerenciadorGestos:
    def __init__(self, mapa):
        self.mapa = mapa
        self.candidato = None
        self.contagem = 0
        self.ja_disparou = False
        self.ultimo_disparo = 0

    def atualizar(self, gesto):
        if gesto != self.candidato:
            self.candidato = gesto
            self.contagem = 0
            self.ja_disparou = False
            return None

        self.contagem += 1
        if (
            gesto in self.mapa
            and self.contagem >= FRAMES_ESTAVEIS
            and not self.ja_disparou
            and time.time() - self.ultimo_disparo > COOLDOWN_GESTO
        ):
            descricao, funcao = self.mapa[gesto]
            funcao()
            self.ja_disparou = True
            self.ultimo_disparo = time.time()
            return descricao
        return None

    def resetar(self):
        self.candidato = None
        self.contagem = 0
        self.ja_disparou = False


# =====================================================================
# MOUSE (MÃO ESQUERDA)
# =====================================================================
class ControleMouse:
    def __init__(self):
        self.x_ant, self.y_ant = SCREEN_W / 2, SCREEN_H / 2
        self.ultimo_clique = 0

    def processar(self, lm, dedos, frame):
        h, w, _ = frame.shape
        x_ind, y_ind = lm[8]  
        x_med, y_med = lm[12] 
        status = "Pausado"

        cv2.rectangle(frame, (MARGEM, MARGEM), (w - MARGEM, h - MARGEM), (255, 0, 255), 2)

        indicador, medio = dedos[1], dedos[2]

        # polegar = dedos[0]
        # indicador = dedos[1]
        # medio = dedos[2]
        # anelar = dedos[3]
        # mindinho = dedos[4]w

        if indicador == 1 and medio == 0 :
            x = np.clip(np.interp(x_ind, (MARGEM, w - MARGEM), (0, SCREEN_W)), 0, SCREEN_W - 1)
            y = np.clip(np.interp(y_ind, (MARGEM, h - MARGEM), (0, SCREEN_H)), 0, SCREEN_H - 1)
            self.x_ant += (x - self.x_ant) / SUAVIZACAO
            self.y_ant += (y - self.y_ant) / SUAVIZACAO
            pyautogui.moveTo(self.x_ant, self.y_ant)
            cv2.circle(frame, (x_ind, y_ind), 12, (255, 0, 255), cv2.FILLED)
            status = "Movendo"

        elif indicador == 1  and medio == 1 :
            status = "Clique (junte os dedos)"
            if dist((x_ind, y_ind), (x_med, y_med)) < DIST_CLIQUE \
                    and time.time() - self.ultimo_clique > COOLDOWN_CLIQUE:
                pyautogui.click()
                self.ultimo_clique = time.time()
                cv2.circle(frame, (x_ind, y_ind), 15, (0, 255, 0), cv2.FILLED)
                status = "CLIQUE!"

        return status


# =====================================================================
# PROGRAMA PRINCIPAL
# =====================================================================
def criar_detector():
    if not os.path.exists(MODELO):
        raise FileNotFoundError(f"Modelo não encontrado: {MODELO}")
    # Lê o modelo para a memória (evita problemas com caminhos/acentos no Windows)
    with open(MODELO, "rb") as f:
        buffer = f.read()
    opcoes = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_buffer=buffer),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.7,
        min_tracking_confidence=0.6,
    )
    return vision.HandLandmarker.create_from_options(opcoes)


def main():
    cap = cv2.VideoCapture(0)
    cap.set(3, CAM_W)
    cap.set(4, CAM_H)

    detector = criar_detector()
    mouse = ControleMouse()
    gestos = GerenciadorGestos(GESTOS_DIREITA)

    ultimo_comando, ultimo_comando_t = "", 0
    t0 = time.time()
    ultimo_ts = -1

    print("AutomaHouse iniciada! Aperte 'q' na janela da câmera para sair.")

    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break

        # Espelha antes de detectar (efeito espelho)
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts = int((time.time() - t0) * 1000)
        if ts <= ultimo_ts:
            ts = ultimo_ts + 1
        ultimo_ts = ts
        resultado = detector.detect_for_video(mp_img, ts)

        # Monta as mãos: {"Left": {...}, "Right": {...}}
        maos = {}
        for lms, handed in zip(resultado.hand_landmarks, resultado.handedness):
            tipo = handed[0].category_name  # "Left" ou "Right"
            if INVERTER_MAOS:
                tipo = "Right" if tipo == "Left" else "Left"
            lm = [(int(p.x * w), int(p.y * h)) for p in lms]
            maos[tipo] = {"lm": lm, "dedos": dedos_levantados(lm)}

            # Desenha o esqueleto
            for a, b in CONEXOES:
                cv2.line(frame, lm[a], lm[b], (0, 255, 0), 2)
            for p in lm:
                cv2.circle(frame, p, 4, (0, 0, 255), cv2.FILLED)

        # ---------- DIAGNÓSTICO (sempre visível) ----------
        cv2.putText(frame, f"Maos detectadas: {len(maos)}", (20, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        for i, (tipo, m) in enumerate(maos.items()):
            cv2.putText(frame, f"{tipo}: {m['dedos']}", (20, 140 + 30 * i),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        # ---------- MÃO ESQUERDA: MOUSE ----------
        if "Left" in maos:
            m = maos["Left"]
            status = mouse.processar(m["lm"], m["dedos"], frame)
            cv2.putText(frame, f"ESQ: {status}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # ---------- MÃO DIREITA: COMANDOS ----------
        if "Right" in maos:
            gesto = maos["Right"]["dedos"]
            cv2.putText(frame, f"DIR: {gesto}", (20, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
            disparou = gestos.atualizar(gesto)
            if disparou:
                ultimo_comando, ultimo_comando_t = disparou, time.time()
                print(f"Comando: {disparou}")
        else:
            gestos.resetar()

        if ultimo_comando and time.time() - ultimo_comando_t < 1.5:
            cv2.putText(frame, f">> {ultimo_comando}", (20, 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)

        #cv2.imshow("AutomaHouse - Controle por Gestos", frame)
        #if cv2.waitKey(1) & 0xFF == ord("q"):
        #    break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()