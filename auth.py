"""
Sistema de autenticacao e seguranca - CPB Alocacao
- Login com email/senha
- Niveis: master / membro
- Restricao por cidade (Sao Jose - SC)
- Registro de IP, maquina, cidade
- Bloqueio apos tentativas falhas
- Token de sessao com expiracao
"""

import hashlib
import hmac
import os
import socket
import secrets
import json
import re
import requests
from datetime import datetime, timedelta, timezone

SUPABASE_URL = "SUA_SUPABASE_URL"
SUPABASE_KEY = "SUA_SUPABASE_KEY"
SERVICE_KEY  = "SUA_SERVICE_KEY"

MAX_TENTATIVAS  = 5
BLOQUEIO_MIN    = 30
TOKEN_HORAS     = 8
CIDADES_OK = [
    "sao jose", "sao jose - sc", "sao jose-sc",
    "florianopolis", "florianopolis - sc", "florianopolis-sc",
    "ilha de santa catarina",
]
VERSAO          = "1.0.0"


# ── Helpers HTTP ──────────────────────────────────────────────────────────────

def _headers(service=False):
    # Usa sempre a service key para bypassar RLS
    key = SERVICE_KEY if SERVICE_KEY else SUPABASE_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def _get(tabela, params=""):
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{tabela}?{params}",
            headers=_headers(), timeout=8
        )
        if r.ok:
            return r.json()
        # Se erro, retorna lista vazia mas nao silencia
        return []
    except Exception:
        return []


def _get_count(tabela, params="") -> int:
    """Retorna contagem exata via header do Supabase."""
    try:
        h = {**_headers(), "Prefer": "count=exact"}
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{tabela}?{params}&select=id",
            headers=h, timeout=8
        )
        if r.ok:
            # Supabase retorna contagem no header Content-Range
            cr = r.headers.get("Content-Range", "")
            if "/" in cr:
                total = cr.split("/")[-1]
                if total != "*":
                    return int(total)
            # Fallback: conta os itens retornados
            data = r.json()
            return len(data) if isinstance(data, list) else 0
    except Exception:
        pass
    return 0

def _post(tabela, dados):
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{tabela}",
            headers=_headers(), json=dados, timeout=8
        )
        return r.json() if r.ok else None
    except Exception:
        return None

def _patch(tabela, params, dados):
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{tabela}?{params}",
            headers=_headers(), json=dados, timeout=8
        )
        return r.ok
    except Exception:
        return False

def _delete(tabela, params):
    try:
        r = requests.delete(
            f"{SUPABASE_URL}/rest/v1/{tabela}?{params}",
            headers=_headers(), timeout=8
        )
        return r.ok
    except Exception:
        return False


# ── Seguranca ─────────────────────────────────────────────────────────────────

def _hash_senha(senha: str) -> str:
    """Hash seguro com salt unico por senha."""
    salt = secrets.token_hex(32)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), 310000)
    return f"{salt}:{h.hex()}"

def _verificar_senha(senha: str, hash_armazenado: str) -> bool:
    """Verifica senha contra hash armazenado."""
    try:
        salt, h_hex = hash_armazenado.split(":", 1)
        h = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), 310000)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False

def _gerar_token() -> str:
    return secrets.token_urlsafe(64)


# ── Info da maquina e localizacao ─────────────────────────────────────────────

def _get_ip_externo() -> str:
    """IP externo - pode estar mascarado por VPN."""
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
    """
    IP real da maquina via interface de rede local.
    VPNs de extensao de browser NAO alteram isso.
    """
    import socket
    try:
        # Conecta UDP ao Google DNS - nao envia dados, so descobre IP local
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "desconhecido"


def _get_ip() -> str:
    """Retorna IP externo para checagem de geolocalizacao."""
    return _get_ip_externo()


def _get_todos_ips() -> dict:
    """Retorna IP externo e IP real da maquina."""
    return {
        "externo": _get_ip_externo(),
        "real":    _get_ip_real(),
    }

def _get_localizacao(ip: str) -> dict:
    """
    Deteccao ultra-rigorosa multicamada.
    Consulta 4 APIs + checagens proprias.
    Principio: em caso de duvida, BLOQUEIA.
    """
    resultado = {
        "cidade": "desconhecida", "pais": "BR",
        "vpn": False, "proxy": False, "hosting": False,
        "tor": False, "suspeito": False, "score_risco": 0,
        "motivos": [],
    }

    def add_risco(pontos, motivo):
        resultado["score_risco"] += pontos
        resultado["motivos"].append(motivo)

    # ── API 1: ip-api.com ─────────────────────────────────────────────────────
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

    # ── API 2: proxycheck.io ──────────────────────────────────────────────────
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

    # ── API 3: ipqualityscore.com ─────────────────────────────────────────────
    try:
        # Chave publica gratuita de demonstracao
        r3 = requests.get(
            f"https://ipqualityscore.com/api/json/ip/DEMO/{ip}"
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

    # ── API 4: ipapi.co ───────────────────────────────────────────────────────
    try:
        r4 = requests.get(f"https://ipapi.co/{ip}/json/", timeout=5)
        if r4.ok:
            d4 = r4.json()
            if resultado["cidade"] == "desconhecida":
                c = d4.get("city","").lower()
                rc = d4.get("region_code","").lower()
                if c:
                    resultado["cidade"] = f"{c} - {rc}"
            org4 = d4.get("org","").lower()
            VPN_ORGS = [
                "vpn","proxy","tunnel","tor","anonymizer","datacenter",
                "hosting","cloud","server","colocation","colo","data center"
            ]
            if any(v in org4 for v in VPN_ORGS):
                add_risco(60, f"org_suspeita:ipapi")
                resultado["suspeito"] = True
            pais4 = d4.get("country_code","BR").upper()
            if pais4 and pais4 != "BR":
                resultado["pais"] = pais4
                add_risco(100, f"pais:{pais4}")
    except Exception:
        pass

    # ── Checagem de consistencia geografica ───────────────────────────────────
    # Se nao conseguiu determinar cidade apos 4 APIs = suspeito
    if resultado["cidade"] == "desconhecida":
        add_risco(50, "cidade_indeterminada")

    return resultado


def _notificar_tentativa_vpn(username: str, ip: str, ip_real: str,
                             maquina: str, cidade: str, motivo: str):
    """Envia email para o master quando alguem tenta logar com VPN."""
    try:
        # Busca configuracoes de email do Supabase
        cfg = _get("configuracoes",
                   "chave=in.(email_notif_master,email_gmail_user,"
                   "email_gmail_senha)&select=chave,valor")
        if not cfg:
            return

        cfg_dict = {c["chave"]: c["valor"] for c in cfg}
        dest     = cfg_dict.get("email_notif_master", "")
        gmail    = cfg_dict.get("email_gmail_user", "")
        senha_gm = cfg_dict.get("email_gmail_senha", "")

        if not dest or not gmail or not senha_gm:
            return

        from notificacao import enviar_notificacao
        from datetime import datetime
        enviar_notificacao(
            destinatario=dest,
            dados={
                "usuario_nome": f"ALERTA VPN — {username}",
                "planilha":     f"Motivo: {motivo}",
                "xmls":         [
                    f"IP Externo: {ip}",
                    f"IP Real: {ip_real}",
                    f"Maquina: {maquina}",
                    f"Cidade: {cidade}",
                    f"Horario: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
                ],
                "divergencias": 0,
                "horario": datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            },
            gmail_user=gmail,
            gmail_app_password=senha_gm,
        )
    except Exception:
        pass


def _ip_suspeito(loc: dict) -> tuple[bool, str]:
    """
    Bloqueia se qualquer API detectou problema OU score >= 33.
    Principio: falso positivo e melhor que falso negativo.
    """
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
        return True  # sem geolocalizacao, permite mas registra
    c = cidade.lower().strip()
    return any(ok.lower() in c for ok in CIDADES_OK)


# ── Controle de tentativas ────────────────────────────────────────────────────

def _contar_tentativas(username: str, ip: str) -> int:
    """
    Conta tentativas falhas por username OU por IP nos ultimos BLOQUEIO_MIN minutos.
    Bloqueia por ambos — impede trocar de usuario com mesmo IP.
    Usa _get_count com header Content-Range para contagem exata.
    """
    limite = (datetime.now(timezone.utc) - timedelta(minutes=BLOQUEIO_MIN)).isoformat()

    n_user = _get_count("tentativas_login",
                        f"username=eq.{username}&sucesso=eq.false"
                        f"&criado_em=gte.{limite}")

    n_ip = 0
    if ip and ip not in ("desconhecido", ""):
        n_ip = _get_count("tentativas_login",
                          f"ip=eq.{ip}&sucesso=eq.false"
                          f"&criado_em=gte.{limite}")

    return max(n_user, n_ip)

def _registrar_tentativa(username: str, ip: str, sucesso: bool,
                         ip_real: str = "", maquina: str = ""):
    _post("tentativas_login", {
        "username": username,
        "ip":       ip,
        "ip_real":  ip_real,
        "maquina":  maquina,
        "sucesso":  sucesso
    })


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


def _verificar_whitelist(usuario_id: str, ip: str,
                         ip_real: str, maquina: str, cidade: str) -> str:
    """
    Regra de IP fixo:
    - Primeiro acesso: registra IP como "aprovado" automaticamente (IP fixo)
    - Acessos seguintes do MESMO ip e ip_real: aprovado
    - Qualquer IP diferente: bloqueado imediatamente
    Retorna: "aprovado", "pendente", "bloqueado"
    """
    rows = _get("dispositivos_aprovados",
                f"usuario_id=eq.{usuario_id}&select=*&order=criado_em.asc")

    if not rows:
        # Primeiro acesso — registra e aprova automaticamente (IP fixo)
        _post("dispositivos_aprovados", {
            "usuario_id":  usuario_id,
            "ip":          ip,
            "ip_real":     ip_real,
            "maquina":     maquina,
            "cidade":      cidade,
            "status":      "aprovado",
            "ip_fixo":     True,
        })
        return "aprovado"

    # Busca o registro aprovado (IP fixo)
    aprovados = [d for d in rows if d.get("status") == "aprovado"]

    if not aprovados:
        # Tem registros mas nenhum aprovado ainda — pendente manual
        # Verifica se ja tem pendente para este IP
        ja_registrado = any(
            d.get("ip") == ip and d.get("ip_real") == ip_real
            for d in rows
        )
        if not ja_registrado:
            _post("dispositivos_aprovados", {
                "usuario_id": usuario_id,
                "ip":         ip,
                "ip_real":    ip_real,
                "maquina":    maquina,
                "cidade":     cidade,
                "status":     "pendente",
                "ip_fixo":    False,
            })
        return "pendente"

    # Tem IP fixo aprovado — verifica se e o mesmo
    ip_fixo = aprovados[0]

    # Bloqueado manualmente pelo master
    bloqueados = [d for d in rows if d.get("status") == "bloqueado"]
    for b in bloqueados:
        if b.get("ip") == ip or b.get("ip_real") == ip_real:
            return "bloqueado"

    # Verifica se IP bate com o fixo
    mesmo_ip      = ip_fixo.get("ip")      == ip
    mesmo_ip_real = ip_fixo.get("ip_real") == ip_real
    mesma_maquina = ip_fixo.get("maquina") == maquina

    if mesmo_ip and mesmo_ip_real:
        return "aprovado"

    # IP diferente do fixo — registra tentativa e bloqueia
    ja_registrado = any(
        d.get("ip") == ip and d.get("ip_real") == ip_real
        for d in rows
    )
    if not ja_registrado:
        _post("dispositivos_aprovados", {
            "usuario_id": usuario_id,
            "ip":         ip,
            "ip_real":    ip_real,
            "maquina":    maquina,
            "cidade":     cidade,
            "status":     "bloqueado_auto",
            "ip_fixo":    False,
        })
    return "bloqueado"


def listar_dispositivos_pendentes() -> list:
    return _get("dispositivos_aprovados",
                "status=eq.pendente&select=*,usuarios(nome,username)"
                "&order=criado_em.desc")


def aprovar_dispositivo(dispositivo_id: str) -> bool:
    return _patch("dispositivos_aprovados",
                  f"id=eq.{dispositivo_id}", {"status": "aprovado"})


def bloquear_dispositivo(dispositivo_id: str) -> bool:
    return _patch("dispositivos_aprovados",
                  f"id=eq.{dispositivo_id}", {"status": "bloqueado"})


def listar_dispositivos_usuario(usuario_id: str) -> list:
    return _get("dispositivos_aprovados",
                f"usuario_id=eq.{usuario_id}&select=*")


def fazer_login(username: str, senha: str) -> ResultadoLogin:
    username = username.strip().lower()

    # Coleta info da maquina
    maquina = _get_nome_maquina()
    ips     = _get_todos_ips()
    ip      = ips["externo"]
    ip_real = ips["real"]

    # 1. Bloqueio por tentativas (persiste no banco por 30 min)
    tentativas = _contar_tentativas(username, ip)
    if tentativas >= MAX_TENTATIVAS:
        _registrar_tentativa(username, ip, False, ip_real, maquina)
        return ResultadoLogin(
            erro=f"Acesso bloqueado por {BLOQUEIO_MIN} minutos.\n"
                 f"Tente novamente mais tarde."
        )

    # 2. Busca usuario antes das checagens geograficas
    rows = _get("usuarios", f"username=eq.{username}&ativo=eq.true&select=*")
    if not rows:
        _registrar_tentativa(username, ip, False, ip_real, maquina)
        tentativas += 1
        restantes = MAX_TENTATIVAS - tentativas
        return ResultadoLogin(
            erro=f"Username ou senha incorretos. {restantes} tentativa(s) restante(s)."
        )
    usuario = rows[0]
    papel   = usuario.get("papel", "membro")

    # 3. Verificacoes geograficas e de VPN (so membros)
    if papel != "master":
        loc    = _get_localizacao(ip)
        cidade = loc.get("cidade", "desconhecida")

        # VPN / Proxy / Hosting
        bloqueado, motivo = _ip_suspeito(loc)
        if bloqueado:
            _registrar_tentativa(username, ip, False, ip_real, maquina)
            # Notifica master por email em background
            import threading as _th
            _th.Thread(
                target=_notificar_tentativa_vpn,
                args=(username, ip, ip_real, maquina, cidade, motivo),
                daemon=True
            ).start()
            return ResultadoLogin(
                erro=f"Acesso negado: {motivo}.\n"
                     f"Verifique sua conexao e tente novamente."
            )

        # Cidade
        if cidade not in ("desconhecida", "") and not _cidade_permitida(cidade):
            _registrar_tentativa(username, ip, False, ip_real, maquina)
            return ResultadoLogin(
                erro=f"Geolocalizacao invalida: {cidade}.\n"
                     f"Este aplicativo so funciona em Sao Jose - SC ou Florianopolis - SC."
            )

        # IP fixo / whitelist
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

    _post("sessoes", {
        "usuario_id":   usuario["id"],
        "token":        token,
        "ip":           ip,
        "ip_real":      ip_real,
        "nome_maquina": maquina,
        "cidade":       cidade,
        "expira_em":    expira
    })
    # Limpa sessoes expiradas deste usuario
    try:
        agora = datetime.now(timezone.utc).isoformat()
        _delete("sessoes",
                f"usuario_id=eq.{usuario['id']}&expira_em=lt.{agora}")
    except Exception:
        pass

    _patch("usuarios", f"id=eq.{usuario['id']}", {
        "ultimo_login": datetime.now(timezone.utc).isoformat()
    })

    _registrar_tentativa(username, ip, True, ip_real, maquina)

    return ResultadoLogin(
        ok=True,
        usuario=usuario["nome"],
        papel=papel,
        token=token,
        ip=ip,
        maquina=maquina,
        cidade=cidade,
        usuario_id=usuario["id"]
    )


def verificar_sessao(token: str) -> dict | None:
    """Verifica se o token e valido e nao expirou."""
    agora = datetime.now(timezone.utc).isoformat()
    rows = _get("sessoes",
                f"token=eq.{token}&expira_em=gte.{agora}&select=*,usuarios(*)")
    if not rows:
        return None
    sessao = rows[0]
    usuario = sessao.get("usuarios", {})
    if not usuario or not usuario.get("ativo"):
        return None
    return {
        "usuario_id": usuario["id"],
        "nome":       usuario["nome"],
        "papel":      usuario["papel"],
        "ip":         sessao["ip"],
        "maquina":    sessao["nome_maquina"],
        "cidade":     sessao["cidade"]
    }


def fazer_logout(token: str):
    """Remove a sessao do banco."""
    _delete("sessoes", f"token=eq.{token}")


# ── Gerenciamento de usuarios (master only) ───────────────────────────────────

def criar_usuario(nome: str, username: str, senha: str, papel: str = "membro") -> dict:
    """Cria novo usuario. Requer papel master."""
    username = username.strip().lower()
    if len(senha) < 8:
        return {"ok": False, "erro": "Senha deve ter no minimo 8 caracteres."}
    if papel not in ("master", "membro"):
        return {"ok": False, "erro": "Papel invalido."}
    if not username or " " in username:
        return {"ok": False, "erro": "Username invalido. Use formato: hudson.amorim"}

    # Verifica se username ja existe
    rows = _get("usuarios", f"username=eq.{username}&select=id")
    if rows:
        return {"ok": False, "erro": "Username ja cadastrado."}

    resultado = _post("usuarios", {
        "nome":       nome,
        "username":   username,
        "senha_hash": _hash_senha(senha),
        "papel":      papel,
        "ativo":      True
    })
    if resultado:
        return {"ok": True, "mensagem": f"Usuario {nome} criado com sucesso."}
    return {"ok": False, "erro": "Erro ao criar usuario."}


def listar_usuarios() -> list:
    return _get("usuarios", "select=id,nome,username,papel,ativo,ultimo_login,criado_em")


def ativar_desativar(usuario_id: str, ativo: bool) -> bool:
    return _patch("usuarios", f"id=eq.{usuario_id}", {"ativo": ativo})


def alterar_senha(usuario_id: str, nova_senha: str) -> bool:
    if len(nova_senha) < 8:
        return False
    return _patch("usuarios", f"id=eq.{usuario_id}",
                  {"senha_hash": _hash_senha(nova_senha)})


# ── Historico ─────────────────────────────────────────────────────────────────

def registrar_historico(usuario_id: str, nome: str, xmls: list,
                        planilha: str, divergencias: int,
                        ip: str, maquina: str, ip_real: str = ""):
    dados = {
        "usuario_id":       usuario_id,
        "usuario_nome":     nome,
        "xmls_processados": xmls,
        "planilha_gerada":  planilha,
        "divergencias":     divergencias,
        "ip":               ip,
        "ip_real":          ip_real,
        "nome_maquina":     maquina
    }
    # Tenta Supabase
    try:
        ok = _post("historico", dados)
    except Exception:
        ok = False

    # Fallback local se Supabase falhar
    if not ok:
        _salvar_historico_local(dados)


def _salvar_historico_local(dados: dict):
    """Salva historico em arquivo local se Supabase estiver indisponivel."""
    import json
    from pathlib import Path
    from datetime import datetime, timezone
    arquivo = Path.home() / ".cpb_historico_local.jsonl"
    dados["concluido_em"] = datetime.now(timezone.utc).isoformat()
    dados["pendente_sync"] = True
    try:
        with open(arquivo, "a", encoding="utf-8") as f:
            f.write(json.dumps(dados) + "\n")
    except Exception:
        pass


def sincronizar_historico_local():
    """Envia registros locais pendentes para o Supabase."""
    import json
    from pathlib import Path
    arquivo = Path.home() / ".cpb_historico_local.jsonl"
    if not arquivo.exists():
        return
    pendentes = []
    try:
        with open(arquivo, "r", encoding="utf-8") as f:
            for linha in f:
                try:
                    pendentes.append(json.loads(linha.strip()))
                except Exception:
                    pass
    except Exception:
        return

    enviados = []
    for dados in pendentes:
        dados.pop("pendente_sync", None)
        try:
            if _post("historico", dados):
                enviados.append(dados)
        except Exception:
            pass

    # Remove os enviados do arquivo local
    if enviados:
        restantes = [d for d in pendentes if d not in enviados]
        try:
            with open(arquivo, "w", encoding="utf-8") as f:
                for d in restantes:
                    d["pendente_sync"] = True
                    f.write(json.dumps(d) + "\n")
        except Exception:
            pass


def listar_historico(limite: int = 50) -> list:
    return _get("historico",
                f"select=*&order=concluido_em.desc&limit={limite}")


# ── Verificacao de versao (auto-update) ───────────────────────────────────────

def verificar_versao() -> dict:
    """Verifica se ha nova versao disponivel."""
    rows = _get("configuracoes", "chave=eq.versao_app&select=valor")
    if not rows:
        return {"atualizado": True}
    versao_servidor = rows[0]["valor"]
    if versao_servidor != VERSAO:
        return {"atualizado": False, "versao_atual": VERSAO,
                "versao_nova": versao_servidor}
    return {"atualizado": True}
