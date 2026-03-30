"""
Faturamento NG - GSA CPB
Base: versao original que funcionava (site_scraper_1).
Otimizacoes: WebDriverWait no lugar de time.sleep fixos.
Correcao: dataProvider soma N.Meses de todas as linhas por periodico.
"""

import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager

REGIONAIS = ["5", "55"]

import json, pathlib

_CACHE_FILE = pathlib.Path.home() / ".cpb_regional_cache.json"

def _cache_carregar() -> dict:
    try:
        if _CACHE_FILE.exists():
            return json.loads(_CACHE_FILE.read_text())
    except Exception:
        pass
    return {}

def _cache_salvar(cache: dict):
    try:
        _CACHE_FILE.write_text(json.dumps(cache))
    except Exception:
        pass

def _cache_get(numero: int) -> str | None:
    return _cache_carregar().get(str(numero))

def _cache_set(numero: int, regional: str):
    c = _cache_carregar()
    c[str(numero)] = regional
    _cache_salvar(c)

PERIODICO_MAP = [
    ("najr", ["na junior", "na junior", "n.a. junior", "nosso amiguinho junior"]),
    ("na",   ["nosso amiguinho", "n.a.", "nosso a"]),
    ("vs",   ["vida e saude", "vida & saude", "vida e saude"]),
]

def _tipo_periodico(texto):
    t = texto.strip().lower()
    for tipo, palavras in PERIODICO_MAP:
        for p in palavras:
            if p in t:
                return tipo
    return None

def js(driver, script, *args):
    return driver.execute_script(script, *args)

def _wait(driver, timeout=10):
    return WebDriverWait(driver, timeout, poll_frequency=0.15,
                         ignored_exceptions=[StaleElementReferenceException])

def _aguardar_grid(driver, timeout=8):
    try:
        _wait(driver, timeout).until(lambda d: js(d, """
            var grids = document.querySelectorAll('vaadin-grid');
            for (var i = 0; i < grids.length; i++) {
                if (grids[i].offsetParent && parseInt(grids[i].getAttribute('size') || '0') > 0)
                    return true;
            }
            return false;
        """))
        return True
    except TimeoutException:
        return False


# -- Login --------------------------------------------------------------------
def _login(driver, usuario, senha):
    driver.get("https://gsa.cpb.com.br/login")
    try:
        _wait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "input")))
    except TimeoutException:
        pass
    for inp in driver.find_elements(By.TAG_NAME, "input"):
        t = inp.get_attribute("type") or ""
        if t == "password":
            inp.clear(); inp.send_keys(senha)
        elif t in ("text", "email", ""):
            inp.clear(); inp.send_keys(usuario)
    for btn in driver.find_elements(By.TAG_NAME, "button"):
        if btn.get_attribute("type") == "submit" or "entrar" in btn.text.lower():
            btn.click(); break
    else:
        driver.find_elements(By.TAG_NAME, "form")[0].submit()
    try:
        _wait(driver, 12).until(lambda d: "login" not in d.current_url.lower())
    except TimeoutException:
        pass
    if "login" in driver.current_url.lower():
        raise Exception("Falha no login - verifique usuario e senha.")


# -- Aba Faturamento NG -------------------------------------------------------
def _ir_faturamento_ng(driver):
    try:
        _wait(driver, 8).until(
            lambda d: len(d.find_elements(By.TAG_NAME, "vaadin-tab")) > 0
        )
    except TimeoutException:
        pass
    for tab in driver.find_elements(By.TAG_NAME, "vaadin-tab"):
        txt = js(driver, "return arguments[0].textContent", tab) or ""
        if "Faturamento NG" in txt:
            js(driver, "arguments[0].click()", tab)
            try:
                _wait(driver, 6).until(
                    lambda d: len(d.find_elements(By.TAG_NAME, "vaadin-combo-box")) > 0
                )
            except TimeoutException:
                pass
            return True
    return False


# -- Shadow root helpers ------------------------------------------------------
GET_COMBO_INPUT_JS = """
    var combo = arguments[0];
    if (!combo.shadowRoot) return null;
    var children1 = combo.shadowRoot.querySelectorAll('*');
    for (var i = 0; i < children1.length; i++) {
        if (children1[i].shadowRoot) {
            var inp = children1[i].shadowRoot.querySelector('input');
            if (inp) return inp;
        }
    }
    return null;
"""

GET_FIELD_INPUT_JS = """
    var el = arguments[0];
    if (el.shadowRoot) {
        var inp = el.shadowRoot.querySelector('input');
        if (inp) return inp;
        var children = el.shadowRoot.querySelectorAll('*');
        for (var i=0; i<children.length; i++) {
            if (children[i].shadowRoot) {
                var found = children[i].shadowRoot.querySelector('input');
                if (found) return found;
            }
        }
    }
    return el.querySelector('input');
"""


# -- Selecionar regional ------------------------------------------------------
def _set_regional(driver, regional, log_fn):
    combos = driver.find_elements(By.TAG_NAME, "vaadin-combo-box")
    if not combos:
        pass
        return False
    combo = combos[0]
    inp = js(driver, GET_COMBO_INPUT_JS, combo)
    if not inp:
        pass
        return False

    js(driver, """
        var combo = arguments[0]; var inp = arguments[1];
        combo.selectedItem = null; combo.value = '';
        combo.opened = false;
        combo.dispatchEvent(new CustomEvent('value-changed', {detail:{value:''}, bubbles:true}));
        inp.value = '';
        inp.dispatchEvent(new Event('input',  {bubbles:true}));
        inp.dispatchEvent(new Event('change', {bubbles:true}));
    """, combo, inp)
    time.sleep(0.3)

    # Abre o combo e aguarda os itens carregarem
    js(driver, """
        var combo = arguments[0];
        combo.opened = true;
        combo.dispatchEvent(new CustomEvent('opened-changed', {detail:{value:true}, bubbles:true}));
    """, combo)

    # Aguarda ate os itens aparecerem (max 3s)
    for _ in range(15):
        time.sleep(0.2)
        items_count = js(driver, """
            var combo = arguments[0];
            var items = combo.items || combo.filteredItems || [];
            return items.length;
        """, combo)
        if items_count and items_count > 0:
            break

    inp.click()
    time.sleep(0.2)
    inp.send_keys(regional)
    time.sleep(2.0)

    resultado = js(driver, """
        var combo = arguments[0]; var regional = arguments[1];
        var prefix = regional + ' - ';
        var items = combo.filteredItems || combo.items || [];
        var item = null;
        for (var i = 0; i < items.length; i++) {
            if (!items[i]) continue;
            var lbl = String(items[i].label || '');
            if (lbl.startsWith(prefix)) { item = items[i]; break; }
        }
        if (!item) {
            var lbls = items.slice(0,5).map(function(x){ return x ? x.label : '?'; });
            return 'SEM_ITEM. filteredItems[0..4]: ' + JSON.stringify(lbls);
        }
        combo.selectedItem = item;
        combo.value = item.key;
        combo.opened = false;
        combo.dispatchEvent(new CustomEvent('value-changed', {detail:{value:item.key}, bubbles:true}));
        var inp = arguments[2];
        if (inp) {
            inp.value = item.label;
            inp.dispatchEvent(new Event('input',  {bubbles:true}));
            inp.dispatchEvent(new Event('change', {bubbles:true}));
        }
        return 'OK:' + item.label;
    """, combo, regional, inp)

    # Se filteredItems veio vazio, tenta mais 2 vezes esperando o Vaadin carregar
    tentativas = 0
    while not resultado.startswith("OK") and "SEM_ITEM" in resultado and tentativas < 2:
        tentativas += 1
        pass
        time.sleep(1.5)
        resultado = js(driver, """
            var combo = arguments[0]; var regional = arguments[1]; var inp = arguments[2];
            var prefix = regional + ' - ';
            var items = combo.filteredItems || combo.items || [];
            var item = null;
            for (var i = 0; i < items.length; i++) {
                if (!items[i]) continue;
                if (String(items[i].label || '').startsWith(prefix)) { item = items[i]; break; }
            }
            if (!item) {
                // Tenta redigitar
                inp.value = '';
                inp.dispatchEvent(new Event('input', {bubbles:true}));
                inp.value = regional;
                inp.dispatchEvent(new Event('input', {bubbles:true}));
                var lbls = (combo.filteredItems||combo.items||[]).slice(0,5).map(function(x){ return x ? x.label : '?'; });
                return 'SEM_ITEM: ' + JSON.stringify(lbls);
            }
            combo.selectedItem = item;
            combo.value = item.key;
            combo.opened = false;
            combo.dispatchEvent(new CustomEvent('value-changed', {detail:{value:item.key}, bubbles:true}));
            if (inp) {
                inp.value = item.label;
                inp.dispatchEvent(new Event('input',  {bubbles:true}));
                inp.dispatchEvent(new Event('change', {bubbles:true}));
            }
            return 'OK:' + item.label;
        """, combo, regional, inp)
        time.sleep(0.5)

    ok = resultado.startswith("OK")
    log_fn(f"      Regional '{regional}': {resultado}", "ok" if ok else "warn")
    time.sleep(0.8)
    return ok


# -- Pesquisar resumo ---------------------------------------------------------
def _pesquisar_resumo(driver, numero, log_fn):
    campos = driver.find_elements(By.TAG_NAME, "vaadin-integer-field")
    campo = None
    for c in campos:
        ph = (c.get_attribute("placeholder") or "").lower()
        if "resumo" in ph:
            campo = c
            break
    if not campo and campos:
        campo = campos[0]
    if not campo:
        pass
        return False

    inp = js(driver, GET_FIELD_INPUT_JS, campo)
    if not inp:
        pass
        return False

    js(driver, """
        var el = arguments[0]; var campo = arguments[1];
        campo.value = null; campo.invalid = false;
        campo.dispatchEvent(new CustomEvent('value-changed', {detail:{value:null}, bubbles:true}));
        el.value = '';
        el.dispatchEvent(new Event('input',  {bubbles:true}));
        el.dispatchEvent(new Event('change', {bubbles:true}));
    """, inp, campo)

    # Aguarda campo vazio
    try:
        _wait(driver, 2).until(lambda d: js(d, "return arguments[0].value", inp) == "")
    except TimeoutException:
        pass

    inp.click()
    inp.send_keys(str(numero))
    # Captura size atual antes de pesquisar (pode ser do resumo anterior)
    size_antes = js(driver, """
        var g = Array.from(document.querySelectorAll('vaadin-grid'))
                     .find(function(g){ return g.offsetParent; });
        return g ? g.getAttribute('size') : '0';
    """) or '0'

    inp.send_keys(Keys.RETURN)

    # Aguarda a grid mudar (size diferente do anterior) ou aparecer do zero
    for _ in range(40):
        time.sleep(0.2)
        size_atual = js(driver, """
            var g = Array.from(document.querySelectorAll('vaadin-grid'))
                         .find(function(g){ return g.offsetParent; });
            return g ? g.getAttribute('size') : null;
        """)
        if size_atual is not None and size_atual != size_antes:
            break

    grids = driver.find_elements(By.TAG_NAME, "vaadin-grid")
    for grid in grids:
        if grid.is_displayed():
            try:
                if int(grid.get_attribute("size") or "0") > 0:
                    return True
            except Exception:
                pass
    return False


# -- Ler grid e somar N.Meses por tipo ----------------------------------------
def _ler_grid_e_somar(driver, log_fn):
    resultado = {"vs": 0, "na": 0, "najr": 0, "cancelado": False}

    # Aguarda grid renderizar
    _aguardar_grid(driver, timeout=5)

    # Forca scroll para carregar todos os registros na grid
    js(driver, """
        var grid = Array.from(document.querySelectorAll('vaadin-grid'))
                        .find(function(g){
                            return g.offsetParent && parseInt(g.getAttribute('size')||'0') > 0;
                        });
        if (grid) {
            try { grid.scrollToIndex(parseInt(grid.getAttribute('size') || '0') - 1); }
            catch(e) {}
        }
    """)
    time.sleep(0.5)

    dados_dp = js(driver, """
        var grid = Array.from(document.querySelectorAll('vaadin-grid'))
                        .find(function(g){
                            return g.offsetParent && parseInt(g.getAttribute('size')||'0') > 0;
                        });
        if (!grid) return null;
        var size = parseInt(grid.getAttribute('size') || '0');

        // Tenta 1: _cache interno do Vaadin (items ja carregados)
        try {
            var cache = grid._cache;
            if (cache && cache.items) {
                var vals = Object.values(cache.items)
                    .filter(function(x){ return x && typeof x === 'object' && !Array.isArray(x); });
                if (vals.length >= size) {
                    return vals.map(function(item) {
                        var row = {};
                        Object.keys(item).forEach(function(k) {
                            row[k] = String(item[k] !== null && item[k] !== undefined ? item[k] : '');
                        });
                        return row;
                    });
                }
            }
        } catch(e) {}

        // Tenta 2: grid.items array direto
        try {
            if (Array.isArray(grid.items) && grid.items.length > 0) {
                return grid.items.map(function(item) {
                    var row = {};
                    Object.keys(item).forEach(function(k) {
                        row[k] = String(item[k] !== null && item[k] !== undefined ? item[k] : '');
                    });
                    return row;
                });
            }
        } catch(e) {}

        // Tenta 3: dataProvider callback
        try {
            var result = [];
            grid.dataProvider(
                {page: 0, pageSize: size + 50, sortOrders: [], filters: []},
                function(items, total) {
                    (items || []).forEach(function(item) {
                        if (!item) return;
                        var row = {};
                        Object.keys(item).forEach(function(k) {
                            row[k] = String(item[k] !== null && item[k] !== undefined ? item[k] : '');
                        });
                        result.push(row);
                    });
                }
            );
            if (result.length > 0) return result;
        } catch(e) { return 'ERRO_DP:' + e.message; }

        return null;
    """)

    if dados_dp and isinstance(dados_dp, list) and len(dados_dp) > 0:
        pass
        if dados_dp:
            pass
            pass

        # Identifica a chave de N.Meses pelo nome do campo
        chave_nmeses = None
        for k in dados_dp[0].keys():
            if "mes" in k.lower():
                chave_nmeses = k
                pass  # campo silenciado
                break

        for row in dados_dp:
            periodico_tipo = None
            for k, v in row.items():
                tipo = _tipo_periodico(v)
                if tipo:
                    periodico_tipo = tipo
                    break

            if not periodico_tipo:
                continue

            nmeses_val = 0

            # Tenta pelo nome do campo
            if chave_nmeses and chave_nmeses in row:
                try:
                    nmeses_val = int(row[chave_nmeses])
                except (ValueError, TypeError):
                    pass

            # Fallback: maior numero >= 12 da linha (N.Meses nunca e menor que 12)
            if nmeses_val == 0:
                for k, v in row.items():
                    try:
                        n = int(v)
                        if n >= 12 and n > nmeses_val:
                            nmeses_val = n
                    except (ValueError, TypeError):
                        pass

            if nmeses_val > 0:
                resultado[periodico_tipo] += nmeses_val
                log_fn(f"      + {periodico_tipo.upper()}: +{nmeses_val}", "ok")

    else:
        pass  # dataProvider silenciado

        # Fallback: texto da pagina - logica original que funcionava
        body_text = driver.find_element(By.TAG_NAME, "body").text
        linhas = body_text.splitlines()

        # Loga linhas relevantes: periodico e numeros entre 2 e 999
        for idx_dbg, l_dbg in enumerate(linhas):
            l_strip = l_dbg.strip()
            eh_num = l_strip.isdigit() and int(l_strip) >= 12
            pass  # debug de linhas silenciado

        # Estrutura do texto da grid do GSA:
        # Cada assinante: "PERIODICO" -> "QTDE" -> "N.MESES"
        # A grid do Vaadin so renderiza os registros visiveis na tela.
        # Para grids grandes, faz scroll ate o final e rele o texto.

        def _coletar_texto():
            txt = driver.find_element(By.TAG_NAME, "body").text
            return txt.splitlines()

        def _processar_linhas(lns):
            # Filtra so linhas de periodico e numeros inteiros
            rel = []
            for l in lns:
                ls = l.strip()
                if _tipo_periodico(ls):
                    rel.append(("p", ls))
                else:
                    try:
                        rel.append(("n", int(ls)))
                    except (ValueError, TypeError):
                        pass

            # Padrao por assinante: ("p", PERIODICO) -> ("n", QTDE) -> ("n", N.MESES)
            # N.Meses sempre >= 12, Qtde e qualquer numero (1, 2, 5...)
            res = {"vs": 0, "na": 0, "najr": 0}
            i2 = 0
            while i2 < len(rel):
                tipo_tag, val = rel[i2]
                if tipo_tag == "p":
                    t2 = _tipo_periodico(val)
                    # Procura o padrao: periodico -> num (qtde) -> num (nmeses)
                    if i2 + 2 < len(rel):
                        tag1, v1 = rel[i2 + 1]
                        tag2, v2 = rel[i2 + 2]
                        if tag1 == "n" and tag2 == "n" and v2 >= 12:
                            res[t2] += v2
                            i2 += 3
                            continue
                i2 += 1
            return res

        # Primeira leitura
        r1 = _processar_linhas(linhas)
        resultado["vs"]   += r1["vs"]
        resultado["na"]   += r1["na"]
        resultado["najr"] += r1["najr"]
        if r1["vs"] > 0:
            pass
        if r1["na"] > 0:
            pass
        if r1["najr"] > 0:
            pass

        # Faz scroll completo: topo -> meio -> final
        # para garantir que todos os registros sejam renderizados
        grids = driver.find_elements(By.TAG_NAME, "vaadin-grid")
        grid_vis = next((g for g in grids if g.is_displayed()), None)
        if grid_vis:
            try:
                size = int(grid_vis.get_attribute("size") or "0")
                if size > 5:
                    acumulado = {"vs": r1["vs"], "na": r1["na"], "najr": r1["najr"]}

                    for idx_scroll in [size - 1, size // 2, 0, size - 1]:
                        js(driver, "arguments[0].scrollToIndex(arguments[1])",
                           grid_vis, idx_scroll)
                        time.sleep(0.6)
                        r_scroll = _processar_linhas(_coletar_texto())
                        # Acumula o maximo encontrado em cada posicao
                        for k in ["vs", "na", "najr"]:
                            if r_scroll[k] > acumulado[k]:
                                diff = r_scroll[k] - acumulado[k]
                                acumulado[k] = r_scroll[k]
                                resultado[k] += diff
                                pass  # scroll silenciado

            except Exception as e_scroll:
                pass

    # Detecta cancelado
    try:
        cancelado = js(driver, """
            var grids = document.querySelectorAll('vaadin-grid');
            for (var gi=0; gi<grids.length; gi++) {
                var g = grids[gi]; if (!g.offsetParent) continue;
                var sr = g.shadowRoot; if (!sr) continue;
                var rows = sr.querySelectorAll('tr[part*="row"]');
                for (var ri=0; ri<rows.length; ri++) {
                    var row = rows[ri];
                    var c = window.getComputedStyle(row).color;
                    if (c && (c.indexOf('255, 0, 0')!==-1 || c.indexOf('255,0,0')!==-1))
                        return true;
                    var cells = row.querySelectorAll('td');
                    for (var ci=0; ci<cells.length; ci++) {
                        var cc = window.getComputedStyle(cells[ci]).color;
                        if (cc && (cc.indexOf('255, 0, 0')!==-1 || cc.indexOf('255,0,0')!==-1))
                            return true;
                    }
                }
            }
            var contents = document.querySelectorAll('vaadin-grid-cell-content');
            for (var i=0; i<contents.length; i++) {
                var cc = window.getComputedStyle(contents[i]).color;
                if (cc && (cc.indexOf('255, 0, 0')!==-1 || cc.indexOf('255,0,0')!==-1))
                    return true;
            }
            return false;
        """)
        resultado["cancelado"] = bool(cancelado)
        if cancelado:
            log_fn("      ! linha(s) CANCELADA(S) detectada(s)", "warn")
    except Exception:
        pass

    return resultado


# -- Fechar alertas -----------------------------------------------------------
def _fechar_alertas(driver):
    for btn in driver.find_elements(By.TAG_NAME, "button"):
        if "Fechar" in (btn.text or "") or "Close" in (btn.text or ""):
            try:
                btn.click()
            except Exception:
                pass


# -- Consultar resumo ---------------------------------------------------------
def _consultar_resumo(driver, numero, log_fn, regional_fixo=None):
    """
    Consulta um resumo no GSA.
    Se regional_fixo for informado, testa apenas aquele regional.
    Retorna (resultado, regional_usado) onde regional_usado e None se nao encontrou.
    """
    resultado = {"vs": 0, "na": 0, "najr": 0, "cancelado": False}

    # Usa cache de regional se disponivel e nao ha fixo da NF
    if not regional_fixo:
        cached = _cache_get(numero)
        if cached:
            regional_fixo = cached

    regionais = [regional_fixo] if regional_fixo else REGIONAIS

    for i, regional in enumerate(regionais):
        pass
        try:
            if i == 0:
                _ir_faturamento_ng(driver)
                time.sleep(0.5)
            else:
                # Na segunda tentativa, aguarda o combo estar pronto
                # sem renavegar (evita quebrar o estado do Vaadin)
                time.sleep(0.5)

            _fechar_alertas(driver)
            time.sleep(0.3)

            if not _set_regional(driver, regional, log_fn):
                continue

            time.sleep(0.5)
            _fechar_alertas(driver)

            achou = _pesquisar_resumo(driver, numero, log_fn)

            _fechar_alertas(driver)
            time.sleep(0.3)

            if not achou:
                log_fn(f"      Regional {regional}: sem resultado", "warn")
                continue

            # Mostra consultando quando regional ja era fixo (nao e primeira fixacao)
            if regional_fixo:
                log_fn(f"      Consultando assinaturas e validando...", "info")

            grids = driver.find_elements(By.TAG_NAME, "vaadin-grid")
            size = next((g.get_attribute("size") for g in grids if g.is_displayed()), "?")
            pass
            if not regional_fixo:
                log_fn(f"   Regional {regional} fixado para esta NF", "ok")

            resultado = _ler_grid_e_somar(driver, log_fn)
            log_fn(
                f"      TOTAL -> VS={resultado['vs']}  NA={resultado['na']}  NAJR={resultado['najr']}"
                + (" [CANCELADO]" if resultado.get("cancelado") else ""),
                "ok" if any(resultado[k] > 0 for k in ["vs", "na", "najr"]) else "warn"
            )
            # Salva regional no cache para proximas sessoes
            _cache_set(numero, regional)
            return resultado, regional

        except Exception as e:
            import traceback as _tb
            log_fn(f"      Falha: {str(e)[:60]}", "warn")
            log_fn(f"      {_tb.format_exc().splitlines()[-1]}", "warn")
            try: _fechar_alertas(driver)
            except: pass

    log_fn(f"      Resumo {numero}: nao encontrado em nenhum regional", "erro")
    return resultado, None


# -- Ponto de entrada ---------------------------------------------------------
class ScrapeSession:
    """
    Mantem o Chrome e a sessao GSA abertos entre multiplos XMLs.
    Uso:
        session = ScrapeSession(usuario, senha, log_fn, headless=True)
        session.iniciar()
        meses1 = session.buscar(resumos1)
        meses2 = session.buscar(resumos2)
        session.encerrar()
    """

    def __init__(self, usuario, senha, log_fn, headless=True):
        self.usuario  = usuario
        self.senha    = senha
        self.log_fn   = log_fn
        self.headless = headless
        self.driver   = None
        self._regional_fixo = None
        self.cancel_flag = False  # sinaliza cancelamento externo
        self.cancelar = False  # sinaliza cancelamento externo

    def iniciar(self):
        opts = Options()
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1400,900")
        opts.add_argument("--log-level=3")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--blink-settings=imagesEnabled=false")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=opts
        )
        pass
        _login(self.driver, self.usuario, self.senha)
        pass
        pass
        _ir_faturamento_ng(self.driver)
        pass

    def _reconectar(self):
        """Reconecta ao GSA se a sessao caiu."""
        self.log_fn("   Sessao perdida, reconectando...", "warn")
        try:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.iniciar()
            self.log_fn("   Reconexao OK", "ok")
            return True
        except Exception as e:
            self.log_fn(f"   Falha na reconexao: {e}", "erro")
            return False

    def buscar(self, resumos):
        """Busca os resumos usando a sessao ja aberta."""
        if not resumos:
            self.log_fn("   Nenhum resumo no XML.", "erro")
            return {}

        resultado = {}
        self._regional_fixo = None

        for i, num in enumerate(resumos, 1):
            if self.cancelar:
                break

            pct = int((i / len(resumos)) * 100)
            self.log_fn(f"   [{i}/{len(resumos)}] Resumo {num} ({pct}%)", "info")

            tentativa = 0
            while tentativa < 2:
                try:
                    meses, regional_encontrado = _consultar_resumo(
                        self.driver, num, self.log_fn,
                        regional_fixo=self._regional_fixo
                    )
                    if regional_encontrado and not self._regional_fixo:
                        self._regional_fixo = regional_encontrado
                    resultado[num] = meses
                    break
                except Exception as e:
                    err = str(e)
                    # Se foi cancelado, para silenciosamente
                    if self.cancelar:
                        break
                    if any(x in err for x in ["invalid session", "disconnected", "not connected"]):
                        tentativa += 1
                        if tentativa < 2 and self._reconectar():
                            self._regional_fixo = None
                            continue
                    self.log_fn(f"   Resumo {num}: falha na conexao com o GSA", "erro")
                    resultado[num] = {"vs": 0, "na": 0, "najr": 0, "cancelado": False}
                    break

            # Sai do for se cancelado
            if self.cancel_flag:
                break

        return resultado

    def encerrar(self):
        if self.driver:
            self.driver.quit()
            self.driver = None


def buscar_meses_assinaturas(usuario, senha, resumos, log_fn, headless=True):
    """Compatibilidade: cria sessao temporaria para um unico XML."""
    session = ScrapeSession(usuario, senha, log_fn, headless=headless)
    try:
        session.iniciar()
        return session.buscar(resumos)
    finally:
        session.encerrar()






# ── Processamento paralelo ───────────────────────────────────────────────────


import concurrent.futures as _futures
import threading as _threading


def _criar_driver_isolado(headless=True):
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium import webdriver
    from webdriver_manager.chrome import ChromeDriverManager
    import os, stat

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--log-level=3")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--blink-settings=imagesEnabled=false")

    driver_path = ChromeDriverManager().install()
    try:
        os.chmod(driver_path, stat.S_IRWXU | stat.S_IRGRP |
                              stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    except Exception:
        pass

    return webdriver.Chrome(service=Service(driver_path), options=opts)


def _worker_xml(tarefa, usuario, senha, headless, cancel_ref):
    """Cada XML tem driver proprio — totalmente isolado."""
    xml_path     = tarefa["xml_path"]
    resumos      = tarefa["resumos"]
    nf           = tarefa.get("numero_nf", "?")
    log_fn       = tarefa.get("log_fn")
    resultado    = {}
    regional_fix = None
    driver       = None

    def log(msg, tipo=""):
        if log_fn:
            log_fn(msg, tipo)

    try:
        driver = _criar_driver_isolado(headless)

        # Retry login ate 3x
        for tentativa in range(1, 4):
            try:
                _login(driver, usuario, senha)
                log(f"NF-e: {nf} | Login OK", "ok")
                break
            except Exception as e_login:
                if tentativa < 3:
                    log(f"Login tentativa {tentativa}/3 falhou — retentando...", "warn")
                    import time as _tl; _tl.sleep(2)
                    try: driver.quit()
                    except: pass
                    driver = _criar_driver_isolado(headless)
                else:
                    raise Exception(f"Login falhou: {e_login}")

        _ir_faturamento_ng(driver)

        for i, num in enumerate(resumos, 1):
            if cancel_ref[0]:
                break
            pct = int((i / len(resumos)) * 100)
            log(f"   [{i}/{len(resumos)}] Resumo {num} ({pct}%)", "info")

            # Tenta ate 5 vezes — regional fixado nunca muda
            meses = {"vs": 0, "na": 0, "najr": 0, "cancelado": False}
            reg   = None
            MAX_TENTATIVAS = 2
            for tentativa in range(MAX_TENTATIVAS):
                meses, reg = _consultar_resumo(
                    driver, num, log,
                    regional_fixo=regional_fix)
                total     = meses.get("vs",0) + meses.get("na",0) + meses.get("najr",0)
                cancelado = meses.get("cancelado", False)

                # Se regional fixado e retornou vazio = falha de carregamento
                # Sempre retenta com o mesmo regional
                if regional_fix and total == 0 and not cancelado:
                    if tentativa < MAX_TENTATIVAS - 1:
                        log(f"   Resumo {num} vazio no regional {regional_fix}"
                            f" — retentando ({tentativa+2}/{MAX_TENTATIVAS})...", "warn")
                        import time as _tr; _tr.sleep(1)
                        try:
                            _ir_faturamento_ng(driver)
                            import time as _tr2; _tr2.sleep(0.5)
                        except Exception:
                            pass
                        continue
                    else:
                        log(f"   Resumo {num}: assumindo vazio apos {MAX_TENTATIVAS} tentativas", "warn")

                # Sem regional fixado e nao achou = pode nao existir, para
                if not regional_fix and reg is None:
                    break

                # Achou resultado ou cancelado — para
                if total > 0 or cancelado:
                    break

            if reg and not regional_fix:
                regional_fix = reg
                log(f"   Regional {regional_fix} fixado", "ok")
            resultado[num] = meses

        log(f"NF {nf} concluida!", "ok")

    except Exception as e:
        import traceback
        log(f"Erro NF {nf}: {str(e)}", "erro")
        log(traceback.format_exc()[:300], "erro")
    finally:
        if driver:
            try: driver.quit()
            except: pass

    return xml_path, resultado


class ProcessadorParalelo:
    def __init__(self, usuario, senha, headless=True):
        self.usuario  = usuario
        self.senha    = senha
        self.headless = headless
        self._cancel  = [False]
        self._lock    = _threading.Lock()

    def processar(self, tarefas, log_fn, progresso_fn=None):
        if not tarefas:
            return {}

        total      = len(tarefas)
        resultados = {}
        concluidos = [0]

        with _futures.ThreadPoolExecutor(max_workers=total) as ex:
            future_map = {
                ex.submit(_worker_xml, t, self.usuario, self.senha,
                          self.headless, self._cancel): t
                for t in tarefas
            }
            for f in _futures.as_completed(future_map):
                try:
                    xml_path, meses = f.result()
                    resultados[xml_path] = meses
                except Exception:
                    t = future_map[f]
                    resultados[t["xml_path"]] = {}
                with self._lock:
                    concluidos[0] += 1
                    if progresso_fn:
                        progresso_fn(concluidos[0], total,
                                     f"[{concluidos[0]}/{total}] concluidas")

        return resultados

    def cancelar(self):
        self._cancel[0] = True
        # Mata todos os processos chromedriver orfaos
        try:
            import psutil
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    if 'chrome' in proc.info['name'].lower() or                        'chromedriver' in proc.info['name'].lower():
                        proc.kill()
                except Exception:
                    pass
        except ImportError:
            import subprocess, sys
            if sys.platform == 'win32':
                subprocess.run(['taskkill', '/F', '/IM', 'chromedriver.exe'],
                               capture_output=True)
                subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'],
                               capture_output=True)
