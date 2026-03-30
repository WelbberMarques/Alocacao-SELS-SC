"""
Auto-update - CPB Alocacao
Verifica versao no Supabase Storage e atualiza arquivos automaticamente.
"""
import os
import sys
import json
import hashlib
import requests
import subprocess
import tempfile
import shutil
from pathlib import Path

SUPABASE_URL = "SUA_SUPABASE_URL"
SUPABASE_KEY = "SUA_SUPABASE_KEY"
BUCKET       = "updates"
VERSAO_LOCAL = "0.0.0"  # sera sobrescrita pelo .app_version

# Arquivos que podem ser atualizados remotamente
ARQUIVOS_ATUALIZAVEIS = [
    "app.py",
    "site_scraper.py",
    "excel_writer.py",
    "xml_parser.py",
    "auth.py",
    "login.py",
    "main.py",
    "painel_master.py",
    "notificacao.py",
]


def _pasta_app() -> Path:
    """Retorna a pasta onde estao os arquivos do app."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }


def _get_versao_remota() -> dict | None:
    """Busca o arquivo version.json do Storage."""
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/version.json"
        r = requests.get(url, headers=_headers(), timeout=6)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def _baixar_arquivo(nome: str, destino: Path) -> bool:
    """Baixa um arquivo do Storage para o destino."""
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{nome}"
        r = requests.get(url, headers=_headers(), timeout=15)
        if r.ok:
            destino.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False


def _md5(path: Path) -> str:
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()
    except Exception:
        return ""


def verificar_e_atualizar(log_fn=None) -> bool:
    """
    Verifica se ha atualizacao disponivel e aplica se necessario.
    Retorna True se o app deve reiniciar.
    """
    def log(msg):
        if log_fn:
            log_fn(msg, "info")

    log("Verificando atualizacoes...")

    remoto = _get_versao_remota()
    if not remoto:
        log("Sem conexao ou sem atualizacoes disponíveis.")
        return False

    versao_local = get_versao_local()
    versao_nova  = remoto.get("versao", versao_local)
    arquivos     = remoto.get("arquivos", {})

    if not _versao_maior(versao_nova, versao_local):
        log(f"App atualizado (v{versao_local}).")
        return False

    log(f"Nova versao: {versao_nova} (atual: {versao_local})")

    pasta = _pasta_app()
    atualizados = []

    for nome, md5_remoto in arquivos.items():
        if nome not in ARQUIVOS_ATUALIZAVEIS:
            continue
        local = pasta / nome
        if local.exists() and _md5(local) == md5_remoto:
            continue  # Arquivo identico, pula

        log(f"Atualizando {nome}...")
        tmp = pasta / f"{nome}.tmp"
        if _baixar_arquivo(nome, tmp):
            # Faz backup do arquivo atual
            bak = pasta / f"{nome}.bak"
            if local.exists():
                shutil.copy2(local, bak)
            # Substitui
            tmp.replace(local)
            atualizados.append(nome)
            log(f"  {nome} atualizado.")
        else:
            log(f"  Falha ao baixar {nome}.")
            if tmp.exists():
                tmp.unlink()

    if atualizados:
        # Atualiza versao local
        _salvar_versao_local(versao_nova)
        log(f"Atualizacao concluída ({len(atualizados)} arquivo(s)). Reiniciando...")
        return True

    return False


def _versao_maior(v1: str, v2: str) -> bool:
    """Retorna True se v1 > v2 (ex: '1.1.0' > '1.0.0')."""
    try:
        t1 = tuple(int(x) for x in v1.split("."))
        t2 = tuple(int(x) for x in v2.split("."))
        return t1 > t2
    except Exception:
        return False


def _salvar_versao_local(versao: str):
    pasta = _pasta_app()
    cfg   = pasta / ".app_version"
    cfg.write_text(versao)


def get_versao_local() -> str:
    pasta = _pasta_app()
    cfg   = pasta / ".app_version"
    if cfg.exists():
        v = cfg.read_text().strip()
        return v if v else "0.0.0"
    return "0.0.0"  # sem arquivo = sempre atualiza


def reiniciar():
    """Reinicia o processo — funciona com exe e .py."""
    import os
    exe = sys.executable
    if getattr(sys, "frozen", False):
        subprocess.Popen([exe])
    else:
        subprocess.Popen([exe] + sys.argv)
    os.kill(os.getpid(), 9)
