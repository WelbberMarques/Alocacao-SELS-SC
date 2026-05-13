"""
Preferencias por usuario - salvas localmente e no Supabase
"""
import json
import os
from pathlib import Path

PREFS_FILE = Path.home() / ".cpb_alocacao_prefs.json"

DEFAULTS = {
    "tema": "escuro",           # escuro / claro / alto_contraste
    "fonte_log": 9,             # tamanho da fonte do log
    "headless": True,           # modo silencioso Chrome
    "notif_som": True,          # som ao concluir
    "backup_pasta": "",         # pasta de backup automatico
    "ultima_planilha": "",      # ultima planilha usada (desativado por ora)
}

TEMAS = {
    "escuro": {
        "BG": "#0a0a0a", "CARD": "#111111", "CARD2": "#181818",
        "BORDER": "#2c2c2c", "ACCENT": "#555555", "SUCCESS": "#4a4a4a",
        "WARNING": "#5a5a5a", "ERROR_C": "#666666", "TEXT": "#c8c8c8",
        "TEXT_DIM": "#707070", "TEXT_MUTED": "#3a3a3a", "WHITE": "#c8c8c8",
        "LOG_BG": "#0d0d0d", "LOG_OK": "#5a5a5a", "LOG_ERRO": "#888888",
        "LOG_INFO": "#666666", "LOG_WARN": "#707070", "LOG_HEAD": "#aaaaaa",
    },
    "claro": {
        "BG": "#f0f0f0", "CARD": "#ffffff", "CARD2": "#e8e8e8",
        "BORDER": "#cccccc", "ACCENT": "#555555", "SUCCESS": "#4a7a4a",
        "WARNING": "#7a6a2a", "ERROR_C": "#8a3a3a", "TEXT": "#1a1a1a",
        "TEXT_DIM": "#555555", "TEXT_MUTED": "#999999", "WHITE": "#1a1a1a",
        "LOG_BG": "#fafafa", "LOG_OK": "#2a6a2a", "LOG_ERRO": "#8a2a2a",
        "LOG_INFO": "#2a2a8a", "LOG_WARN": "#7a5a0a", "LOG_HEAD": "#1a1a1a",
    },
    "alto_contraste": {
        "BG": "#000000", "CARD": "#0a0a0a", "CARD2": "#111111",
        "BORDER": "#ffffff", "ACCENT": "#ffffff", "SUCCESS": "#00ff00",
        "WARNING": "#ffff00", "ERROR_C": "#ff0000", "TEXT": "#ffffff",
        "TEXT_DIM": "#cccccc", "TEXT_MUTED": "#888888", "WHITE": "#ffffff",
        "LOG_BG": "#000000", "LOG_OK": "#00ff00", "LOG_ERRO": "#ff4444",
        "LOG_INFO": "#4444ff", "LOG_WARN": "#ffff00", "LOG_HEAD": "#ffffff",
    },
}


def carregar(username: str = "") -> dict:
    prefs = dict(DEFAULTS)
    try:
        if PREFS_FILE.exists():
            dados = json.loads(PREFS_FILE.read_text())
            user_prefs = dados.get(username, dados.get("_global", {}))
            prefs.update(user_prefs)
    except Exception:
        pass
    return prefs


def salvar(prefs: dict, username: str = ""):
    try:
        dados = {}
        if PREFS_FILE.exists():
            dados = json.loads(PREFS_FILE.read_text())
        dados[username or "_global"] = prefs
        PREFS_FILE.write_text(json.dumps(dados, indent=2))
    except Exception:
        pass


def get_tema(nome: str) -> dict:
    return TEMAS.get(nome, TEMAS["escuro"])
