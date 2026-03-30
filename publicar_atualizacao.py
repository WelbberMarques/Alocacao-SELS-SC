"""
Script para publicar atualizacoes no Supabase Storage.
Execute este script no seu computador quando quiser atualizar o app.

Uso:
    python publicar_atualizacao.py 1.1.0
"""
import sys
import os
import json
import hashlib
import requests
from pathlib import Path

SUPABASE_URL = "SUA_SUPABASE_URL"
SERVICE_KEY  = "SUA_SERVICE_KEY"
BUCKET       = "updates"

ARQUIVOS = [
    "app.py",
    "site_scraper.py",
    "excel_writer.py",
    "xml_parser.py",
    "auth.py",
    "login.py",
    "main.py",
    "painel_master.py",
    "notificacao.py",
    "app_icon.ico",
    "relatorio_pdf.py",
    "updater.py",
]


def _headers(content_type="application/octet-stream"):
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": content_type,
    }


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _upload(nome: str, conteudo: bytes) -> bool:
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{nome}"
    r = requests.post(url, headers=_headers(), data=conteudo, timeout=30)
    if not r.ok:
        # Tenta upsert se ja existir
        r = requests.put(url, headers={**_headers(),
                         "x-upsert": "true"}, data=conteudo, timeout=30)
    return r.ok


def publicar(nova_versao: str):
    pasta = Path(__file__).parent
    print(f"\nPublicando versao {nova_versao}...")

    arquivos_md5 = {}
    enviados = 0

    for nome in ARQUIVOS:
        path = pasta / nome
        if not path.exists():
            print(f"  AVISO: {nome} nao encontrado, pulando.")
            continue

        conteudo = path.read_bytes()
        md5 = _md5(path)

        print(f"  Enviando {nome}...", end=" ")
        if _upload(nome, conteudo):
            arquivos_md5[nome] = md5
            enviados += 1
            print("OK")
        else:
            print("FALHOU")

    # Publica version.json
    version_json = json.dumps({
        "versao":   nova_versao,
        "arquivos": arquivos_md5
    }, indent=2).encode()

    print(f"  Enviando version.json...", end=" ")
    if _upload("version.json", version_json):
        print("OK")
    else:
        print("FALHOU")

    print(f"\nPublicacao concluída: {enviados}/{len(ARQUIVOS)} arquivo(s) enviados.")
    print(f"Versao publicada: {nova_versao}")
    print("Os usuarios receberam a atualizacao na proxima vez que abrirem o app.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python publicar_atualizacao.py <versao>")
        print("Exemplo: python publicar_atualizacao.py 1.1.0")
        sys.exit(1)
    publicar(sys.argv[1])
