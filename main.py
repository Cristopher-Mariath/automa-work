import os
import math
import time
import shutil
import threading
import subprocess
import urllib.parse
import webbrowser
from collections import deque

import cv2
import numpy as np
import pyautogui
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# =====================================================================
# CONFIGURAÇÕES GERAIS
# =====================================================================
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

CAM_W, CAM_H = 640, 480
SCREEN_W, SCREEN_H = pyautogui.size()

MARGEM = 100
SUAVIZACAO = 5
FRAMES_ESTAVEIS = 6
COOLDOWN_GESTO = 1.0
DIST_CLIQUE = 20          # usado no scroll (dois dedos colados, em pixels)
COOLDOWN_CLIQUE = 0.4

# --- Clique por pinça (ponta do indicador encostando na ponta do polegar) ---
# A distância é dividida pelo tamanho da mão (pulso -> base do dedo médio),
# então funciona perto ou longe da câmera.
PINCA_ON = 0.25    # razão abaixo da qual a pinça é considerada "fechada" (clica)
PINCA_OFF = 0.40   # razão acima da qual a pinça é considerada "aberta" (histerese)
TEMPO_SEGURAR = 1.0       # segundos com a pinça fechada para ativar o modo segurar (arrastar)
FRAMES_ATRASO_CLIQUE = 5  # clica na posição de alguns frames atrás (evita o cursor "fugir" ao pinçar)

# Se esquerda/direita aparecerem trocadas na tela, mude para True
INVERTER_MAOS = False
# Se "Frente"/"Tras" aparecerem trocados na tela, mude para True
INVERTER_ORIENTACAO = False

# Se True, as URLs (modo jutsu) abrem no Opera em vez do navegador padrão
ABRIR_URL_NO_OPERA = False

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

FONTE = cv2.FONT_HERSHEY_SIMPLEX


# =====================================================================
# AÇÕES
# =====================================================================
def atalho(*teclas):
    """Cria uma ação que aperta um atalho de teclado. Ex.: atalho("ctrl", "r")"""
    def _acao():
        pyautogui.hotkey(*teclas)
    return _acao


def tecla(nome):
    """Cria uma ação que aperta uma única tecla. Ex.: tecla("enter")"""
    def _acao():
        pyautogui.press(nome)
    return _acao


def _caminho_opera():
    return next((p for p in OPERA_PATHS if os.path.exists(p)), None) or shutil.which("opera")


def abrir_opera():
    caminho = _caminho_opera()
    if caminho:
        subprocess.Popen([caminho])
    else:
        print("Opera não encontrado. Ajuste OPERA_PATHS no início do código.")


def abrir_url(url):
    """Cria uma ação que abre uma URL. Ex.: abrir_url("https://youtube.com")"""
    def _acao():
        caminho = _caminho_opera() if ABRIR_URL_NO_OPERA else None
        if caminho:
            subprocess.Popen([caminho, url])
        else:
            webbrowser.open(url)
    return _acao


def youtube_busca(termo):
    """Cria uma ação que abre a busca do YouTube. Ex.: youtube_busca("katon jutsu")"""
    return abrir_url("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(termo))


def nova_aba():
    pyautogui.hotkey("ctrl", "t")


def fechar_aba():
    pyautogui.hotkey("ctrl", "w")


def proxima_aba():
    pyautogui.hotkey("ctrl", "tab")


def aba_anterior():
    pyautogui.hotkey("ctrl", "shift", "tab")


_aviso_acentos = False


def digitar_texto(texto):
    """Digita um texto no teclado. Acentos precisam de 'pip install pyperclip'."""
    global _aviso_acentos
    if texto.isascii():
        pyautogui.write(texto, interval=0.01)
        return
    try:
        import pyperclip
        antigo = pyperclip.paste()
        pyperclip.copy(texto)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.05)
        pyperclip.copy(antigo)
    except Exception:
        import unicodedata
        if not _aviso_acentos:
            print("Dica: instale 'pyperclip' (pip install pyperclip) para digitar acentos.")
            _aviso_acentos = True
        sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
        pyautogui.write(sem_acento, interval=0.01)


_lock_voz = threading.Lock()


def falar_voz(texto):
    """Fala o texto em voz alta (precisa de 'pip install pyttsx3')."""
    try:
        import pyttsx3
    except ImportError:
        print("Para voz instale: pip install pyttsx3")
        return

    def _rodar():
        with _lock_voz:
            try:
                motor = pyttsx3.init()
                motor.say(texto)
                motor.runAndWait()
            except Exception as e:
                print(f"Erro na voz: {e}")

    threading.Thread(target=_rodar, daemon=True).start()


# =====================================================================
# DICIONÁRIO DE GESTOS - MODO ÁREA DE TRABALHO (MÃO DIREITA)
# =====================================================================
# Para adicionar um atalho novo, basta incluir uma linha:
#   (polegar, indicador, médio, anelar, mindinho, orientação): ("Descrição", função)
#
# 1 = dedo levantado, 0 = dedo abaixado
# orientação: "Frente" (palma) ou "Tras" (costas da mão)
#
# Funções: use uma das acima ou crie na hora com atalho("ctrl", "r").
GESTOS_DIREITA = {
    (1, 1, 1, 1, 1, "Frente"): ("Abrir Opera", abrir_opera),
    (0, 1, 0, 0, 0, "Frente"): ("Nova aba", nova_aba),
    (0, 1, 1, 0, 0, "Frente"): ("Proxima aba", proxima_aba),
    (0, 0, 0, 0, 1, "Frente"): ("Aba anterior", aba_anterior),
    (0, 1, 0, 0, 0, "Tras"): ("Fechar aba (Costas da Mao)", fechar_aba),
    # Exemplos (descomente para usar):
    # (0, 1, 1, 1, 0, "Frente"): ("Recarregar", atalho("ctrl", "r")),
    # (1, 0, 0, 0, 0, "Frente"): ("Voltar", atalho("alt", "left")),
    # (1, 1, 0, 0, 0, "Frente"): ("Reabrir aba", atalho("ctrl", "shift", "t")),
}


# =====================================================================
# DETECÇÃO DE DEDOS E ORIENTAÇÃO
# =====================================================================
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def detectar_orientacao(lm, tipo_mao):
    """
    Detecta se a mão está virada para Frente (Palma) ou Trás (Dorso)
    baseado na posição horizontal da base do indicador (ponto 5) e do mindinho (ponto 17).
    """
    x_base_indicador = lm[5][0]
    x_base_mindinho = lm[17][0]

    if tipo_mao == "Right":
        frente = x_base_indicador > x_base_mindinho
    else:
        frente = x_base_indicador < x_base_mindinho

    if INVERTER_ORIENTACAO:
        frente = not frente
    return "Frente" if frente else "Tras"


def dedos_levantados(lm):
    """lm = lista de 21 pontos (x, y) em pixels. Retorna (polegar, ind, med, anel, mind)."""
    polegar = 1 if dist(lm[4], lm[17]) > dist(lm[3], lm[17]) else 0

    resultado = [polegar]
    for ponta, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        resultado.append(1 if dist(lm[ponta], lm[0]) > dist(lm[pip], lm[0]) * 1.15 else 0)
    return tuple(resultado)


def razao_pinca(lm):
    """Distância ponta do polegar <-> ponta do indicador, relativa ao tamanho da mão."""
    tamanho_mao = max(dist(lm[0], lm[9]), 1)
    return dist(lm[4], lm[8]) / tamanho_mao


# =====================================================================
# SINAIS (gestos com UMA ou DUAS mãos) - usados no menu e no modo jutsu
# =====================================================================
def sinal(direita=None, esquerda=None):
    """
    Define um sinal de mão. Cada mão pode ser:
      - None                       -> ignora essa mão
      - (pol, ind, med, anel, min) -> só os dedos
      - (pol, ind, med, anel, min, "Frente"/"Tras") -> dedos + orientação
    Se informar as duas mãos, as duas precisam estar no gesto ao mesmo tempo.
    """
    return {"Right": direita, "Left": esquerda}


def sinal_casa(padrao, maos):
    exigidas = {tipo: p for tipo, p in padrao.items() if p is not None}
    if not exigidas:
        return False
    for tipo, p in exigidas.items():
        m = maos.get(tipo)
        if m is None:
            return False
        atual = m["dedos"] if len(p) == 5 else m["dedos"] + (m["orientacao"],)
        if atual != tuple(p):
            return False
    return True


def identificar_sinal(maos, sinais):
    """Retorna o nome do primeiro sinal que casa (sinais de duas mãos têm prioridade)."""
    ordenados = sorted(sinais.items(), key=lambda kv: -sum(v is not None for v in kv[1].values()))
    for nome, padrao in ordenados:
        if sinal_casa(padrao, maos):
            return nome
    return None


# =====================================================================
# CONFIGURAÇÃO DOS MODOS  (edite à vontade!)
# =====================================================================

# ---------- Gatilho do menu (abre o seletor de modos) ----------
# Padrão: hangloose (polegar + mindinho) com as DUAS mãos ao mesmo tempo.
# Fazer de novo dentro do seletor cancela e volta ao modo anterior.
SINAL_MENU = sinal(direita=(1, 0, 0, 0, 1), esquerda=(1, 0, 0, 0, 1))
FRAMES_MENU = 10          # frames segurando o sinal para abrir o menu
COOLDOWN_MENU = 1.5       # segundos entre aberturas do menu
SELETOR_TIMEOUT = 10.0    # segundos sem escolher nada = volta ao modo anterior
SEQ_TIMEOUT = 3.0         # segundos máximos entre um sinal e outro de uma sequência

MODO_INICIAL = "area_de_trabalho"

# ---------- Sinais usados para ESCOLHER o modo ----------
SINAIS_MENU = {
    "punho":  sinal(direita=(0, 0, 0, 0, 0)),
    "um":     sinal(direita=(0, 1, 0, 0, 0)),
    "dois":   sinal(direita=(0, 1, 1, 0, 0)),
    "tres":   sinal(direita=(0, 1, 1, 1, 0)),
    "quatro": sinal(direita=(0, 1, 1, 1, 1)),
    "cinco":  sinal(direita=(1, 1, 1, 1, 1)),
}

# ---------- Sequência -> modo ----------
# Troque as sequências como quiser (pode ter 1, 2, 3... sinais, de uma ou duas mãos).
# Cuidado: uma sequência não deve ser o começo de outra mais longa.
SEQUENCIAS_MODOS = {
    ("punho", "um"):     "area_de_trabalho",
    ("punho", "dois"):   "modo_3d",
    ("punho", "tres"):   "fala",
    ("punho", "quatro"): "jutsu",
}

# ---------- MODO 3D ----------
CONFIG_3D = {
    "botao_rotacao": "left",        # "left", "middle" (Blender) ou "right"
    "sens_rotacao": 2.0,            # quanto o cursor anda por pixel de movimento da mão
    "sens_zoom": 0.08,              # cliques de scroll por pixel de variação entre as mãos
    "inverter_zoom": False,
    "zoom_com_duas_maos": True,     # pinça nas duas mãos = zoom (afasta/aproxima)
    "mao_rotacao": "qualquer",      # "qualquer", "Left" ou "Right"
}

# ---------- MODO FALA ----------
CONFIG_FALA = {
    "digitar": True,                # digita o texto no teclado
    "voz_a_cada_sinal": False,      # fala cada sinal em voz alta
    "frames": 8,                    # frames estáveis para registrar um sinal
    "cooldown": 0.8,                # segundos entre sinais
}
# Valores aceitos: "texto"  |  ("Descrição", "texto")  |  função  |  ("Descrição", função)
# Tokens especiais: "<APAGAR>", "<ENTER>", "<LIMPAR>", "<FALAR>" (fala o texto acumulado)
FALAS_DIREITA = {
    (0, 1, 0, 0, 0, "Frente"): "A",
    (0, 1, 1, 0, 0, "Frente"): "B",
    (0, 1, 1, 1, 0, "Frente"): "C",
    (1, 1, 1, 1, 1, "Frente"): "Ola ",
    (0, 0, 0, 0, 1, "Frente"): "Tudo bem? ",
    (1, 0, 0, 0, 0, "Frente"): "Obrigado ",
}
FALAS_ESQUERDA = {
    (0, 0, 0, 0, 0, "Frente"): "<APAGAR>",
    (0, 1, 0, 0, 0, "Frente"): "<ENTER>",
    (1, 1, 1, 1, 1, "Frente"): "<FALAR>",
}

# ---------- MODO JUTSU ----------
# Sinais de mão do modo jutsu (exemplos com as duas mãos; troque pelos seus).
SINAIS_JUTSU = {
    "tigre":    sinal(direita=(0, 1, 1, 0, 0), esquerda=(0, 1, 1, 0, 0)),
    "cobra":    sinal(direita=(0, 0, 0, 0, 0), esquerda=(0, 0, 0, 0, 0)),
    "cavalo":   sinal(direita=(0, 1, 0, 0, 0), esquerda=(0, 1, 0, 0, 0)),
    "dragao":   sinal(direita=(1, 1, 1, 1, 1), esquerda=(1, 1, 1, 1, 1)),
    "carneiro": sinal(direita=(0, 1, 1, 1, 1), esquerda=(0, 1, 1, 1, 1)),
}
# Sequência de sinais -> ("Nome do jutsu", ação)
JUTSUS = {
    ("tigre", "cobra", "cavalo"):    ("Katon", youtube_busca("Naruto Katon Goukakyuu no Jutsu")),
    ("dragao", "carneiro", "tigre"): ("Chidori", youtube_busca("Naruto Chidori")),
    ("cavalo", "dragao"):            ("Rasengan", youtube_busca("Naruto Rasengan")),
}


# =====================================================================
# HUD
# =====================================================================
def hud(frame, linhas, y0=250, cor=(255, 255, 255)):
    for i, linha in enumerate(linhas):
        cv2.putText(frame, linha, (20, y0 + 22 * i), FONTE, 0.55, cor, 2)


# =====================================================================
# GERENCIADOR DE GESTOS
# =====================================================================
class GerenciadorGestos:
    def __init__(self, mapa, frames=None, cooldown=None):
        self.mapa = mapa
        self.frames = FRAMES_ESTAVEIS if frames is None else frames
        self.cooldown = COOLDOWN_GESTO if cooldown is None else cooldown
        self.candidato = None
        self.contagem = 0
        self.ja_disparou = False
        self.ultimo_disparo = 0

    def atualizar(self, combinacao_atual):
        if combinacao_atual != self.candidato:
            self.candidato = combinacao_atual
            self.contagem = 0
            self.ja_disparou = False
            return None

        self.contagem += 1
        if (
            self.candidato in self.mapa
            and self.contagem >= self.frames
            and not self.ja_disparou
            and time.time() - self.ultimo_disparo > self.cooldown
        ):
            descricao, funcao = self.mapa[self.candidato]
            funcao()
            self.ja_disparou = True
            self.ultimo_disparo = time.time()
            return descricao
        return None

    def resetar(self):
        self.candidato = None
        self.contagem = 0
        self.ja_disparou = False


class GatilhoSinal:
    """Dispara UMA vez quando uma condição fica verdadeira por N frames (precisa soltar para repetir)."""

    def __init__(self, frames, cooldown):
        self.frames = frames
        self.cooldown = cooldown
        self.contagem = 0
        self.disparado = False
        self.ultimo = 0

    def atualizar(self, ativo):
        if not ativo:
            self.contagem = 0
            self.disparado = False
            return False
        self.contagem += 1
        if self.contagem >= self.frames and not self.disparado and time.time() - self.ultimo > self.cooldown:
            self.disparado = True
            self.ultimo = time.time()
            return True
        return False


class ReconhecedorSequencia:
    """
    Recebe, a cada frame, o nome do sinal atual (ou None) e reconhece SEQUÊNCIAS de sinais.
    sequencias = {("sinal1", "sinal2", ...): valor}
    Quando uma sequência completa é feita, atualizar() retorna (sequencia, valor).
    Para repetir o mesmo sinal em seguida, solte a mão (ou troque de sinal) entre eles.
    """

    def __init__(self, sequencias, frames=None, timeout=None):
        self.sequencias = {tuple(k): v for k, v in sequencias.items()}
        self.frames = FRAMES_ESTAVEIS if frames is None else frames
        self.timeout = SEQ_TIMEOUT if timeout is None else timeout
        self.resetar()

    def resetar(self):
        self.buffer = []
        self.candidato = None
        self.contagem = 0
        self.confirmado = False
        self.ultimo_t = time.time()

    def atualizar(self, nome):
        agora = time.time()
        if self.buffer and agora - self.ultimo_t > self.timeout:
            self.buffer = []

        if nome is None:
            self.candidato = None
            self.contagem = 0
            self.confirmado = False
            return None

        if nome != self.candidato:
            self.candidato = nome
            self.contagem = 0
            self.confirmado = False
            return None

        self.contagem += 1
        if self.contagem < self.frames or self.confirmado:
            return None

        self.confirmado = True
        self.buffer.append(nome)
        self.ultimo_t = agora
        return self._checar()

    def _checar(self):
        atual = tuple(self.buffer)
        if atual in self.sequencias:
            self.buffer = []
            return atual, self.sequencias[atual]
        if not any(seq[:len(atual)] == atual for seq in self.sequencias):
            ultimo = atual[-1:]
            comeca_alguma = any(seq[:1] == ultimo for seq in self.sequencias)
            self.buffer = list(ultimo) if comeca_alguma else []
        return None


class DetectorPinca:
    """Pinça (polegar + indicador) com histerese, para uma mão."""

    def __init__(self):
        self.pincando = False

    def atualizar(self, lm):
        razao = razao_pinca(lm)
        if self.pincando and razao > PINCA_OFF:
            self.pincando = False
        elif not self.pincando and razao < PINCA_ON:
            self.pincando = True
        return self.pincando


# =====================================================================
# MOUSE (MÃO ESQUERDA)
# =====================================================================
class ControleMouse:
    def __init__(self):
        self.x_ant, self.y_ant = SCREEN_W / 2, SCREEN_H / 2
        self.ultimo_clique = 0
        self.y_scroll_ant = None
        self.pincando = False
        self.pinca_t0 = None      # instante em que a pinça fechou
        self.pinca_pos = None     # posição do cursor quando a pinça fechou
        self.segurando = False    # True = botão do mouse pressionado (modo segurar)
        self.historico = deque(maxlen=FRAMES_ATRASO_CLIQUE)

    def soltar(self):
        """Solta o botão do mouse se estiver no modo segurar."""
        if self.segurando:
            pyautogui.mouseUp()
            self.segurando = False

    def resetar(self):
        """Chamado quando a mão some ou muda de modo."""
        self.soltar()
        self.y_scroll_ant = None
        self.pincando = False
        self.pinca_t0 = None
        self.pinca_pos = None
        self.historico.clear()

    def atualizar_pinca(self, lm):
        """Atualiza a pinça com histerese. Retorna (pincando, inicio, fim, razao)."""
        razao = razao_pinca(lm)
        antes = self.pincando
        if self.pincando and razao > PINCA_OFF:
            self.pincando = False
        elif not self.pincando and razao < PINCA_ON:
            self.pincando = True
        return self.pincando, (self.pincando and not antes), (antes and not self.pincando), razao

    def mover(self, x_ind, y_ind, w, h):
        x = np.clip(np.interp(x_ind, (MARGEM, w - MARGEM), (0, SCREEN_W)), 0, SCREEN_W - 1)
        y = np.clip(np.interp(y_ind, (MARGEM, h - MARGEM), (0, SCREEN_H)), 0, SCREEN_H - 1)
        self.x_ant += (x - self.x_ant) / SUAVIZACAO
        self.y_ant += (y - self.y_ant) / SUAVIZACAO
        pyautogui.moveTo(self.x_ant, self.y_ant)

    def processar(self, lm, dedos, orientacao, frame):
        h, w, _ = frame.shape
        x_ind, y_ind = lm[8]
        status = "Pausado"

        cv2.rectangle(frame, (MARGEM, MARGEM), (w - MARGEM, h - MARGEM), (255, 0, 255), 2)

        dedao, indicador, medio, anelar, mindinho = dedos[0], dedos[1], dedos[2], dedos[3], dedos[4]

        if orientacao == "Tras":
            self.resetar()
            return "Pausado (Mão Invertida)"

        pincando, inicio_pinca, fim_pinca, _ = self.atualizar_pinca(lm)

        # Ao pinçar, o indicador se curva e pode deixar de contar como "levantado",
        # por isso a pinça também ativa o modo mouse.
        modo_mouse = (indicador == 1 or pincando) and medio == 0

        if modo_mouse:
            self.y_scroll_ant = None

            # Linha entre polegar e indicador (feedback visual da pinça)
            cor_pinca = (0, 255, 0) if pincando else (255, 0, 255)
            cv2.line(frame, lm[4], lm[8], cor_pinca, 2)

            if inicio_pinca:
                self.pinca_t0 = time.time()
                # Posição de alguns frames atrás: ao fechar a pinça o indicador se mexe.
                self.pinca_pos = self.historico[0] if self.historico else (self.x_ant, self.y_ant)
                self.x_ant, self.y_ant = self.pinca_pos
                pyautogui.moveTo(int(self.x_ant), int(self.y_ant))

            if pincando and self.pinca_t0 is not None:
                tempo = time.time() - self.pinca_t0

                if self.segurando:
                    # Modo segurar ativo: arrasta o objeto junto com o dedo
                    self.mover(x_ind, y_ind, w, h)
                    cv2.circle(frame, (x_ind, y_ind), 18, (0, 0, 255), cv2.FILLED)
                    status = "SEGURANDO (solte a pinça para soltar)"

                elif tempo >= TEMPO_SEGURAR:
                    # Passou de 1s: aperta e mantém o botão do mouse
                    pyautogui.moveTo(int(self.x_ant), int(self.y_ant))
                    pyautogui.mouseDown()
                    self.segurando = True
                    status = "MODO SEGURAR ATIVADO"

                else:
                    # Pinça recente: cursor parado + anel de progresso
                    angulo = int(360 * tempo / TEMPO_SEGURAR)
                    cv2.ellipse(frame, (x_ind, y_ind), (20, 20), -90, 0, angulo, (0, 255, 255), 3)
                    status = f"Pinça {tempo:.1f}s"

            elif fim_pinca:
                if self.segurando:
                    self.soltar()
                    status = "Soltou"
                elif time.time() - self.ultimo_clique > COOLDOWN_CLIQUE:
                    # Pinça curta (< TEMPO_SEGURAR) = clique, feito ao abrir a pinça
                    px, py = self.pinca_pos if self.pinca_pos else (self.x_ant, self.y_ant)
                    pyautogui.click(int(px), int(py))
                    self.ultimo_clique = time.time()
                    cv2.circle(frame, (x_ind, y_ind), 25, (0, 255, 0), cv2.FILLED)
                    status = "CLIQUE!"
                else:
                    status = "Pinça (Aguardando Cooldown)"
                self.pinca_t0 = None
                self.pinca_pos = None
                self.historico.clear()

            else:
                # Movimento normal
                self.mover(x_ind, y_ind, w, h)
                self.historico.append((self.x_ant, self.y_ant))
                cv2.circle(frame, (x_ind, y_ind), 12, (255, 0, 255), cv2.FILLED)
                status = "Movendo"

        else:
            # Saiu do modo mouse: nunca deixa o botão preso
            self.soltar()
            self.pincando = False
            self.pinca_t0 = None
            self.pinca_pos = None
            self.historico.clear()

            if indicador == 1 and medio == 1:
                if dist(lm[8], lm[12]) < DIST_CLIQUE:
                    status = "Rolando Página"
                    if self.y_scroll_ant is None:
                        self.y_scroll_ant = y_ind

                    variacao_y = self.y_scroll_ant - y_ind
                    if abs(variacao_y) > 2:
                        pyautogui.scroll(int(variacao_y * 2))

                    self.y_scroll_ant = y_ind
                    cv2.circle(frame, (x_ind, y_ind), 15, (0, 255, 255), cv2.FILLED)
                else:
                    self.y_scroll_ant = None
                    status = "Dedos Separados"
            else:
                self.y_scroll_ant = None
                status = "Inativo"

        return status


# =====================================================================
# MODOS
# =====================================================================
class Modo:
    """
    Base de todo modo. Para criar um modo novo:
      1. herde de Modo e implemente processar(maos, frame)
      2. registre em criar_modos()
      3. (opcional) coloque uma sequência para ele em SEQUENCIAS_MODOS
    `maos` = {"Left": {...}, "Right": {...}} com "lm", "dedos" e "orientacao".
    """
    nome = "Modo"
    gerenciador = None

    def ao_entrar(self):
        pass

    def ao_sair(self):
        pass

    def processar(self, maos, frame):
        pass


class ModoAreaDeTrabalho(Modo):
    """Código padrão: mão esquerda = mouse, mão direita = atalhos (GESTOS_DIREITA)."""
    nome = "Area de trabalho"

    def __init__(self):
        self.mouse = ControleMouse()
        self.gestos = GerenciadorGestos(GESTOS_DIREITA)
        self.ultimo_comando, self.ultimo_comando_t = None, 0

    def ao_sair(self):
        self.mouse.resetar()
        self.gestos.resetar()

    def processar(self, maos, frame):
        if "Left" in maos:
            m = maos["Left"]
            status = self.mouse.processar(m["lm"], m["dedos"], m["orientacao"], frame)
            cv2.putText(frame, f"ESQ: {status}", (20, 40), FONTE, 0.7, (0, 255, 0), 2)
        else:
            self.mouse.resetar()

        if "Right" in maos:
            m = maos["Right"]
            combinacao_atual = m["dedos"] + (m["orientacao"],)

            cv2.putText(frame, f"DIR: {m['dedos']} | {m['orientacao']}", (20, 75),
                        FONTE, 0.7, (255, 0, 0), 2)

            disparou = self.gestos.atualizar(combinacao_atual)
            if disparou:
                self.ultimo_comando = disparou
                self.ultimo_comando_t = time.time()
        else:
            self.gestos.resetar()

        if self.ultimo_comando and (time.time() - self.ultimo_comando_t < 1.5):
            cv2.putText(frame, f"Acao: {self.ultimo_comando}", (20, 110), FONTE, 0.7, (0, 0, 255), 2)
        else:
            self.ultimo_comando = None


class Modo3D(Modo):
    """
    Manipulação 3D com pinça (polegar + indicador):
      - pinça em UMA mão e mover  = girar o modelo (segura o botão do mouse e arrasta)
      - pinça nas DUAS mãos       = zoom (afastar/aproximar as mãos = scroll)
    Deixe o cursor em cima do visualizador 3D antes de entrar no modo
    (use o modo Área de trabalho para posicionar). Ajuste em CONFIG_3D.
    """
    nome = "Manipulacao 3D"

    def __init__(self):
        self.detectores = {}
        self.segurando = False
        self.pos_ant = None
        self.resto = [0.0, 0.0]
        self.dist_ant = None

    def _soltar(self):
        if self.segurando:
            pyautogui.mouseUp(button=CONFIG_3D["botao_rotacao"])
            self.segurando = False
        self.pos_ant = None
        self.resto = [0.0, 0.0]

    def ao_sair(self):
        self._soltar()
        self.dist_ant = None
        self.detectores.clear()

    def processar(self, maos, frame):
        for tipo, det in self.detectores.items():
            if tipo not in maos:
                det.pincando = False

        pontos = {}
        for tipo, m in maos.items():
            lm = m["lm"]
            det = self.detectores.setdefault(tipo, DetectorPinca())
            if det.atualizar(lm):
                ponto = ((lm[4][0] + lm[8][0]) // 2, (lm[4][1] + lm[8][1]) // 2)
                pontos[tipo] = ponto
                cv2.line(frame, lm[4], lm[8], (0, 255, 0), 2)
                cv2.circle(frame, ponto, 10, (0, 255, 0), cv2.FILLED)

        status = "Aguardando pinca (junte polegar e indicador)"

        if len(pontos) == 2 and CONFIG_3D["zoom_com_duas_maos"]:
            self._soltar()
            a, b = pontos["Left"], pontos["Right"]
            d = dist(a, b)
            cv2.line(frame, a, b, (0, 255, 255), 2)
            if self.dist_ant is None:
                self.dist_ant = d
            else:
                sinal_zoom = -1 if CONFIG_3D["inverter_zoom"] else 1
                passos = int((d - self.dist_ant) * CONFIG_3D["sens_zoom"] * sinal_zoom)
                if passos:
                    pyautogui.scroll(passos)
                    self.dist_ant = d
            status = "ZOOM (afaste/aproxime as maos)"

        elif pontos:
            self.dist_ant = None
            escolha = CONFIG_3D["mao_rotacao"]
            if escolha == "qualquer":
                tipo = next(iter(pontos))
            else:
                tipo = escolha if escolha in pontos else None

            if tipo is None:
                self._soltar()
            else:
                x, y = pontos[tipo]
                if not self.segurando:
                    pyautogui.mouseDown(button=CONFIG_3D["botao_rotacao"])
                    self.segurando = True
                    self.pos_ant = (x, y)
                else:
                    self.resto[0] += (x - self.pos_ant[0]) * CONFIG_3D["sens_rotacao"]
                    self.resto[1] += (y - self.pos_ant[1]) * CONFIG_3D["sens_rotacao"]
                    mx, my = int(self.resto[0]), int(self.resto[1])
                    self.resto[0] -= mx
                    self.resto[1] -= my
                    if mx or my:
                        pyautogui.moveRel(mx, my)
                    self.pos_ant = (x, y)
                status = "ROTACIONANDO (mova a mao)"
        else:
            self._soltar()
            self.dist_ant = None

        hud(frame, [status], y0=250, cor=(0, 255, 255))


class ModoFala(Modo):
    """
    Cada sinal de mão vira uma letra/palavra/frase (FALAS_DIREITA e FALAS_ESQUERDA).
    O texto é digitado no teclado e/ou falado (CONFIG_FALA).
    """
    nome = "Fala"

    def __init__(self):
        self.texto = ""
        self.ultimo = ""
        self.ultimo_t = 0
        self.gestos = {
            "Right": GerenciadorGestos(self._montar(FALAS_DIREITA),
                                       CONFIG_FALA["frames"], CONFIG_FALA["cooldown"]),
            "Left": GerenciadorGestos(self._montar(FALAS_ESQUERDA),
                                      CONFIG_FALA["frames"], CONFIG_FALA["cooldown"]),
        }

    def _montar(self, tabela):
        return {combo: self._normalizar(valor) for combo, valor in tabela.items()}

    def _normalizar(self, valor):
        if isinstance(valor, tuple):
            descricao, acao = valor
        else:
            descricao, acao = None, valor
        if isinstance(acao, str):
            texto = acao
            acao = lambda t=texto: self.dizer(t)
            descricao = descricao or texto.strip()
        elif descricao is None:
            descricao = getattr(acao, "__name__", "acao")
        return descricao, acao

    def dizer(self, texto):
        if texto == "<APAGAR>":
            self.texto = self.texto[:-1]
            if CONFIG_FALA["digitar"]:
                pyautogui.press("backspace")
        elif texto == "<ENTER>":
            if CONFIG_FALA["digitar"]:
                pyautogui.press("enter")
        elif texto == "<LIMPAR>":
            self.texto = ""
        elif texto == "<FALAR>":
            if self.texto.strip():
                falar_voz(self.texto)
            self.texto = ""
        else:
            self.texto += texto
            if CONFIG_FALA["digitar"]:
                digitar_texto(texto)
            if CONFIG_FALA["voz_a_cada_sinal"]:
                falar_voz(texto)

    def ao_sair(self):
        for g in self.gestos.values():
            g.resetar()

    def processar(self, maos, frame):
        h, w, _ = frame.shape
        for tipo, gerenciador in self.gestos.items():
            if tipo in maos:
                m = maos[tipo]
                disparou = gerenciador.atualizar(m["dedos"] + (m["orientacao"],))
                if disparou:
                    self.ultimo = disparou
                    self.ultimo_t = time.time()
            else:
                gerenciador.resetar()

        linhas = ["MODO FALA"]
        if self.ultimo and time.time() - self.ultimo_t < 1.5:
            linhas.append(f"Sinal: {self.ultimo}")
        hud(frame, linhas, y0=250, cor=(0, 255, 255))
        cv2.putText(frame, f"Texto: {self.texto[-40:]}", (20, h - 50), FONTE, 0.7, (255, 255, 0), 2)


class ModoJutsu(Modo):
    """
    Faça a sequência de sinais (SINAIS_JUTSU) de um jutsu (JUTSUS) para executar a ação
    (por padrão, abre uma busca no YouTube).
    """
    nome = "Jutsu"

    def __init__(self):
        self.reconhecedor = ReconhecedorSequencia(JUTSUS)
        self.ultimo = None
        self.ultimo_t = 0

    def ao_entrar(self):
        self.reconhecedor.resetar()

    def ao_sair(self):
        self.reconhecedor.resetar()

    def processar(self, maos, frame):
        sinal_atual = identificar_sinal(maos, SINAIS_JUTSU)
        resultado = self.reconhecedor.atualizar(sinal_atual)
        if resultado:
            _, (nome, acao) = resultado
            acao()
            self.ultimo = nome
            self.ultimo_t = time.time()

        linhas = [
            "MODO JUTSU",
            f"Sinal atual: {sinal_atual}",
            f"Sequencia: {' > '.join(self.reconhecedor.buffer)}",
        ]
        if self.ultimo and time.time() - self.ultimo_t < 3.0:
            linhas.append(f"JUTSU: {self.ultimo}!")
        hud(frame, linhas, y0=250, cor=(0, 165, 255))


class ModoSeletor(Modo):
    """Aberto pelo hangloose com as duas mãos. Faça a sequência (SEQUENCIAS_MODOS) para escolher o modo."""
    nome = "Seletor de modos"

    def __init__(self):
        self.reconhecedor = ReconhecedorSequencia(SEQUENCIAS_MODOS)
        self.t_entrada = 0

    def ao_entrar(self):
        self.reconhecedor.resetar()
        self.t_entrada = time.time()

    def processar(self, maos, frame):
        sinal_atual = identificar_sinal(maos, SINAIS_MENU)
        resultado = self.reconhecedor.atualizar(sinal_atual)
        if resultado:
            _, chave = resultado
            self.gerenciador.trocar(chave)
            return

        if time.time() - self.t_entrada > SELETOR_TIMEOUT:
            self.gerenciador.voltar()
            return

        linhas = [
            "SELETOR - faca a sequencia (hangloose cancela)",
            f"Sinal atual: {sinal_atual}   Sequencia: {' > '.join(self.reconhecedor.buffer)}",
        ]
        for seq, chave in SEQUENCIAS_MODOS.items():
            modo = self.gerenciador.modos.get(chave)
            linhas.append(f"  {' > '.join(seq)}  =  {modo.nome if modo else chave + ' (nao registrado)'}")
        hud(frame, linhas, y0=250, cor=(255, 255, 0))


class GerenciadorModos:
    def __init__(self, inicial):
        self.modos = {}
        self.inicial = inicial
        self.atual_chave = None
        self.anterior = None
        self.gatilho_menu = GatilhoSinal(FRAMES_MENU, COOLDOWN_MENU)

    def registrar(self, chave, modo):
        modo.gerenciador = self
        self.modos[chave] = modo
        return self

    def iniciar(self):
        self.trocar(self.inicial)

    def trocar(self, chave):
        if chave not in self.modos:
            print(f"Modo '{chave}' não está registrado.")
            return
        if self.atual_chave is not None:
            self.modos[self.atual_chave].ao_sair()
        self.atual_chave = chave
        self.modos[chave].ao_entrar()
        print(f"Modo: {self.modos[chave].nome}")

    def voltar(self):
        self.trocar(self.anterior or self.inicial)

    def encerrar(self):
        if self.atual_chave is not None:
            self.modos[self.atual_chave].ao_sair()

    def processar(self, maos, frame):
        h, w, _ = frame.shape

        if self.gatilho_menu.atualizar(sinal_casa(SINAL_MENU, maos)):
            if self.atual_chave == "seletor":
                self.voltar()
            else:
                self.anterior = self.atual_chave
                self.trocar("seletor")

        modo = self.modos[self.atual_chave]
        modo.processar(maos, frame)
        cv2.putText(frame, f"MODO: {modo.nome}", (w - 290, 25), FONTE, 0.55, (255, 255, 255), 2)


def criar_modos():
    """Para adicionar um modo novo, registre-o aqui."""
    modos = GerenciadorModos(MODO_INICIAL)
    modos.registrar("area_de_trabalho", ModoAreaDeTrabalho())
    modos.registrar("modo_3d", Modo3D())
    modos.registrar("fala", ModoFala())
    modos.registrar("jutsu", ModoJutsu())
    modos.registrar("seletor", ModoSeletor())
    return modos


# =====================================================================
# PROGRAMA PRINCIPAL
# =====================================================================
def criar_detector():
    if not os.path.exists(MODELO):
        raise FileNotFoundError(f"Modelo não encontrado: {MODELO}")
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
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)

    detector = criar_detector()
    modos = criar_modos()
    modos.iniciar()

    t0 = time.time()
    ultimo_ts = -1

    print("AutomaHouse iniciada! Aperte 'q' na janela da câmera para sair.")
    print("Hangloose com as duas mãos abre o seletor de modos.")

    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts = int((time.time() - t0) * 1000)
        if ts <= ultimo_ts:
            ts = ultimo_ts + 1
        ultimo_ts = ts
        resultado = detector.detect_for_video(mp_img, ts)

        maos = {}
        if resultado.hand_landmarks:
            for lms, handed in zip(resultado.hand_landmarks, resultado.handedness):
                tipo = handed[0].category_name
                if INVERTER_MAOS:
                    tipo = "Right" if tipo == "Left" else "Left"
                lm = [(int(p.x * w), int(p.y * h)) for p in lms]

                orientacao = detectar_orientacao(lm, tipo)

                maos[tipo] = {
                    "lm": lm,
                    "dedos": dedos_levantados(lm),
                    "orientacao": orientacao
                }

                for a, b in CONEXOES:
                    cv2.line(frame, lm[a], lm[b], (0, 255, 0), 2)
                for p in lm:
                    cv2.circle(frame, p, 4, (0, 0, 255), cv2.FILLED)

        cv2.putText(frame, f"Maos detectadas: {len(maos)}", (20, h - 20),
                    FONTE, 0.6, (255, 255, 255), 2)
        for i, (tipo, m) in enumerate(maos.items()):
            cv2.putText(frame, f"{tipo} ({m['orientacao']}): {m['dedos']}", (20, 140 + 30 * i),
                        FONTE, 0.7, (0, 255, 255), 2)

        modos.processar(maos, frame)

        cv2.imshow("AutomaHouse", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    modos.encerrar()  # garante que o botão do mouse não fique preso
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()