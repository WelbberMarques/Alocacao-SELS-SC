"""
Sistema de autenticacao e seguranca - CPB Alocacao
- Login com email/senha
- Niveis: master / membro
- Restricao por cidade (Sao Jose - SC)
- Registro de IP, maquina, cidade
- Bloqueio apos tentativas falhas
- Token de sessao com expiracao
- Armazenamento: arquivos JSON locais (sem Supabase)
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ── Caminhos dos arquivos de dados ────────────────────────────────────────────
import sys, shutil
if getattr(sys, "frozen", False):
    DATA_DIR = Path(sys.executable).parent
else:
    DATA_DIR = Path(__file__).parent.parent  # raiz do projeto, nao core/
DATA_DIR.mkdir(parents=True, exist_ok=True)

def _seed_from_bundle():
    """Copia usuarios.json embutido no exe se ainda nao existir localmente."""
    if not getattr(sys, "frozen", False):
        return
    local = DATA_DIR / "usuarios.json"
    if local.exists():
        return
    bundle = Path(sys._MEIPASS) / "usuarios.json"
    if bundle.exists():
        shutil.copy(bundle, local)

_seed_from_bundle()

_F_USUARIOS     = DATA_DIR / "usuarios.json"
_F_SESSOES      = DATA_DIR / "sessoes.json"
_F_TENTATIVAS   = DATA_DIR / "tentativas_login.json"
_F_DISPOSITIVOS = DATA_DIR / "dispositivos_aprovados.json"
_F_HISTORICO    = DATA_DIR / "historico.json"
_F_CONFIG       = DATA_DIR / "configuracoes.json"

_lock = threading.Lock()

# ── Configuracoes ─────────────────────────────────────────────────────────────
MAX_TENTATIVAS = 5
BLOQUEIO_MIN   = 30
TOKEN_HORAS    = 8
CIDADES_OK = [
    "sao jose", "sao jose - sc", "sao jose-sc",
    "florianopolis", "florianopolis - sc", "florianopolis-sc",
    "ilha de santa catarina",
]
VERSAO = "1.0.0"

MASTER_USERNAME    = os.getenv("MASTER_USERNAME", "master")
MASTER_SENHA_PADRAO = os.getenv("MASTER_SENHA_PADRAO", "")


# ── Helpers de arquivo ────────────────────────────────────────────────────────

def _load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def _save(path: Path, data):
    with _lock:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Garantir master sempre presente ───────────────────────────────────────────

def _ensure_master():
    """Cria o usuario master se ainda nao existir. Nunca e apagado."""
    usuarios = _load(_F_USUARIOS, [])
    for u in usuarios:
        if u.get("papel") == "master":
            return  # ja existe
    usuarios.insert(0, {
        "id":           str(uuid.uuid4()),
        "nome":         "Master",
        "username":     MASTER_USERNAME,
        "senha_hash":   _hash_senha(MASTER_SENHA_PADRAO),
        "papel":        "master",
        "ativo":        True,
        "ultimo_login": None,
        "criado_em":    _now_iso(),
    })
    _save(_F_USUARIOS, usuarios)


# ── Seguranca ─────────────────────────────────────────────────────────────────

def _hash_senha(senha: str) -> str:
    salt = secrets.token_hex(32)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), 310000)
    return f"{salt}:{h.hex()}"


def _verificar_senha(senha: str, hash_armazenado: str) -> bool:
    try:
        salt, h_hex = hash_armazenado.split(":", 1)
        h = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), 310000)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


def _gerar_token() -> str:
    return secrets.token_urlsafe(64)


# Garante master ao iniciar
_ensure_master()


# ── Info da maquina e localizacao ─────────────────────────────────────────────

def _get_ip_externo() -> str:
    apis = [
        "https://api.ipify.org",
        "https://api4.my-ip.io/ip",
        "https://ipv4.icanhazip.com",
    ]
    for url in apis:
        try:
            r = requests.get(url, timeout=5)
            if r.ok:
                return r.text.strip()
        except Exception:
            continue
    return "desconhecido"


def _get_ip_real() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "desconhecido"


def _get_ip() -> str:
    return _get_ip_externo()


def _get_todos_ips() -> dict:
    return {"externo": _get_ip_externo(), "real": _get_ip_real()}


def _get_localizacao(ip: str) -> dict:
    resultado = {
        "cidade": "desconhecida", "pais": "BR",
        "vpn": False, "proxy": False, "hosting": False,
        "tor": False, "suspeito": False, "score_risco": 0,
        "motivos": [],
    }

    def add_risco(pontos, motivo):
        resultado["score_risco"] += pontos
        resultado["motivos"].append(motivo)

    # API 1: ip-api.com
    try:
        fields = "status,city,regionCode,countryCode,proxy,hosting,mobile,isp,org,as,asname"
        r1 = requests.get(f"https://ip-api.com/json/{ip}?fields={fields}", timeout=6)
        if r1.ok:
            d = r1.json()
            if d.get("status") == "success":
                resultado["cidade"] = f"{d.get('city','').lower()} - {d.get('regionCode','').lower()}"
                resultado["pais"]   = d.get("countryCode", "BR").upper()
                if d.get("proxy"):
                    resultado["proxy"] = True
                    add_risco(100, "proxy:ip-api")
                if d.get("hosting"):
                    resultado["hosting"] = True
                    add_risco(100, "hosting:ip-api")
                isp_full = " ".join([
                    d.get("isp",""), d.get("org",""),
                    d.get("as",""), d.get("asname","")
                ]).lower()
                VPN_KEYWORDS = [
                    "vpn","proxy","tunnel","anonymi","tor ","socks",
                    "nordvpn","expressvpn","surfshark","mullvad","protonvpn",
                    "cyberghost","ipvanish","purevpn","windscribe","tunnelbear",
                    "hotspot shield","hidemyass","torguard","private internet access",
                    "pia ","hide.me","zenmate","astrill","vyprvpn","strongvpn",
                    "urban vpn","hola ","psiphon","lantern","ultrasurf","freeproxylist",
                    "amazon aws","amazon ec2","digitalocean","vultr","linode","hetzner",
                    "ovh","choopa","constant","datacamp","serverius","m247","tzulo",
                    "quadranet","voxility","leaseweb","psychz","datapoint","incapsula",
                    "cloudflare","fastly","akamai","zscaler","netskope",
                ]
                for kw in VPN_KEYWORDS:
                    if kw in isp_full:
                        add_risco(80, f"isp_suspeito:{kw.strip()}")
                        resultado["suspeito"] = True
                        break
    except Exception:
        pass

    # API 2: proxycheck.io
    try:
        r2 = requests.get(
            f"https://proxycheck.io/v2/{ip}?vpn=1&asn=1&risk=1&port=1&seen=1",
            timeout=7
        )
        if r2.ok:
            d2 = r2.json()
            ip_data = d2.get(ip, {})
            tipo = ip_data.get("type", "").lower()
            if ip_data.get("proxy") == "yes":
                resultado["proxy"] = True
                add_risco(100, f"proxy:proxycheck:{tipo}")
            if tipo in ("vpn", "tor", "web proxy", "compromised server",
                        "hosted", "socks4", "socks5", "http proxy",
                        "https proxy", "transit"):
                resultado["vpn"] = True
                add_risco(100, f"tipo:{tipo}")
            risk = int(ip_data.get("risk", 0))
            if risk > 0:
                add_risco(risk, f"risk_score:{risk}")
    except Exception:
        pass

    # API 3: ipqualityscore.com
    try:
        _ipqs_key = os.getenv("IPQS_API_KEY", "")
        if not _ipqs_key:
            raise ValueError("IPQS_API_KEY nao configurada")
        r3 = requests.get(
            f"https://ipqualityscore.com/api/json/ip/{_ipqs_key}/{ip}"
            f"?strictness=2&allow_public_access_points=false",
            timeout=7
        )
        if r3.ok:
            d3 = r3.json()
            if d3.get("vpn"):
                resultado["vpn"] = True
                add_risco(100, "vpn:ipqs")
            if d3.get("proxy"):
                resultado["proxy"] = True
                add_risco(100, "proxy:ipqs")
            if d3.get("tor"):
                resultado["tor"] = True
                add_risco(100, "tor:ipqs")
            if d3.get("active_vpn"):
                resultado["vpn"] = True
                add_risco(100, "active_vpn:ipqs")
            if d3.get("active_tor"):
                resultado["tor"] = True
                add_risco(100, "active_tor:ipqs")
            fraud = int(d3.get("fraud_score", 0))
            if fraud >= 50:
                add_risco(fraud, f"fraud_score:{fraud}")
                resultado["suspeito"] = True
    except Exception:
        pass

    # API 4: ipapi.co
    try:
        r4 = requests.get(f"https://ipapi.co/{ip}/json/", timeout=5)
        if r4.ok:
            d4 = r4.json()
            if resultado["cidade"] == "desconhecida":
                c  = d4.get("city","").lower()
                rc = d4.get("region_code","").lower()
                if c:
                    resultado["cidade"] = f"{c} - {rc}"
            org4 = d4.get("org","").lower()
            VPN_ORGS = [
                "vpn","proxy","tunnel","tor","anonymizer","datacenter",
                "hosting","cloud","server","colocation","colo","data center"
            ]
            if any(v in org4 for v in VPN_ORGS):
                add_risco(60, "org_suspeita:ipapi")
                resultado["suspeito"] = True
            pais4 = d4.get("country_code","BR").upper()
            if pais4 and pais4 != "BR":
                resultado["pais"] = pais4
                add_risco(100, f"pais:{pais4}")
    except Exception:
        pass

    if resultado["cidade"] == "desconhecida":
        add_risco(50, "cidade_indeterminada")

    return resultado


def _ip_suspeito(loc: dict) -> tuple[bool, str]:
    if loc.get("tor"):
        return True, "Rede TOR detectada"
    if loc.get("vpn"):
        return True, "VPN detectada"
    if loc.get("proxy"):
        return True, "Proxy detectado"
    if loc.get("hosting"):
        return True, "IP de servidor/datacenter detectado"
    if loc.get("score_risco", 0) >= 33:
        return True, "Conexao suspeita detectada"
    if loc.get("suspeito"):
        return True, "Conexao nao confiavel detectada"
    if loc.get("pais", "BR") not in ("BR", ""):
        return True, f"Acesso fora do Brasil ({loc.get('pais')})"
    return False, ""


def _get_cidade(ip: str) -> str:
    return _get_localizacao(ip).get("cidade", "desconhecida")


def _get_nome_maquina() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "desconhecida"


def _cidade_permitida(cidade: str) -> bool:
    if not cidade or cidade in ("desconhecida", ""):
        return True
    c = cidade.lower().strip()
    return any(ok.lower() in c for ok in CIDADES_OK)


# ── Tentativas de login ───────────────────────────────────────────────────────

def _contar_tentativas(username: str, ip: str) -> int:
    limite = (datetime.now(timezone.utc) - timedelta(minutes=BLOQUEIO_MIN)).isoformat()
    tentativas = _load(_F_TENTATIVAS, [])
    n_user = sum(
        1 for t in tentativas
        if t.get("username") == username
        and not t.get("sucesso")
        and t.get("criado_em", "") >= limite
    )
    n_ip = 0
    if ip and ip not in ("desconhecido", ""):
        n_ip = sum(
            1 for t in tentativas
            if t.get("ip") == ip
            and not t.get("sucesso")
            and t.get("criado_em", "") >= limite
        )
    return max(n_user, n_ip)


def _registrar_tentativa(username: str, ip: str, sucesso: bool,
                         ip_real: str = "", maquina: str = ""):
    tentativas = _load(_F_TENTATIVAS, [])
    tentativas.append({
        "id":        str(uuid.uuid4()),
        "username":  username,
        "ip":        ip,
        "ip_real":   ip_real,
        "maquina":   maquina,
        "sucesso":   sucesso,
        "criado_em": _now_iso(),
    })
    _save(_F_TENTATIVAS, tentativas)


# ── Whitelist de dispositivos ─────────────────────────────────────────────────

def _verificar_whitelist(usuario_id: str, ip: str,
                         ip_real: str, maquina: str, cidade: str) -> str:
    dispositivos = _load(_F_DISPOSITIVOS, [])
    rows = [d for d in dispositivos if d.get("usuario_id") == usuario_id]

    if not rows:
        dispositivos.append({
            "id":         str(uuid.uuid4()),
            "usuario_id": usuario_id,
            "ip":         ip,
            "ip_real":    ip_real,
            "maquina":    maquina,
            "cidade":     cidade,
            "status":     "aprovado",
            "ip_fixo":    True,
            "criado_em":  _now_iso(),
        })
        _save(_F_DISPOSITIVOS, dispositivos)
        return "aprovado"

    aprovados = [d for d in rows if d.get("status") == "aprovado"]

    if not aprovados:
        ja_registrado = any(
            d.get("ip") == ip and d.get("ip_real") == ip_real
            for d in rows
        )
        if not ja_registrado:
            dispositivos.append({
                "id":         str(uuid.uuid4()),
                "usuario_id": usuario_id,
                "ip":         ip,
                "ip_real":    ip_real,
                "maquina":    maquina,
                "cidade":     cidade,
                "status":     "pendente",
                "ip_fixo":    False,
                "criado_em":  _now_iso(),
            })
            _save(_F_DISPOSITIVOS, dispositivos)
        return "pendente"

    ip_fixo = aprovados[0]

    bloqueados = [d for d in rows if d.get("status") == "bloqueado"]
    for b in bloqueados:
        if b.get("ip") == ip or b.get("ip_real") == ip_real:
            return "bloqueado"

    if ip_fixo.get("ip") == ip and ip_fixo.get("ip_real") == ip_real:
        return "aprovado"

    ja_registrado = any(
        d.get("ip") == ip and d.get("ip_real") == ip_real
        for d in rows
    )
    if not ja_registrado:
        dispositivos.append({
            "id":         str(uuid.uuid4()),
            "usuario_id": usuario_id,
            "ip":         ip,
            "ip_real":    ip_real,
            "maquina":    maquina,
            "cidade":     cidade,
            "status":     "bloqueado_auto",
            "ip_fixo":    False,
            "criado_em":  _now_iso(),
        })
        _save(_F_DISPOSITIVOS, dispositivos)
    return "bloqueado"


def listar_dispositivos_pendentes() -> list:
    dispositivos = _load(_F_DISPOSITIVOS, [])
    usuarios     = _load(_F_USUARIOS, [])
    u_map = {u["id"]: u for u in usuarios}
    result = []
    for d in dispositivos:
        if d.get("status") == "pendente":
            u = u_map.get(d.get("usuario_id"), {})
            result.append({**d, "usuarios": {"nome": u.get("nome",""), "username": u.get("username","")}})
    return result


def aprovar_dispositivo(dispositivo_id: str) -> bool:
    dispositivos = _load(_F_DISPOSITIVOS, [])
    for d in dispositivos:
        if d.get("id") == dispositivo_id:
            d["status"] = "aprovado"
            _save(_F_DISPOSITIVOS, dispositivos)
            return True
    return False


def bloquear_dispositivo(dispositivo_id: str) -> bool:
    dispositivos = _load(_F_DISPOSITIVOS, [])
    for d in dispositivos:
        if d.get("id") == dispositivo_id:
            d["status"] = "bloqueado"
            _save(_F_DISPOSITIVOS, dispositivos)
            return True
    return False


def listar_dispositivos_usuario(usuario_id: str) -> list:
    return [d for d in _load(_F_DISPOSITIVOS, []) if d.get("usuario_id") == usuario_id]


# ── Autenticacao ──────────────────────────────────────────────────────────────

class ResultadoLogin:
    def __init__(self, ok=False, usuario=None, papel=None, token=None,
                 erro=None, ip=None, maquina=None, cidade=None, usuario_id=None):
        self.ok         = ok
        self.usuario    = usuario
        self.papel      = papel
        self.token      = token
        self.erro       = erro
        self.ip         = ip
        self.maquina    = maquina
        self.cidade     = cidade
        self.usuario_id = usuario_id


def fazer_login(username: str, senha: str) -> ResultadoLogin:
    username = username.strip().lower()

    maquina = _get_nome_maquina()
    ips     = _get_todos_ips()
    ip      = ips["externo"]
    ip_real = ips["real"]

    # 1. Bloqueio por tentativas
    tentativas = _contar_tentativas(username, ip)
    if tentativas >= MAX_TENTATIVAS:
        _registrar_tentativa(username, ip, False, ip_real, maquina)
        return ResultadoLogin(
            erro=f"Acesso bloqueado por {BLOQUEIO_MIN} minutos.\n"
                 f"Tente novamente mais tarde."
        )

    # 2. Busca usuario
    usuarios = _load(_F_USUARIOS, [])
    usuario  = next((u for u in usuarios
                     if u.get("username") == username and u.get("ativo")), None)
    if not usuario:
        _registrar_tentativa(username, ip, False, ip_real, maquina)
        restantes = MAX_TENTATIVAS - tentativas - 1
        return ResultadoLogin(
            erro=f"Username ou senha incorretos. {restantes} tentativa(s) restante(s)."
        )

    papel = usuario.get("papel", "membro")

    # 3. Verificacoes geograficas (so membros)
    if papel != "master":
        loc    = _get_localizacao(ip)
        cidade = loc.get("cidade", "desconhecida")

        bloqueado, motivo = _ip_suspeito(loc)
        if bloqueado:
            _registrar_tentativa(username, ip, False, ip_real, maquina)
            return ResultadoLogin(
                erro=f"Acesso negado: {motivo}.\n"
                     f"Verifique sua conexao e tente novamente."
            )

        if cidade not in ("desconhecida", "") and not _cidade_permitida(cidade):
            _registrar_tentativa(username, ip, False, ip_real, maquina)
            return ResultadoLogin(
                erro=f"Geolocalizacao invalida: {cidade}.\n"
                     f"Este aplicativo so funciona em Sao Jose - SC ou Florianopolis - SC."
            )

        status_ip = _verificar_whitelist(
            usuario["id"], ip, ip_real, maquina, cidade)
        if status_ip == "bloqueado":
            _registrar_tentativa(username, ip, False, ip_real, maquina)
            return ResultadoLogin(
                erro="Acesso negado: este dispositivo foi bloqueado."
            )
        if status_ip == "pendente":
            _registrar_tentativa(username, ip, False, ip_real, maquina)
            return ResultadoLogin(
                erro="Dispositivo nao reconhecido.\n"
                     "Aguarde aprovacao do administrador."
            )
    else:
        cidade = "master"

    # 4. Verifica senha
    if not _verificar_senha(senha, usuario["senha_hash"]):
        _registrar_tentativa(username, ip, False, ip_real, maquina)
        tentativas += 1
        restantes = MAX_TENTATIVAS - tentativas
        if restantes <= 0:
            return ResultadoLogin(
                erro=f"Acesso bloqueado por {BLOQUEIO_MIN} minutos."
            )
        return ResultadoLogin(
            erro=f"Username ou senha incorretos. {restantes} tentativa(s) restante(s)."
        )

    # 5. Gera token e registra sessao
    token  = _gerar_token()
    expira = (datetime.now(timezone.utc) + timedelta(hours=TOKEN_HORAS)).isoformat()

    sessoes = _load(_F_SESSOES, [])
    # Remove sessoes expiradas deste usuario
    agora = _now_iso()
    sessoes = [s for s in sessoes
               if not (s.get("usuario_id") == usuario["id"]
                       and s.get("expira_em", "") < agora)]
    sessoes.append({
        "id":           str(uuid.uuid4()),
        "usuario_id":   usuario["id"],
        "token":        token,
        "ip":           ip,
        "ip_real":      ip_real,
        "nome_maquina": maquina,
        "cidade":       cidade,
        "expira_em":    expira,
        "criado_em":    agora,
    })
    _save(_F_SESSOES, sessoes)

    # Atualiza ultimo_login
    for u in usuarios:
        if u["id"] == usuario["id"]:
            u["ultimo_login"] = agora
    _save(_F_USUARIOS, usuarios)

    _registrar_tentativa(username, ip, True, ip_real, maquina)

    return ResultadoLogin(
        ok=True,
        usuario=usuario["nome"],
        papel=papel,
        token=token,
        ip=ip,
        maquina=maquina,
        cidade=cidade,
        usuario_id=usuario["id"],
    )


def verificar_sessao(token: str) -> dict | None:
    agora   = _now_iso()
    sessoes = _load(_F_SESSOES, [])
    sessao  = next((s for s in sessoes
                    if s.get("token") == token and s.get("expira_em", "") >= agora), None)
    if not sessao:
        return None

    usuarios = _load(_F_USUARIOS, [])
    usuario  = next((u for u in usuarios
                     if u["id"] == sessao["usuario_id"] and u.get("ativo")), None)
    if not usuario:
        return None

    return {
        "usuario_id": usuario["id"],
        "nome":       usuario["nome"],
        "papel":      usuario["papel"],
        "ip":         sessao["ip"],
        "maquina":    sessao["nome_maquina"],
        "cidade":     sessao["cidade"],
    }


def fazer_logout(token: str):
    sessoes = _load(_F_SESSOES, [])
    sessoes = [s for s in sessoes if s.get("token") != token]
    _save(_F_SESSOES, sessoes)


# ── Gerenciamento de usuarios (master only) ───────────────────────────────────

def criar_usuario(nome: str, username: str, senha: str, papel: str = "membro") -> dict:
    username = username.strip().lower()
    if len(senha) < 8:
        return {"ok": False, "erro": "Senha deve ter no minimo 8 caracteres."}
    if papel not in ("master", "membro"):
        return {"ok": False, "erro": "Papel invalido."}
    if not username or " " in username:
        return {"ok": False, "erro": "Username invalido. Use formato: hudson.amorim"}

    usuarios = _load(_F_USUARIOS, [])
    if any(u.get("username") == username for u in usuarios):
        return {"ok": False, "erro": "Username ja cadastrado."}

    novo = {
        "id":           str(uuid.uuid4()),
        "nome":         nome,
        "username":     username,
        "senha_hash":   _hash_senha(senha),
        "papel":        papel,
        "ativo":        True,
        "ultimo_login": None,
        "criado_em":    _now_iso(),
    }
    usuarios.append(novo)
    _save(_F_USUARIOS, usuarios)
    return {"ok": True, "mensagem": f"Usuario {nome} criado com sucesso."}


def listar_usuarios() -> list:
    return [
        {k: u[k] for k in ("id","nome","username","papel","ativo","ultimo_login","criado_em") if k in u}
        for u in _load(_F_USUARIOS, [])
    ]


def ativar_desativar(usuario_id: str, ativo: bool) -> bool:
    usuarios = _load(_F_USUARIOS, [])
    for u in usuarios:
        if u.get("id") == usuario_id:
            # Nao desativa o master
            if u.get("papel") == "master" and not ativo:
                return False
            u["ativo"] = ativo
            _save(_F_USUARIOS, usuarios)
            return True
    return False


def alterar_senha(usuario_id: str, nova_senha: str) -> bool:
    if len(nova_senha) < 8:
        return False
    usuarios = _load(_F_USUARIOS, [])
    for u in usuarios:
        if u.get("id") == usuario_id:
            u["senha_hash"] = _hash_senha(nova_senha)
            _save(_F_USUARIOS, usuarios)
            return True
    return False


# ── Historico ─────────────────────────────────────────────────────────────────

def registrar_historico(usuario_id: str, nome: str, xmls: list,
                        planilha: str, divergencias: int,
                        ip: str, maquina: str, ip_real: str = ""):
    historico = _load(_F_HISTORICO, [])
    historico.append({
        "id":               str(uuid.uuid4()),
        "usuario_id":       usuario_id,
        "usuario_nome":     nome,
        "xmls_processados": xmls,
        "planilha_gerada":  planilha,
        "divergencias":     divergencias,
        "ip":               ip,
        "ip_real":          ip_real,
        "nome_maquina":     maquina,
        "concluido_em":     _now_iso(),
    })
    _save(_F_HISTORICO, historico)


def listar_historico(limite: int = 50) -> list:
    historico = _load(_F_HISTORICO, [])
    return sorted(historico, key=lambda x: x.get("concluido_em",""), reverse=True)[:limite]


# ── Verificacao de versao ─────────────────────────────────────────────────────

def verificar_versao() -> dict:
    config = _load(_F_CONFIG, {})
    versao_servidor = config.get("versao_app", VERSAO)
    if versao_servidor != VERSAO:
        return {"atualizado": False, "versao_atual": VERSAO, "versao_nova": versao_servidor}
    return {"atualizado": True}


# ── Compatibilidade com painel_master (substitui chamadas Supabase) ───────────

_TABLE_MAP = {
    "usuarios":              _F_USUARIOS,
    "sessoes":               _F_SESSOES,
    "tentativas_login":      _F_TENTATIVAS,
    "dispositivos_aprovados": _F_DISPOSITIVOS,
    "historico":             _F_HISTORICO,
    "configuracoes":         _F_CONFIG,
}


def _parse_filters(params: str) -> list:
    filters = []
    for part in params.split("&"):
        for op in ("=eq.", "=neq.", "=gte.", "=lt."):
            if op in part:
                field, val = part.split(op, 1)
                filters.append((op[1:-1], field, val))
                break
    return filters


def _record_matches(record: dict, filters: list) -> bool:
    for op, field, val in filters:
        rv = str(record.get(field, "")).lower()
        fv = val.lower()
        if op == "eq"  and rv != fv: return False
        if op == "neq" and rv == fv: return False
        if op == "gte" and rv  < fv: return False
        if op == "lt"  and rv >= fv: return False
    return True


def _get(tabela: str, params: str = "") -> list:
    path = _TABLE_MAP.get(tabela)
    if not path:
        return []

    if tabela == "configuracoes":
        raw = _load(path, {})
        records = [{"chave": k, "valor": v} for k, v in raw.items()]
    else:
        records = _load(path, [])
        if not isinstance(records, list):
            records = []

    filters = _parse_filters(params)
    records = [r for r in records if _record_matches(r, filters)]

    # Joins: enriquece com dados do usuario
    if "usuarios(" in params and tabela in ("sessoes", "dispositivos_aprovados", "historico"):
        u_map = {u["id"]: u for u in _load(_F_USUARIOS, [])}
        for r in records:
            r["usuarios"] = u_map.get(r.get("usuario_id"), {})

    # Ordenacao
    for part in params.split("&"):
        if part.startswith("order="):
            order_str = part[6:].split("&")[0]
            if "." in order_str:
                field, direction = order_str.rsplit(".", 1)
                records = sorted(records,
                                 key=lambda x: x.get(field, "") or "",
                                 reverse=(direction == "desc"))
            break

    # Limite
    for part in params.split("&"):
        if part.startswith("limit="):
            try:
                records = records[:int(part[6:])]
            except ValueError:
                pass
            break

    return records


def _get_count(tabela: str, params: str = "") -> int:
    return len(_get(tabela, params))


def _delete(tabela: str, params: str) -> bool:
    path = _TABLE_MAP.get(tabela)
    if not path:
        return False

    records = _load(path, [])
    if not isinstance(records, list):
        return False

    filters = _parse_filters(params)
    if not filters:
        return False

    masters_total    = sum(1 for r in records if r.get("papel") == "master")
    masters_deletados = sum(1 for r in records if _record_matches(r, filters) and r.get("papel") == "master")
    masters_restantes = masters_total - masters_deletados

    kept = []
    for r in records:
        if _record_matches(r, filters):
            # Protege apenas se for o ultimo master restante
            if tabela == "usuarios" and r.get("papel") == "master" and masters_restantes < 1:
                kept.append(r)
        else:
            kept.append(r)

    _save(path, kept)
    return True


def excluir_usuario(usuario_id: str) -> bool:
    return _delete("usuarios", f"id=eq.{usuario_id}")
