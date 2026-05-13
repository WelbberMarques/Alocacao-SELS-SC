import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import time
import base64
import hashlib

from xml_parser import parse_nfe_xml
from excel_writer import preencher_planilha
from preferencias import carregar as _prefs_carregar, salvar as _prefs_salvar, get_tema, TEMAS


def _ofuscar(texto: str) -> str:
    """Ofusca credencial em memoria  nao e criptografia forte, mas evita texto puro."""
    if not texto:
        return ""
    chave = hashlib.md5(b"cpb_sels_sc_2026").digest()
    b = texto.encode()
    r = bytes(b[i] ^ chave[i % len(chave)] for i in range(len(b)))
    return base64.b64encode(r).decode()


def _revelar(ofuscado: str) -> str:
    if not ofuscado:
        return ""
    try:
        chave = hashlib.md5(b"cpb_sels_sc_2026").digest()
        b = base64.b64decode(ofuscado)
        r = bytes(b[i] ^ chave[i % len(chave)] for i in range(len(b)))
        return r.decode()
    except Exception:
        return ""


def _T(tema, key):
    return tema.get(key, "#888888")


class LogBox(tk.Frame):
    def __init__(self, parent, tema, fonte=9, **kwargs):
        super().__init__(parent, bg=_T(tema, "BG"), **kwargs)
        self._tema  = tema
        self._fonte = fonte
        self._build()

    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        t = self._tema
        self._auto_scroll = True
        self._text = tk.Text(
            self, font=("Consolas", self._fonte),
            bg=_T(t, "LOG_BG"), fg=_T(t, "TEXT_DIM"),
            relief="flat", state="disabled", wrap="word",
            padx=10, pady=8,
            insertbackground=_T(t, "TEXT"),
            selectbackground=_T(t, "ACCENT"), spacing1=2,
        )
        self._text.bind("<Enter>", lambda e: setattr(self, "_auto_scroll", False))
        self._text.bind("<Leave>", lambda e: setattr(self, "_auto_scroll", True))
        sb = tk.Scrollbar(self, command=self._text.yview,
                          bg=_T(t, "CARD"), width=8,
                          troughcolor=_T(t, "CARD2"), relief="flat")
        self._text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._text.pack(fill="both", expand=True)
        self._text.tag_config("ok",   foreground=_T(t, "LOG_OK"))
        self._text.tag_config("erro", foreground=_T(t, "LOG_ERRO"))
        self._text.tag_config("info", foreground=_T(t, "LOG_INFO"))
        self._text.tag_config("warn", foreground=_T(t, "LOG_WARN"))
        self._text.tag_config("sep",  foreground=_T(t, "BORDER"))
        self._text.tag_config("head", foreground=_T(t, "LOG_HEAD"),
                               font=("Consolas", self._fonte, "bold"))

    def atualizar_tema(self, tema, fonte=None):
        self._tema  = tema
        if fonte:
            self._fonte = fonte
        self._build()

    def write(self, msg, tipo=""):
        self._text.configure(state="normal")
        self._text.insert("end", msg + "\n", tipo)
        if self._text.yview()[1] >= 0.95:
            self._text.see("end")
        self._text.configure(state="disabled")
        self._text.update_idletasks()

    def search(self, termo):
        self._text.tag_remove("search", "1.0", "end")
        if not termo:
            return
        self._text.tag_config("search",
                               background=_T(self._tema, "ACCENT"),
                               foreground=_T(self._tema, "TEXT"))
        start = "1.0"
        while True:
            pos = self._text.search(termo, start, stopindex="end",
                                    nocase=True)
            if not pos:
                break
            end = f"{pos}+{len(termo)}c"
            self._text.tag_add("search", pos, end)
            start = end

    def clear(self):
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")


class App(tk.Tk):
    def __init__(self, usuario=None):
        super().__init__()
        self.usuario_info    = usuario
        self.papel           = usuario.papel    if usuario else "membro"
        self.usuario_nome    = usuario.usuario  if usuario else "Dev"
        self.usuario_token   = usuario.token    if usuario else ""
        self.usuario_ip      = usuario.ip       if usuario else ""
        self.usuario_maquina = usuario.maquina  if usuario else ""
        self.usuario_id      = getattr(usuario, "usuario_id", "") if usuario else ""

        # Preferencias do usuario
        self._prefs = _prefs_carregar(self.usuario_nome)
        self._tema  = get_tema(self._prefs.get("tema", "escuro"))

        self.title("Alocacao CPB | SELS-SC")
        self.geometry("980x800")
        self.minsize(860, 680)
        self.configure(bg=_T(self._tema, "BG"))
        self.resizable(True, True)

        self.xml_paths    = []
        self.xlsx_path    = tk.StringVar()
        _creds = self._prefs.get("gsa_usuario", "")
        _senha_enc = self._prefs.get("gsa_senha_enc", "")
        _senha_dec = _revelar(_senha_enc) if _senha_enc else ""
        self.usuario_gsa  = tk.StringVar(value=_creds)
        self.senha_gsa    = tk.StringVar(value=_senha_dec)
        self.headless     = tk.BooleanVar(value=self._prefs.get("headless", True))
        self.output_paths = []
        self._running       = False
        self._cancel_flag   = False
        self._gsa_session   = None
        self._proc_paralelo = None
        self._prog_fill     = None
        self._prog_label    = None
        self._prog_pct      = None
        self._prog_tempo    = None
        self._tempo_inicio = 0

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)

    #  Helpers de tema 
    def _t(self, key):
        return _T(self._tema, key)

    def _aplicar_tema(self, nome_tema):
        self._prefs["tema"] = nome_tema
        self._tema = get_tema(nome_tema)
        _prefs_salvar(self._prefs, self.usuario_nome)
        # Aplica tema em tempo real reconstruindo a UI
        self._rebuild()

    def _rebuild(self):
        """Reconstroi toda a UI com o tema atual."""
        # Salva estado
        xmls     = list(self.xml_paths)
        xlsx     = self.xlsx_path.get()
        usr      = self.usuario_gsa.get() if hasattr(self, 'usuario_gsa') else ""
        senha    = self.senha_gsa.get()   if hasattr(self, 'senha_gsa')    else ""
        headless = self.headless.get()    if hasattr(self, 'headless')      else True

        # Atualiza bg da janela principal
        self.configure(bg=self._t("BG"))

        # Destroi e reconstroi
        for w in self.winfo_children():
            w.destroy()
        self._build()

        # Restaura estado
        self.xml_paths = xmls
        for p in xmls:
            nome = os.path.basename(p)
            try:
                d = parse_nfe_xml(p)
                nome = f"{nome}  [NF {d['numero_nf']}]"
            except Exception:
                pass
            self._xml_listbox.insert("end", nome)
        self._xml_count_label.configure(text=f"{len(xmls)} XML(s)")
        self.xlsx_path.set(xlsx)
        if hasattr(self, 'usuario_gsa'):
            self.usuario_gsa.set(usr)
        if hasattr(self, 'senha_gsa'):
            self.senha_gsa.set(senha)
        if hasattr(self, 'headless'):
            self.headless.set(headless)
        self.update_idletasks()

    #  Build UI 
    def _build(self):
        self._build_topbar()
        self._build_header()

        body = tk.Frame(self, bg=self._t("BG"))
        body.pack(fill="both", expand=True, padx=20, pady=14)

        left = tk.Frame(body, bg=self._t("BG"))
        left.pack(side="left", fill="both", expand=False, padx=(0, 10))
        left.configure(width=330)
        left.pack_propagate(False)

        self._build_inputs(left)
        if self.papel == "master":
            self._build_credentials(left)
        self._build_action(left)

        sep = tk.Frame(body, bg=self._t("BORDER"), width=1)
        sep.pack(side="left", fill="y", padx=(0,0))

        right = tk.Frame(body, bg=self._t("BG"))
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self._build_log(right)

        self._build_footer()

    def _checar_pendentes(self):
        """Verifica dispositivos pendentes e notifica no botao Painel Master."""
        def _check():
            try:
                from auth import _get_count
                n = _get_count("dispositivos_aprovados",
                               "status=eq.pendente")
                def _update():
                    if not hasattr(self, '_btn_painel'):
                        return
                    if n > 0:
                        self._btn_painel.configure(
                            text=f"Painel Master ({n})",
                            fg="#ff6666")
                    else:
                        self._btn_painel.configure(
                            text="Painel Master",
                            fg=self._t("TEXT_DIM"))
                self.after(0, _update)
            except Exception:
                pass
        import threading as _th
        _th.Thread(target=_check, daemon=True).start()
        self.after(30000, self._checar_pendentes)

    def _build_topbar(self):
        is_master = self.papel == "master"
        bar_bg    = "#161616" if is_master else self._t("CARD")

        bar = tk.Frame(self, bg=bar_bg, height=34)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text=f"  {self.usuario_nome}",
                 font=("Courier New", 9, "bold" if is_master else "normal"),
                 bg=bar_bg,
                 fg=self._t("TEXT") if is_master else self._t("TEXT_DIM"),
                 anchor="w").pack(side="left", fill="y")

        papel_txt = "[MASTER]" if is_master else "[MEMBRO]"
        papel_cor = "#999999" if is_master else self._t("TEXT_MUTED")
        tk.Label(bar, text=papel_txt,
                 font=("Courier New", 8, "bold"),
                 bg=bar_bg, fg=papel_cor).pack(side="left", fill="y", padx=4)

        tk.Button(bar, text="Sair",
                  font=("Courier New", 8), bg=bar_bg,
                  fg=self._t("TEXT_DIM"), relief="flat", cursor="hand2",
                  command=self._logout).pack(side="right", padx=8, fill="y")

        tk.Button(bar, text="  Preferencias  ",
                  font=("Courier New", 8), bg=self._t("CARD2"),
                  fg=self._t("TEXT"), relief="flat", cursor="hand2",
                  activebackground=self._t("BORDER"),
                  command=self._abrir_preferencias).pack(side="right", fill="y", padx=6)

        if is_master:
            tk.Button(bar, text="Historico",
                      font=("Courier New", 8), bg=bar_bg,
                      fg=self._t("TEXT_DIM"), relief="flat", cursor="hand2",
                      command=self._abrir_historico).pack(side="right", fill="y", padx=2)

            tk.Button(bar, text="  Painel Master  ",
                      font=("Courier New", 8, "bold"),
                      bg=self._t("ACCENT"), fg=self._t("WHITE"),
                      relief="flat", cursor="hand2",
                      command=self._abrir_painel_master).pack(side="right", padx=8, fill="y")

        sep = "#333333" if is_master else self._t("BORDER")
        tk.Frame(self, bg=sep, height=1).pack(fill="x")

    def _build_header(self):
        header = tk.Frame(self, bg=self._t("CARD"), height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tf = tk.Frame(header, bg=self._t("CARD"))
        tf.pack(side="left", padx=20, fill="y")
        tk.Label(tf, text="Alocacao CPB",
                 font=("Segoe UI", 13, "bold"),
                 bg=self._t("CARD"), fg=self._t("TEXT")).pack(anchor="w", pady=(10, 0))
        tk.Label(tf, text="Preenchimento automatico - multiplos XMLs",
                 font=("Segoe UI", 8),
                 bg=self._t("CARD"), fg=self._t("TEXT_DIM")).pack(anchor="w")
        tk.Frame(self, bg=self._t("BORDER"), height=1).pack(fill="x")

    def _section(self, parent, title):
        f = tk.Frame(parent, bg=self._t("BG"))
        f.pack(fill="x", pady=(0, 4))
        tk.Label(f, text=title.upper(),
                 font=("Segoe UI", 8, "bold"),
                 bg=self._t("BG"), fg=self._t("TEXT_MUTED")).pack(anchor="w")
        tk.Frame(parent, bg=self._t("BORDER"), height=1).pack(fill="x", pady=(2, 8))

    def _build_inputs(self, parent):
        self._section(parent, "1  Arquivos de entrada")
        card = tk.Frame(parent, bg=self._t("CARD"), padx=12, pady=12)
        card.pack(fill="x", pady=(0, 10))

        tk.Label(card, text="XMLs das Notas Fiscais",
                 font=("Segoe UI", 9, "bold"),
                 bg=self._t("CARD"), fg=self._t("TEXT_DIM")).pack(anchor="w", pady=(0, 4))

        xml_frame = tk.Frame(card, bg=self._t("CARD2"), pady=6, padx=8)
        xml_frame.pack(fill="x")
        self._xml_listbox = tk.Listbox(
            xml_frame, bg=self._t("CARD2"), fg=self._t("TEXT_DIM"),
            font=("Segoe UI", 9), relief="flat", height=4,
            selectbackground=self._t("ACCENT"),
            selectforeground=self._t("WHITE"),
            activestyle="none", highlightthickness=0)
        sb_xml = tk.Scrollbar(xml_frame, command=self._xml_listbox.yview,
                              bg=self._t("CARD"), troughcolor=self._t("CARD2"),
                              relief="flat", width=8)
        self._xml_listbox.configure(yscrollcommand=sb_xml.set)
        sb_xml.pack(side="right", fill="y")
        self._xml_listbox.pack(fill="x", expand=True)

        btn_row = tk.Frame(card, bg=self._t("CARD"))
        btn_row.pack(fill="x", pady=(6, 0))
        for txt, cmd in [("+ Adicionar", self._add_xmls),
                         ("Remover",     self._remove_xml),
                         ("Limpar",      self._clear_xmls)]:
            tk.Button(btn_row, text=txt,
                      font=("Segoe UI", 9),
                      bg=self._t("ACCENT") if "Adicionar" in txt else self._t("CARD2"),
                      fg=self._t("WHITE") if "Adicionar" in txt else self._t("TEXT_DIM"),
                      relief="flat", padx=8, pady=3, cursor="hand2",
                      command=cmd).pack(side="left", padx=(0, 4))
        self._xml_count_label = tk.Label(
            btn_row, text="0 XML(s)",
            font=("Segoe UI", 8),
            bg=self._t("CARD"), fg=self._t("TEXT_MUTED"))
        self._xml_count_label.pack(side="right")

        tk.Frame(card, bg=self._t("BORDER"), height=1).pack(fill="x", pady=8)

        tk.Label(card, text="Planilha Modelo (.xlsm / .xlsx)",
                 font=("Segoe UI", 9, "bold"),
                 bg=self._t("CARD"), fg=self._t("TEXT_DIM")).pack(anchor="w", pady=(0, 4))
        xlsx_row = tk.Frame(card, bg=self._t("CARD"))
        xlsx_row.pack(fill="x")
        self._xlsx_label = tk.Label(
            xlsx_row, text="Nenhuma planilha selecionada",
            font=("Segoe UI", 8),
            bg=self._t("CARD2"), fg=self._t("TEXT_MUTED"),
            anchor="w", padx=8, pady=6)
        self._xlsx_label.pack(side="left", fill="x", expand=True)
        tk.Button(xlsx_row, text="Selecionar",
                  font=("Segoe UI", 9),
                  bg=self._t("CARD2"), fg=self._t("TEXT_DIM"),
                  relief="flat", padx=8, pady=4, cursor="hand2",
                  command=self._select_xlsx).pack(side="right", padx=(4, 0))

    def _build_credentials(self, parent):
        self._section(parent, "2  Credenciais GSA")
        card = tk.Frame(parent, bg=self._t("CARD"), padx=12, pady=12)
        card.pack(fill="x", pady=(0, 10))
        for label, var, show in [
            ("Usuario GSA", self.usuario_gsa, ""),
            ("Senha GSA",   self.senha_gsa,   "*"),
        ]:
            tk.Label(card, text=label,
                     font=("Segoe UI", 8),
                     bg=self._t("CARD"), fg=self._t("TEXT_DIM")).pack(anchor="w")
            tk.Entry(card, textvariable=var,
                     font=("Segoe UI", 10),
                     bg=self._t("CARD2"), fg=self._t("TEXT"),
                     insertbackground=self._t("TEXT"),
                     relief="flat", show=show).pack(fill="x", ipady=6, pady=(2, 8))
            tk.Frame(card, bg=self._t("BORDER"), height=1).pack(fill="x", pady=(0, 4))
        tk.Checkbutton(card, text="Modo silencioso (sem janela Chrome)",
                       variable=self.headless,
                       font=("Segoe UI", 8),
                       bg=self._t("CARD"), fg=self._t("TEXT_DIM"),
                       selectcolor=self._t("CARD2"),
                       activebackground=self._t("CARD"),
                       relief="flat").pack(anchor="w", pady=(4, 0))

    def _build_action(self, parent):
        sec = "3" if self.papel == "master" else "2"
        self._section(parent, f"{sec}  Acao")
        self._btn = tk.Button(
            parent, text="  GERAR PLANILHAS PREENCHIDAS",
            font=("Segoe UI", 10, "bold"),
            bg=self._t("ACCENT"), fg=self._t("WHITE"),
            relief="flat", bd=0, pady=12,
            cursor="hand2", command=self._run_thread)
        self._btn.pack(fill="x")
        self._btn.bind("<Enter>", lambda e: self._btn.configure(
            bg="#777777") if not self._running else None)
        self._btn.bind("<Leave>", lambda e: self._btn.configure(
            bg=self._t("ACCENT")) if not self._running else None)
        self._btn_cancel = tk.Button(
            parent, text="  CANCELAR",
            font=("Segoe UI", 10),
            bg=self._t("CARD2"), fg=self._t("TEXT_DIM"),
            relief="flat", bd=0, pady=10,
            cursor="hand2", command=self._cancelar, state="disabled")
        self._btn_cancel.pack(fill="x", pady=(6, 0))
        self._btn_cancel.bind("<Enter>", lambda e:
            self._btn_cancel.configure(bg=self._t("ERROR_C"),
                                       fg=self._t("WHITE"))
            if str(self._btn_cancel.cget("state")) == "normal" else None)
        self._btn_cancel.bind("<Leave>", lambda e:
            self._btn_cancel.configure(bg=self._t("CARD2"),
                                       fg=self._t("TEXT_DIM"))
            if str(self._btn_cancel.cget("state")) == "normal" else None)
        self._btn_save = tk.Button(
            parent, text="  SALVAR PLANILHA",
            font=("Segoe UI", 10),
            bg=self._t("CARD2"), fg=self._t("TEXT_DIM"),
            relief="flat", bd=0, pady=10,
            cursor="hand2", command=self._save_files, state="disabled")
        self._btn_save.pack(fill="x", pady=(6, 0))

        self._btn_reprocess = tk.Button(
            parent, text="  REPROCESSAR XML",
            font=("Segoe UI", 9),
            bg=self._t("CARD2"), fg=self._t("TEXT_DIM"),
            relief="flat", bd=0, pady=8,
            cursor="hand2", command=self._reprocessar, state="disabled")
        self._btn_reprocess.pack(fill="x", pady=(4, 0))

    def _build_log(self, parent):
        self._section(parent, "Log de execucao")

        # Barra de progresso  area destacada
        prog_box = tk.Frame(parent, bg=self._t("CARD2"),
                            pady=8, padx=10)
        prog_box.pack(fill="x", pady=(0, 6))

        # Linha 1: label + pct + tempo
        prog_top = tk.Frame(prog_box, bg=self._t("CARD2"))
        prog_top.pack(fill="x")
        self._prog_label = tk.Label(prog_top, text="Aguardando...",
                                    font=("Courier New", 9),
                                    bg=self._t("CARD2"),
                                    fg=self._t("TEXT_DIM"), anchor="w")
        self._prog_label.pack(side="left")
        self._prog_tempo = tk.Label(prog_top, text="",
                                    font=("Courier New", 8),
                                    bg=self._t("CARD2"),
                                    fg=self._t("TEXT_MUTED"))
        self._prog_tempo.pack(side="right", padx=(8,0))
        self._prog_pct = tk.Label(prog_top, text="0%",
                                  font=("Courier New", 9, "bold"),
                                  bg=self._t("CARD2"),
                                  fg=self._t("TEXT"), anchor="e")
        self._prog_pct.pack(side="right")

        # Linha 2: barra
        bar_track = tk.Frame(prog_box, bg=self._t("BORDER"), height=8)
        bar_track.pack(fill="x", pady=(6, 0))
        self._prog_fill = tk.Frame(bar_track, bg=self._t("ACCENT"), height=8)
        self._prog_fill.place(x=0, y=0, relwidth=0, height=8)

        # Busca + fonte
        search_frame = tk.Frame(parent, bg=self._t("BG"))
        search_frame.pack(fill="x", pady=(0, 4))
        tk.Label(search_frame, text="Buscar:",
                 font=("Segoe UI", 8),
                 bg=self._t("BG"), fg=self._t("TEXT_MUTED")).pack(side="left")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._buscar_log())
        tk.Entry(search_frame, textvariable=self._search_var,
                 font=("Segoe UI", 9),
                 bg=self._t("CARD2"), fg=self._t("TEXT"),
                 insertbackground=self._t("TEXT"),
                 relief="flat", width=20).pack(side="left", padx=(4, 8), ipady=3)
        tk.Label(search_frame, text="Fonte:",
                 font=("Segoe UI", 8),
                 bg=self._t("BG"), fg=self._t("TEXT_MUTED")).pack(side="left")
        self._fonte_var = tk.IntVar(value=self._prefs.get("fonte_log", 9))
        for sz in [8, 9, 10, 11]:
            tk.Radiobutton(search_frame, text=str(sz),
                           variable=self._fonte_var, value=sz,
                           font=("Segoe UI", 8),
                           bg=self._t("BG"), fg=self._t("TEXT_DIM"),
                           selectcolor=self._t("CARD2"),
                           activebackground=self._t("BG"),
                           command=self._alterar_fonte).pack(side="left", padx=2)

        # Container de logs  modo unico ou multiplos paineis
        self._log_container = tk.Frame(parent, bg=self._t("BG"))
        self._log_container.pack(fill="both", expand=True)

        # Log principal (modo sequencial ou geral)
        self._log = LogBox(self._log_container, self._tema,
                           fonte=self._prefs.get("fonte_log", 9))
        self._log.pack(fill="both", expand=True)

        # Dict de logs paralelos {idx: LogBox}
        self._logs_paralelos = {}




    def _build_footer(self):
        tk.Frame(self, bg=self._t("BORDER"), height=1).pack(fill="x")
        footer = tk.Frame(self, bg=self._t("CARD"), height=28)
        footer.pack(fill="x")
        footer.pack_propagate(False)
        self._status_label = tk.Label(footer, text="Pronto",
                                      font=("Segoe UI", 8),
                                      bg=self._t("CARD"),
                                      fg=self._t("TEXT_MUTED"))
        self._status_label.pack(side="left", padx=14)
        self._online_label = tk.Label(footer, text=" online",
                                      font=("Segoe UI", 7),
                                      bg=self._t("CARD"), fg="#4a4a4a")
        self._online_label.pack(side="left", padx=(0, 8))
        self._checar_conexao()
        tk.Label(footer,
                 text="Ctrl+O: abrir XML  |  F5: processar  |  Esc: cancelar",
                 font=("Segoe UI", 7),
                 bg=self._t("CARD"), fg=self._t("TEXT_MUTED")).pack(side="right", padx=14)
        # Atalhos
        self.bind("<Control-o>", lambda e: self._add_xmls())
        self.bind("<F5>",        lambda e: self._run_thread())
        self.bind("<Escape>",    lambda e: self._cancelar())
        self.bind("<Control-s>", lambda e: self._save_files())

    #  Helpers 
    def log(self, msg, tipo=""):
        self.after(0, lambda: self._log.write(msg, tipo))

    def status(self, msg, cor=None):
        cor = cor or self._t("TEXT_MUTED")
        self.after(0, lambda: self._status_label.configure(text=msg, fg=cor))

    def _set_progresso(self, atual, total, label=""):
        if total <= 0 or not self._prog_fill:
            return
        pct = atual / total
        self._prog_fill.place(x=0, y=0, relwidth=pct, height=8)
        if self._prog_label:
            self._prog_label.configure(text=label)
        if self._prog_pct:
            self._prog_pct.configure(text=f"{int(pct*100)}%")
        if self._prog_tempo and hasattr(self, "_tempo_inicio"):
            import time as _ti
            seg_dec = _ti.time() - self._tempo_inicio
            if pct > 0.01:
                restante = int((seg_dec / pct) * (1 - pct))
                mr, sr = divmod(restante, 60)
                eta = f"~{mr}m{sr:02d}s restantes" if mr else f"~{sr}s restantes"
            else:
                eta = "calculando..."
            self._prog_tempo.configure(text=eta)
        # Tempo estimado
        if self._tempo_inicio and atual > 0:
            decorrido  = time.time() - self._tempo_inicio
            por_item   = decorrido / atual
            restante   = por_item * (total - atual)
            mins, secs = divmod(int(restante), 60)
            self._prog_tempo.configure(
                text=f"~{mins}m{secs:02d}s restantes" if mins else f"~{secs}s restantes")
        self.update_idletasks()

    def _animar_progresso(self, atual, total, label=""):
        self.after(0, lambda: self._set_progresso(atual, total, label))

    def _reset_progresso(self):
        if self._prog_fill:
            self._prog_fill.place(x=0, y=0, relwidth=0, height=8)
        if self._prog_label:
            self._prog_label.configure(text="Aguardando...")
        if self._prog_pct:
            self._prog_pct.configure(text="0%")
        if hasattr(self, "_prog_tempo") and self._prog_tempo:
            self._prog_tempo.configure(text="")
        self._prog_tempo.configure(text="")

    def _buscar_log(self):
        self._log.search(self._search_var.get())

    def _alterar_fonte(self):
        sz = self._fonte_var.get()
        self._prefs["fonte_log"] = sz
        _prefs_salvar(self._prefs, self.usuario_nome)
        self._log.atualizar_tema(self._tema, sz)

    #  Preferencias 
    def _abrir_preferencias(self):
        win = tk.Toplevel(self)
        win.title("Preferencias")
        win.geometry("380x320")
        win.configure(bg=self._t("BG"))
        win.resizable(False, False)
        win.grab_set()

        tk.Label(win, text="Preferencias",
                 font=("Courier New", 11, "bold"),
                 bg=self._t("BG"), fg=self._t("TEXT")).pack(anchor="w", padx=24, pady=(20, 12))



        # Som
        tk.Label(win, text="NOTIFICACOES",
                 font=("Segoe UI", 8, "bold"),
                 bg=self._t("BG"), fg=self._t("TEXT_MUTED")).pack(anchor="w", padx=24, pady=(16, 0))
        tk.Frame(win, bg=self._t("BORDER"), height=1).pack(fill="x", padx=24, pady=(2, 8))

        som_var = tk.BooleanVar(value=self._prefs.get("notif_som", True))
        tk.Checkbutton(win, text="Som ao concluir processamento",
                       variable=som_var,
                       font=("Segoe UI", 9),
                       bg=self._t("BG"), fg=self._t("TEXT_DIM"),
                       selectcolor=self._t("CARD2"),
                       activebackground=self._t("BG"),
                       relief="flat").pack(anchor="w", padx=32)

        # Backup
        tk.Label(win, text="BACKUP AUTOMATICO",
                 font=("Segoe UI", 8, "bold"),
                 bg=self._t("BG"), fg=self._t("TEXT_MUTED")).pack(anchor="w", padx=24, pady=(16, 0))
        tk.Frame(win, bg=self._t("BORDER"), height=1).pack(fill="x", padx=24, pady=(2, 8))

        backup_frame = tk.Frame(win, bg=self._t("BG"))
        backup_frame.pack(fill="x", padx=24)
        backup_var = tk.StringVar(value=self._prefs.get("backup_pasta", ""))
        backup_label = tk.Label(backup_frame,
                                textvariable=backup_var,
                                font=("Segoe UI", 8),
                                bg=self._t("CARD2"), fg=self._t("TEXT_DIM"),
                                anchor="w", padx=6, pady=4)
        backup_label.pack(side="left", fill="x", expand=True)
        def escolher_pasta():
            p = filedialog.askdirectory(title="Pasta de backup")
            if p:
                backup_var.set(p)
        tk.Button(backup_frame, text="...",
                  font=("Segoe UI", 9),
                  bg=self._t("CARD2"), fg=self._t("TEXT_DIM"),
                  relief="flat", padx=6, cursor="hand2",
                  command=escolher_pasta).pack(side="right", padx=(4, 0))

        def salvar_prefs():
            self._prefs["notif_som"]    = som_var.get()
            self._prefs["backup_pasta"] = backup_var.get()
            win.grab_release()
            win.destroy()

        tk.Button(win, text="Salvar",
                  font=("Segoe UI", 10, "bold"),
                  bg=self._t("ACCENT"), fg=self._t("WHITE"),
                  relief="flat", pady=10, cursor="hand2",
                  command=salvar_prefs).pack(fill="x", padx=24, pady=14)

    #  Acoes de arquivo 
    def _on_drop_xml(self, event):
        """Recebe arquivos arrastados para a lista."""
        import re as _re
        raw = event.data
        # tkinterdnd2 retorna paths entre {} se tiver espacos
        paths = _re.findall(r'{([^}]+)}|(\S+)', raw)
        paths = [p[0] or p[1] for p in paths]
        for p in paths:
            if p.lower().endswith('.xml') and p not in self.xml_paths:
                self.xml_paths.append(p)
                nome = os.path.basename(p)
                # Tenta ler NF para mostrar na lista
                try:
                    d = parse_nfe_xml(p)
                    nome = f"{nome}  [NF {d['numero_nf']}]"
                except Exception:
                    pass
                self._xml_listbox.insert("end", nome)
        self._xml_count_label.configure(text=f"{len(self.xml_paths)} XML(s)")
        if paths:
            self._atualizar_preview()

    def _mover_xml(self, direcao):
        """Move XML selecionado para cima (-1) ou baixo (+1) na lista."""
        sel = self._xml_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        novo = idx + direcao
        if novo < 0 or novo >= len(self.xml_paths):
            return
        # Troca na lista e no listbox
        self.xml_paths[idx], self.xml_paths[novo] =             self.xml_paths[novo], self.xml_paths[idx]
        txt_idx  = self._xml_listbox.get(idx)
        txt_novo = self._xml_listbox.get(novo)
        self._xml_listbox.delete(idx)
        self._xml_listbox.insert(idx, txt_novo)
        self._xml_listbox.delete(novo)
        self._xml_listbox.insert(novo, txt_idx)
        self._xml_listbox.selection_set(novo)

    def _add_xmls(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("XML", "*.xml")],
            initialdir=self._prefs.get("ultima_pasta_xml", ""))
        for p in paths:
            if p not in self.xml_paths:
                self.xml_paths.append(p)
                nome = os.path.basename(p)
                try:
                    d = parse_nfe_xml(p)
                    nome = f"{nome}  [NF {d['numero_nf']}]"
                except Exception:
                    pass
                self._xml_listbox.insert("end", nome)
        if paths:
            self._prefs["ultima_pasta_xml"] = os.path.dirname(list(paths)[-1])
            _prefs_salvar(self._prefs, self.usuario_nome)
        self._xml_count_label.configure(text=f"{len(self.xml_paths)} XML(s)")
        if paths:
            self._atualizar_preview()

    def _atualizar_preview(self):
        """Mostra preview dos XMLs no log antes de processar."""
        if not hasattr(self, '_log'):
            return
        self._log.clear()
        self._log.write(f"  {len(self.xml_paths)} XML(s) carregado(s):", "head")
        self._log.write("-" * 52, "sep")
        total_vs = total_na = total_najr = 0
        for p in self.xml_paths:
            try:
                from xml_parser import parse_nfe_xml
                d = parse_nfe_xml(p)
                total_vs   += d["vs"]
                total_na   += d["na"]
                total_najr += d["najr"]
                self._log.write(
                    f"  NF {d['numero_nf']}  |  "
                    f"VS:{d['vs']}  NA:{d['na']}  NAJR:{d['najr']}  |  "
                    f"{len(d['resumos'])} resumo(s)", "ok")
            except Exception as e:
                self._log.write(f"  {os.path.basename(p)}: erro ao ler", "erro")
        self._log.write("-" * 52, "sep")
        self._log.write(
            f"  TOTAL  VS:{total_vs}  NA:{total_na}  NAJR:{total_najr}", "head")

    def _remove_xml(self):
        sel = self._xml_listbox.curselection()
        if sel:
            idx = sel[0]
            self._xml_listbox.delete(idx)
            self.xml_paths.pop(idx)
            self._xml_count_label.configure(text=f"{len(self.xml_paths)} XML(s)")

    def _clear_xmls(self):
        self.xml_paths = []
        self._xml_listbox.delete(0, "end")
        self._xml_count_label.configure(text="0 XML(s)")

    def _select_xlsx(self):
        path = filedialog.askopenfilename(
            filetypes=[("Excel com macro", "*.xlsm"),
                       ("Excel", "*.xlsx"),
                       ("Todos Excel", "*.xls*")])
        if path:
            self.xlsx_path.set(path)
            self._xlsx_label.configure(
                text=os.path.basename(path), fg=self._t("TEXT_DIM"))

    #  Validacao 
    def _validate(self):
        if not self.xml_paths:
            messagebox.showwarning("Aviso", "Selecione ao menos um XML.")
            return False
        if not self.xlsx_path.get():
            messagebox.showwarning("Aviso", "Selecione a planilha modelo.")
            return False
        if self.papel == "master":
            if not self.usuario_gsa.get().strip():
                messagebox.showwarning("Aviso", "Informe o usuario GSA.")
                return False
            if not self.senha_gsa.get().strip():
                messagebox.showwarning("Aviso", "Informe a senha GSA.")
                return False
        return True

    #  Cancelar 
    def _cancelar(self):
        if not self._running:
            return
        self._cancel_flag = True
        if self._proc_paralelo:
            try:
                self._proc_paralelo.cancelar()
            except Exception:
                pass
        if self._gsa_session:
            self._gsa_session.cancel_flag = True
            try:
                self._gsa_session.driver.quit()
            except Exception:
                pass
        self._btn_cancel.configure(
            state="disabled", text="  Cancelando...",
            bg=self._t("WARNING"))
        self.status("Cancelando...", self._t("WARNING"))

    #  Run 
    def _run_thread(self):
        if self._running:
            return
        if not self._validate():
            return
        self._running = True
        self._cancel_flag = False
        self.output_paths = []
        self._reset_progresso()
        self._tempo_inicio = time.time()
        self._btn.configure(state="disabled", text="  Processando...")
        self._btn_cancel.configure(
            state="normal",
            bg=self._t("ERROR_C"), fg=self._t("WHITE"), text="  CANCELAR")
        self._btn_save.configure(
            state="disabled",
            bg=self._t("CARD2"), fg=self._t("TEXT_DIM"))
        t = threading.Thread(target=self._run, daemon=True)
        t.start()
        # Aguarda _run montar as tarefas (max 5s) e cria paineis na thread principal
        self._aguardar_e_criar_paineis()

    def _run(self):
        """Roda em thread secundaria  NUNCA chama widgets diretamente."""
        import queue as _queue
        import threading as _th
        import time as _t2
        from openpyxl import load_workbook as _load
        from excel_writer import _ler_consulta1 as _lc1
        from site_scraper import ProcessadorParalelo

        def ui(fn): self.after(0, fn)
        def log(msg, tipo=""):
            def _escreve(m=msg, t=tipo):
                try:
                    # Tenta escrever no log principal seguro
                    lp = getattr(self, '_log_principal', None) or self._log
                    lp.write(m, t)
                except Exception:
                    pass
            ui(_escreve)

        planilha_acumulada = None
        try:
            total = len(self.xml_paths)
            ui(lambda: self._log.clear())
            log("-" * 52, "sep")
            log(f"  PROCESSANDO {total} XML(s) EM PARALELO", "head")
            log("-" * 52, "sep")

            ts   = _t2.strftime("%Y%m%d_%H%M%S")
            base, _ = os.path.splitext(self.xlsx_path.get())
            planilha_acumulada = f"{base}_preenchida_{ts}.xlsx"
            wb = _load(self.xlsx_path.get(), keep_vba=False)
            wb.save(planilha_acumulada)
            del wb
            log(f" Saida: {os.path.basename(planilha_acumulada)}", "info")

            _totais = {}
            try:
                keep = self.xlsx_path.get().lower().endswith('.xlsm')
                wbc  = _load(self.xlsx_path.get(), keep_vba=keep, data_only=True)
                _totais = _lc1(wbc, lambda m, t="": log(m, t))
            except Exception as ec:
                log(f" Consulta1: {ec}", "warn")

            tarefas = []
            for i, xp in enumerate(self.xml_paths):
                try:
                    d = parse_nfe_xml(xp)
                    tarefas.append({
                        "idx": i, "xml_path": xp, "dados": d,
                        "resumos": d["resumos"], "numero_nf": d["numero_nf"],
                    })
                    log(f" NF {d['numero_nf']}  VS:{d['vs']}"
                        f"  NA:{d['na']}  NAJR:{d['najr']}"
                        f"  {len(d['resumos'])} resumo(s)", "ok")
                except Exception as e:
                    log(f" Erro: {os.path.basename(xp)}: {e}", "erro")

            if not tarefas:
                ui(self._finalizar_btn)
                return

            n   = len(tarefas)

            # Sinaliza thread principal para criar paineis
            self._tarefas_para_painel = tarefas

            fila = _queue.Queue()

            def mk_log(idx):
                def fn(msg, tipo=""):
                    fila.put((idx, msg, tipo))
                return fn

            for t in tarefas:
                t["log_fn"] = mk_log(t["idx"])

            self._fila_log           = fila
            self._paralelo_pronto    = _th.Event()
            self._resultados_par     = {}
            self._tarefas_par        = tarefas
            self._planilha_par       = planilha_acumulada
            self._totais_par         = _totais
            self._n_par              = n
            self._concluidos_par     = [0]
            self._resumos_concluidos = {}
            self._total_resumos_par  = sum(len(t["resumos"]) for t in tarefas)

            usr = self.usuario_gsa.get().strip() if self.papel == "master" else ""
            pwd = self.senha_gsa.get().strip()   if self.papel == "master" else ""
            # Salva usuario GSA nas preferencias
            if usr:
                self._prefs["gsa_usuario"]  = usr
                self._prefs["gsa_senha_enc"] = _ofuscar(pwd)
                _prefs_salvar(self._prefs, self.usuario_nome)
            proc = ProcessadorParalelo(usr, pwd, headless=self.headless.get())
            self._proc_paralelo = proc

            # Mostra resumo de cada XML antes de iniciar
            total_resumos = sum(len(t["resumos"]) for t in tarefas)
            log(f"\n  {n} Chrome(s) | {total_resumos} resumos no total", "head")
            log("" * 52, "sep")
            for t in tarefas:
                log(f"  XML {t['idx']+1}: NF {t['numero_nf']}"
                    f"  ({len(t['resumos'])} resumos)", "info")
            log("" * 52, "sep")
            ui(lambda: self.status(f"Processando {n} XML(s)...",
                                   self._t("WARNING")))

            def bg():
                res = proc.processar(tarefas,
                                     log_fn=lambda m, t="": None,
                                     progresso_fn=None)
                self._resultados_par = res
                self._paralelo_pronto.set()

            _th.Thread(target=bg, daemon=True).start()
            ui(lambda: self.after(50, self._poll))

        except Exception as e:
            ui(lambda err=str(e): (
                self._log.write(f"\n ERRO: {err}", "erro"),
                messagebox.showerror("Erro", err)
            ))
            ui(self._finalizar_btn)


    def _poll(self):
        """Polling da fila  roda na thread principal a cada 50ms."""
        import queue as _queue

        logs    = getattr(self, '_logs_xml', {})
        paineis = getattr(self, '_paineis_xml', [])

        # Aguarda paineis estarem prontos
        if not logs and self._running:
            self.after(100, self._poll)
            return

        for _ in range(500):
            try:
                idx, msg, tipo = self._fila_log.get_nowait()

                if idx in logs:
                    try:
                        txt = logs[idx]
                        txt.configure(state="normal")
                        tag = tipo if tipo in ("ok","erro","info","warn","head") else "info"
                        txt.insert("end", msg + "\n", tag)
                        txt.see("end")
                        txt.configure(state="disabled")
                        if idx < len(paineis):
                            if "concluida!" in msg.lower():
                                paineis[idx].configure(text="concluido!")
                            elif "Login OK" in msg:
                                paineis[idx].configure(text="processando...")
                    except Exception:
                        pass

                if "TOTAL ->" in msg:
                    self._resumos_concluidos[idx] =                         self._resumos_concluidos.get(idx, 0) + 1
                    feitos = sum(self._resumos_concluidos.values())
                    total  = getattr(self, '_total_resumos_par', 1)
                    self._set_progresso(feitos, total,
                                        f"{feitos}/{total} resumos")

                if "concluida!" in msg.lower():
                    self._concluidos_par[0] += 1
                    c = self._concluidos_par[0]
                    n = self._n_par
                    self.title(f"CPB Alocacao  {c}/{n} concluidos")

            except _queue.Empty:
                break

        if not self._paralelo_pronto.is_set() or not self._fila_log.empty():
            self.after(50, self._poll)
        else:
            self._restaurar_log()
            self._finalizar_par()

    def _finalizar_par(self):
        try:
            resultados = self._resultados_par
            if self._cancel_flag:
                try: os.remove(self._planilha_par)
                except: pass
                self.status("Cancelado.", self._t("TEXT_MUTED"))
                self._finalizar_btn()
                return

            self.log(f"\n{'-'*52}", "sep")
            self.log("  Preenchendo planilha...", "head")
            for t in self._tarefas_par:
                d = t["dados"]
                m = resultados.get(t["xml_path"], {})
                self.log(f" Aba NF-{d['numero_nf']}...", "info")
                preencher_planilha(
                    self._planilha_par, d, m, self.log,
                    totais_consulta=self._totais_par)

            self.output_paths = [self._planilha_par]
            self._animar_progresso(1, 1, "Concluido!")

            import time as _t3
            ts = int(_t3.time() - self._tempo_inicio)
            ms, ss = divmod(ts, 60)
            tp = f"{ms}m{ss:02d}s" if ms else f"{ss}s"

            self.log(f"\n{'-'*52}", "sep")
            self.log(f"  {self._n_par} XML(s) PROCESSADO(S)", "ok")
            self.log(f"  {os.path.basename(self._planilha_par)}", "ok")
            self.log(f"  Tempo: {tp}", "info")
            self.status(f"Concluido em {tp}!", self._t("SUCCESS"))

            if self._prefs.get("notif_som", True):
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except: pass
            # Notificacao Windows toast
            try:
                from win10toast import ToastNotifier
                ToastNotifier().show_toast(
                    "CPB Alocacao",
                    f"{self._n_par} XML(s) processado(s) com sucesso!",
                    duration=5, threaded=True)
            except Exception:
                pass

            bk = self._prefs.get("backup_pasta", "")
            if bk and os.path.isdir(bk):
                import shutil
                shutil.copy2(self._planilha_par,
                    os.path.join(bk, os.path.basename(self._planilha_par)))

            self._btn_save.configure(
                state="normal", bg=self._t("SUCCESS"),
                fg=self._t("WHITE"), text="  SALVAR PLANILHA")



            try:
                from auth import registrar_historico, _get_todos_ips
                _ips = _get_todos_ips()
                registrar_historico(
                    usuario_id=self.usuario_id, nome=self.usuario_nome,
                    xmls=[os.path.basename(p) for p in self.xml_paths],
                    planilha=os.path.basename(self._planilha_par),
                    divergencias=0, ip=self.usuario_ip,
                    maquina=self.usuario_maquina,
                    ip_real=_ips.get("real", ""))
            except: pass

        except Exception as e:
            self.log(f"\n ERRO: {e}", "erro")
            messagebox.showerror("Erro", str(e))
        finally:
            self._finalizar_btn()



    def _finalizar_btn(self):
        self._running       = False
        self._cancel_flag   = False
        self._proc_paralelo = None
        self._gsa_session   = None
        self.title("Alocacao CPB | SELS-SC")
        self._btn.configure(
            state="normal", text="  GERAR PLANILHAS PREENCHIDAS")
        self._btn_cancel.configure(
            state="disabled", bg=self._t("CARD2"),
            fg=self._t("TEXT_DIM"), text="  CANCELAR")


    def _aguardar_e_criar_paineis(self, tentativas=0):
        """Aguarda _run definir tarefas e cria paineis na thread principal."""
        if hasattr(self, '_tarefas_para_painel') and self._tarefas_para_painel:
            tarefas = self._tarefas_para_painel
            self._tarefas_para_painel = None
            self._criar_paineis_xml(tarefas)
        elif self._running and tentativas < 100:
            self.after(50, lambda: self._aguardar_e_criar_paineis(tentativas+1))

    def _criar_paineis_xml(self, tarefas):
        n     = len(tarefas)
        cores = ["#1a3a1a","#1a2a3a","#3a2a1a","#3a1a2a",
                 "#2a1a3a","#1a3a3a","#3a3a1a","#2a2a1a",
                 "#1a1a3a","#3a2a2a"]

        self._logs_xml    = {}
        self._paineis_xml = []

        for w in self._log_container.winfo_children():
            w.destroy()

        pai = tk.Frame(self._log_container, bg=self._t("BG"))
        pai.pack(fill="both", expand=True)
        self._pai_paineis = pai

        if n <= 3:
            grupos = [list(range(n))]
        else:
            mid    = (n + 1) // 2
            grupos = [list(range(mid)), list(range(mid, n))]

        for grupo in grupos:
            # PanedWindow para redimensionamento proporcional
            paned = tk.PanedWindow(pai, orient="horizontal",
                                   bg=self._t("BG"),
                                   sashwidth=4,
                                   sashrelief="flat",
                                   opaqueresize=True)
            paned.pack(fill="both", expand=True, pady=1)

            for idx in grupo:
                cor   = cores[idx % len(cores)]
                outer = tk.Frame(paned, bg=self._t("BG"))
                paned.add(outer, stretch="always")

                # Header
                hdr = tk.Frame(outer, bg=cor, height=24)
                hdr.pack(fill="x")
                hdr.pack_propagate(False)
                nf       = tarefas[idx].get("numero_nf","?")
                xml_path = tarefas[idx].get("xml_path","")
                xml_nome = os.path.basename(xml_path) if xml_path else f"XML {idx+1}"
                tk.Label(hdr, text=f" {xml_nome} · NF {nf}",
                         font=("Courier New", 8, "bold"),
                         bg=cor, fg="#ffffff").pack(
                             side="left", fill="y", padx=6)
                st = tk.Label(hdr, text="iniciando...",
                              font=("Courier New", 7),
                              bg=cor, fg="#cccccc")
                st.pack(side="right", padx=6, fill="y")
                self._paineis_xml.append(st)

                # Text + scrollbar
                frame_txt = tk.Frame(outer, bg=self._t("LOG_BG"))
                frame_txt.pack(fill="both", expand=True)

                sb = tk.Scrollbar(frame_txt, bg=self._t("CARD"),
                                  troughcolor=self._t("CARD2"),
                                  relief="flat", width=8)
                sb.pack(side="right", fill="y")

                txt = tk.Text(frame_txt,
                              font=("Consolas", self._prefs.get("fonte_log",8)),
                              bg=self._t("LOG_BG"),
                              fg=self._t("TEXT_DIM"),
                              relief="flat", state="disabled",
                              wrap="word", padx=6, pady=4,
                              yscrollcommand=sb.set)
                txt.pack(fill="both", expand=True)
                sb.config(command=txt.yview)

                txt.tag_config("ok",   foreground=self._t("LOG_OK"))
                txt.tag_config("erro", foreground=self._t("LOG_ERRO"))
                txt.tag_config("info", foreground=self._t("LOG_INFO"))
                txt.tag_config("warn", foreground=self._t("LOG_WARN"))
                txt.tag_config("head", foreground=self._t("LOG_HEAD"),
                               font=("Consolas",
                                     self._prefs.get("fonte_log",8), "bold"))

                self._logs_xml[idx] = txt

        # _log aponta para painel 0  mas nao usa LogBox
        # Usamos _log_principal para o log geral
        self._log_principal = self._log
        pai.update()


    def _restaurar_log(self):
        if hasattr(self, '_pai_paineis') and self._pai_paineis:
            try:
                self._pai_paineis.destroy()
            except Exception:
                pass
        self._logs_xml = {}
        self._paineis_xml = []
        for w in self._log_container.winfo_children():
            w.destroy()
        self._log = LogBox(self._log_container, self._tema,
                           fonte=self._prefs.get("fonte_log", 9))
        self._log.pack(fill="both", expand=True)
        self._log_principal = self._log

    def _reprocessar(self):
        """Reprocessa o XML selecionado na lista."""
        sel = self._xml_listbox.curselection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um XML na lista.")
            return
        if not self.output_paths:
            messagebox.showwarning("Aviso", "Gere a planilha primeiro.")
            return
        idx  = sel[0]
        path = self.xml_paths[idx]
        if not messagebox.askyesno("Reprocessar",
                f"Reprocessar:\n{os.path.basename(path)}?"):
            return
        self._running     = True
        self._cancel_flag = False
        self._btn.configure(state="disabled", text="  Reprocessando...")
        self._btn_cancel.configure(state="normal",
            bg=self._t("ERROR_C"), fg=self._t("WHITE"))

        import threading as _th
        import queue as _queue
        from site_scraper import ProcessadorParalelo

        def run():
            try:
                from openpyxl import load_workbook as _load
                from excel_writer import _ler_consulta1 as _lc1
                dados = parse_nfe_xml(path)
                fila  = _queue.Queue()
                tarefa = {
                    "idx": 0, "xml_path": path,
                    "dados": dados, "resumos": dados["resumos"],
                    "numero_nf": dados["numero_nf"],
                    "log_fn": lambda m, t="": fila.put((0, m, t))
                }
                _totais = {}
                try:
                    keep = self.xlsx_path.get().lower().endswith('.xlsm')
                    wb   = _load(self.xlsx_path.get(), keep_vba=keep, data_only=True)
                    _totais = _lc1(wb, lambda m, t="": None)
                except Exception:
                    pass

                self._fila_log        = fila
                self._paralelo_pronto = _th.Event()
                self._resultados_par  = {}
                self._tarefas_par     = [tarefa]
                self._planilha_par    = self.output_paths[0]
                self._totais_par      = _totais
                self._n_par           = 1
                self._concluidos_par  = [0]

                usr = self.usuario_gsa.get().strip() if self.papel == "master" else ""
                pwd = self.senha_gsa.get().strip()   if self.papel == "master" else ""
                proc = ProcessadorParalelo(usr, pwd, headless=self.headless.get())
                self._proc_paralelo = proc

                def bg():
                    res = proc.processar([tarefa],
                                         log_fn=lambda m, t="": None,
                                         progresso_fn=None)
                    self._resultados_par = res
                    self._paralelo_pronto.set()

                _th.Thread(target=bg, daemon=True).start()
                self.after(100, self._poll)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Erro", str(e)))
                self._finalizar_btn()

        _th.Thread(target=run, daemon=True).start()

    def _save_files(self):
        if not self.output_paths:
            messagebox.showerror("Erro", "Nenhuma planilha gerada ainda.")
            return
        src  = self.output_paths[0]
        dest = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=os.path.basename(src))
        if not dest:
            return
        import shutil
        shutil.copy2(src, dest)
        self.log(f"\n Salvo: {dest}", "ok")
        self.status(f"Salvo: {os.path.basename(dest)}", self._t("SUCCESS"))
        messagebox.showinfo("Salvo!", f"Planilha salva:\n{dest}")

    #  Logout / fechar 
    def _ao_fechar(self):
        if self._running:
            if not messagebox.askyesno("Sair",
                    "Processamento em andamento. Deseja cancelar e sair?"):
                return
            self._cancelar()
        self.destroy()

    def _atualizar_hora(self):
        import time as _th
        self._hora_label.configure(
            text=_th.strftime("%H:%M:%S"))
        self.after(1000, self._atualizar_hora)

    def _atualizar_ip_footer(self):
        def _busca():
            try:
                from auth import _get_ip_externo
                ip = _get_ip_externo()
                self.after(0, lambda: self._ip_label.configure(
                    text=f"IP: {ip}"))
            except Exception:
                pass
        import threading as _th
        _th.Thread(target=_busca, daemon=True).start()

    def _checar_conexao(self):
        def check():
            try:
                import requests as _req
                _req.get("https://www.google.com", timeout=4)
                online = True
            except Exception:
                online = False
            cor  = "#4a4a4a" if online else "#888888"
            txt  = " online" if online else " offline"
            self.after(0, lambda: self._online_label.configure(text=txt, fg=cor))
        threading.Thread(target=check, daemon=True).start()
        self.after(30000, self._checar_conexao)

    def _logout(self):
        try:
            from auth import fazer_logout
            fazer_logout(self.usuario_token)
        except Exception:
            pass
        self.destroy()
        from login import TelaLogin
        def ao_logar(r):
            App(usuario=r).mainloop()
        TelaLogin(on_success=ao_logar).mainloop()

    #  Painel master / historico 
    def _abrir_painel_master(self):
        if self.papel != "master":
            return
        from painel_master import PainelMaster
        PainelMaster(self, self.usuario_token)

    def _abrir_historico(self):
        if self.papel != "master":
            return
        from tkinter import ttk
        from auth import listar_historico

        win = tk.Toplevel(self)
        win.title("Historico")
        win.geometry("960x500")
        win.configure(bg=self._t("BG"))

        tk.Label(win, text="Historico de Processamentos",
                 font=("Courier New", 11, "bold"),
                 bg=self._t("BG"), fg=self._t("TEXT")).pack(anchor="w", padx=16, pady=(16, 8))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("H.Treeview",
                        background=self._t("CARD2"),
                        foreground=self._t("TEXT"),
                        fieldbackground=self._t("CARD2"),
                        font=("Courier New", 8), rowheight=22)
        style.configure("H.Treeview.Heading",
                        background=self._t("CARD"),
                        foreground=self._t("TEXT_DIM"),
                        font=("Courier New", 8, "bold"), relief="flat")
        style.map("H.Treeview",
                  background=[("selected", self._t("ACCENT"))])

        frame = tk.Frame(win, bg=self._t("BG"))
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        cols = ("Usuario", "Planilha", "XMLs", "Divergencias",
                "Horario", "Maquina", "IP")
        tree = ttk.Treeview(frame, columns=cols,
                             show="headings", style="H.Treeview")
        for col, w in zip(cols, [120, 200, 180, 80, 130, 120, 100]):
            tree.heading(col, text=col)
            tree.column(col, width=w)

        sb = tk.Scrollbar(frame, command=tree.yview,
                          bg=self._t("CARD"),
                          troughcolor=self._t("CARD2"),
                          relief="flat", width=8)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        def carregar():
            try:
                for r in listar_historico(100):
                    xmls    = ", ".join(r.get("xmls_processados") or [])
                    horario = (r.get("concluido_em") or "")[:16]
                    tree.insert("", "end", values=(
                        r.get("usuario_nome", ""),
                        r.get("planilha_gerada", ""),
                        xmls, r.get("divergencias", 0),
                        horario, r.get("nome_maquina", ""),
                        r.get("ip", "")))
            except Exception as e:
                self.log(f"Historico: {e}", "warn")

        threading.Thread(target=carregar, daemon=True).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
