import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import threading

BG      = "#0a0a0a"
CARD    = "#111111"
CARD2   = "#181818"
BORDER  = "#2c2c2c"
ACCENT  = "#555555"
SUCCESS = "#4a4a4a"
ERROR_C = "#666666"
TEXT    = "#c8c8c8"
TEXT_DIM= "#707070"
TEXT_MU = "#3a3a3a"
WHITE   = "#c8c8c8"
WARNING = "#5a5a5a"


def _estilo():
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("P.Treeview", background=CARD2, foreground=TEXT,
                fieldbackground=CARD2, font=("Courier New", 9), rowheight=24)
    s.configure("P.Treeview.Heading", background=CARD, foreground=TEXT_DIM,
                font=("Courier New", 9, "bold"), relief="flat")
    s.map("P.Treeview", background=[("selected", ACCENT)])


def _tabela(parent, colunas, larguras=None):
    _estilo()
    frame = tk.Frame(parent, bg=BORDER)
    tree  = ttk.Treeview(frame, columns=colunas, show="headings", style="P.Treeview")
    for i, col in enumerate(colunas):
        w = larguras[i] if larguras else 140
        tree.heading(col, text=col)
        tree.column(col, width=w, minwidth=60)
    sb = tk.Scrollbar(frame, command=tree.yview,
                      bg=CARD, troughcolor=CARD2, relief="flat", width=8)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    tree.pack(fill="both", expand=True)
    return frame, tree


class PainelMaster(tk.Toplevel):
    def __init__(self, parent, token):
        super().__init__(parent)
        self.token = token
        self.title("Painel Master - SELS-SC")
        self.geometry("960x640")
        self.configure(bg=BG)
        self.resizable(True, True)
        self._trees = {}
        self._build()
        self._recarregar()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        # Titulo
        tbar = tk.Frame(self, bg=CARD, height=44)
        tbar.pack(fill="x")
        tbar.pack_propagate(False)
        tk.Label(tbar, text="  Painel Master",
                 font=("Courier New", 11, "bold"),
                 bg=CARD, fg=TEXT).pack(side="left", fill="y")

        tk.Button(tbar, text="  Atualizar",
                  font=("Courier New", 9), bg=CARD, fg=TEXT_DIM,
                  relief="flat", cursor="hand2",
                  command=self._recarregar).pack(side="right", padx=8, fill="y")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Abas
        abas = tk.Frame(self, bg=CARD2, height=36)
        abas.pack(fill="x")
        abas.pack_propagate(False)
        self._aba_btns = {}
        for label, key in [("Usuarios", "usuarios"),
                            ("Dispositivos", "dispositivos"),
                            ("Historico", "historico"),
                            ("Estatisticas", "stats"),
                            ("Sessoes Ativas", "sessoes")]:
            b = tk.Button(abas, text=f"  {label}  ",
                          font=("Courier New", 9),
                          bg=CARD2, fg=TEXT_DIM,
                          relief="flat", cursor="hand2",
                          command=lambda k=key: self._aba(k))
            b.pack(side="left", fill="y")
            self._aba_btns[key] = b

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        self._conteudo = tk.Frame(self, bg=BG)
        self._conteudo.pack(fill="both", expand=True, padx=16, pady=14)

        self._aba("usuarios")

    def _aba(self, key):
        # Destaca aba ativa
        for k, b in self._aba_btns.items():
            b.configure(bg=ACCENT if k == key else CARD2,
                        fg=WHITE  if k == key else TEXT_DIM)
        for w in self._conteudo.winfo_children():
            w.destroy()
        {"usuarios":    self._aba_usuarios,
         "dispositivos": self._build_dispositivos,
         "stats":        self._build_stats,
         "historico":    self._aba_historico,
         "sessoes":      self._aba_sessoes}.get(key, lambda: None)()

    # ── ABA USUARIOS ──────────────────────────────────────────────────────────
    def _aba_usuarios(self):
        f = self._conteudo

        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", pady=(0, 10))
        tk.Label(top, text="Usuarios cadastrados",
                 font=("Courier New", 10, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")

        for txt, cmd in [("+ Novo usuario", self._novo_usuario)]:
            tk.Button(top, text=txt,
                      font=("Courier New", 9), bg=ACCENT, fg=WHITE,
                      relief="flat", padx=10, pady=4, cursor="hand2",
                      command=cmd).pack(side="right", padx=(4, 0))

        cols = ("Nome", "Username", "Papel", "Ativo", "Ultimo login")
        lrgs = [160, 160, 80, 60, 140]
        frame, tree = _tabela(f, cols, lrgs)
        frame.pack(fill="both", expand=True)
        self._trees["usuarios"] = tree

        acoes = tk.Frame(f, bg=BG)
        acoes.pack(fill="x", pady=(8, 0))
        for txt, cmd in [
            ("Ativar / Desativar", self._toggle_ativo),
            ("Alterar senha",      self._alterar_senha),
            ("Excluir usuario",    self._excluir_usuario),
        ]:
            tk.Button(acoes, text=txt,
                      font=("Courier New", 9), bg=CARD2, fg=TEXT_DIM,
                      relief="flat", padx=10, pady=4, cursor="hand2",
                      command=cmd).pack(side="left", padx=(0, 6))

    def _novo_usuario(self):
        win = tk.Toplevel(self)
        win.title("Novo usuario")
        win.geometry("380x400")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.grab_set()

        tk.Label(win, text="Criar novo usuario",
                 font=("Courier New", 11, "bold"),
                 bg=BG, fg=TEXT).pack(anchor="w", padx=24, pady=(20, 12))

        campos = {}
        defs = [
            ("Nome completo",              "nome",     ""),
            ("Username  (ex: joao.silva)", "username", ""),
            ("Senha (min 8 caracteres)",   "senha",    "*"),
        ]
        for label, key, show in defs:
            tk.Label(win, text=label, font=("Courier New", 8),
                     bg=BG, fg=TEXT_DIM).pack(anchor="w", padx=24, pady=(6, 0))
            e = tk.Entry(win, font=("Courier New", 10),
                         bg=CARD2, fg=TEXT, insertbackground=TEXT,
                         relief="flat", show=show)
            e.pack(fill="x", padx=24, ipady=7)
            tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=24)
            campos[key] = e

        # Papel
        tk.Label(win, text="Nivel de acesso",
                 font=("Courier New", 8),
                 bg=BG, fg=TEXT_DIM).pack(anchor="w", padx=24, pady=(8, 0))
        papel_var = tk.StringVar(value="membro")
        pf = tk.Frame(win, bg=BG)
        pf.pack(anchor="w", padx=24)
        for val, lbl in [("membro", "Membro"), ("master", "Master")]:
            tk.Radiobutton(pf, text=lbl, variable=papel_var, value=val,
                           font=("Courier New", 9), bg=BG, fg=TEXT_DIM,
                           selectcolor=CARD2, activebackground=BG,
                           relief="flat").pack(side="left", padx=(0, 16))

        status = tk.Label(win, text="", font=("Courier New", 8),
                          bg=BG, fg=ERROR_C, wraplength=330)
        status.pack(pady=(6, 0))

        def criar():
            from auth import criar_usuario
            r = criar_usuario(campos["nome"].get(),
                              campos["username"].get(),
                              campos["senha"].get(),
                              papel_var.get())
            if r["ok"]:
                win.destroy()
                messagebox.showinfo("Usuario criado", r["mensagem"])
                self._recarregar()
            else:
                status.configure(text=r["erro"])

        tk.Button(win, text="Criar usuario",
                  font=("Courier New", 10, "bold"),
                  bg=ACCENT, fg=WHITE, relief="flat", pady=11,
                  cursor="hand2", command=criar).pack(fill="x", padx=24, pady=14)

    def _toggle_ativo(self):
        u = self._usuario_selecionado()
        if not u:
            return
        from auth import ativar_desativar
        novo = not (u.get("ativo", True))
        ativar_desativar(u["id"], novo)
        acao = "ativado" if novo else "desativado"
        messagebox.showinfo("OK", f"Usuario {acao}.")
        self._recarregar()

    def _alterar_senha(self):
        u = self._usuario_selecionado()
        if not u:
            return
        nova = simpledialog.askstring(
            "Alterar senha",
            f"Nova senha para {u['nome']} (min 8 caracteres):",
            show="*", parent=self)
        if nova:
            if len(nova) < 8:
                messagebox.showerror("Erro", "Senha muito curta.")
                return
            from auth import alterar_senha
            alterar_senha(u["id"], nova)
            messagebox.showinfo("OK", "Senha alterada com sucesso.")

    def _excluir_usuario(self):
        u = self._usuario_selecionado()
        if not u:
            return
        if not messagebox.askyesno("Confirmar",
                                   f"Excluir o usuario {u['nome']}?\n"
                                   "Esta acao nao pode ser desfeita."):
            return
        from auth import _delete
        _delete("usuarios", f"id=eq.{u['id']}")
        messagebox.showinfo("OK", "Usuario excluido.")
        self._recarregar()

    def _usuario_selecionado(self):
        tree = self._trees.get("usuarios")
        if not tree:
            return None
        sel = tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um usuario na lista.")
            return None
        vals = tree.item(sel[0])["values"]
        # vals: (Nome, Username, Papel, Ativo, Ultimo login)
        from auth import listar_usuarios
        users = listar_usuarios()
        return next((x for x in users if x.get("username") == vals[1]), None)

    # ── ABA DISPOSITIVOS ──────────────────────────────────────────────────────
    def _build_dispositivos(self):
        f = self._conteudo

        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", pady=(0, 10))
        tk.Label(top, text="Dispositivos aguardando aprovacao",
                 font=("Courier New", 10, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")

        cols = ("Usuario", "IP Externo", "IP Real (maquina)",
                "Nome Maquina", "Cidade", "Status", "IP Fixo", "Data")
        lrgs = [120, 115, 125, 130, 130, 75, 65, 120]
        frame, tree = _tabela(f, cols, lrgs)
        frame.pack(fill="both", expand=True)
        self._trees["dispositivos"] = tree

        acoes = tk.Frame(f, bg=BG)
        acoes.pack(fill="x", pady=(8, 0))
        tk.Button(acoes, text="Aprovar",
                  font=("Courier New", 9), bg=SUCCESS, fg=WHITE,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._aprovar_dispositivo).pack(side="left", padx=(0, 6))
        tk.Button(acoes, text="Bloquear",
                  font=("Courier New", 9), bg=ERROR_C, fg=WHITE,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._bloquear_dispositivo).pack(side="left")

        tk.Button(acoes, text="Redefinir IP fixo",
                  font=("Courier New", 9), bg=WARNING, fg=WHITE,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._redefinir_ip_fixo).pack(side="left", padx=(6, 0))

        tk.Label(acoes,
                 text="IP Fixo = primeiro IP registrado. Qualquer outro IP e barrado automaticamente.",
                 font=("Courier New", 7), bg=BG, fg=TEXT_MU).pack(side="right")

    def _redefinir_ip_fixo(self):
        """Remove todos os registros do usuario e permite novo primeiro IP."""
        d = self._dispositivo_selecionado()
        if not d:
            return
        u = d.get("usuarios") or {}
        nome = u.get("nome", d.get("usuario_id","")) if isinstance(u,dict) else ""
        if not messagebox.askyesno("Confirmar",
                f"Redefinir IP fixo de {nome}?\n"
                "Todos os registros serao apagados e o proximo login "
                "sera registrado como novo IP fixo."):
            return
        from auth import _delete
        uid = d.get("usuario_id","")
        _delete("dispositivos_aprovados", f"usuario_id=eq.{uid}")
        messagebox.showinfo("OK",
            f"IP fixo de {nome} redefinido.\n"
            "Proximo login registrara o novo IP automaticamente.")
        self._recarregar()

    def _aprovar_dispositivo(self):
        d = self._dispositivo_selecionado()
        if not d:
            return
        # Avisa se ja tem um IP fixo aprovado para este usuario
        from auth import aprovar_dispositivo, _get
        existentes = _get("dispositivos_aprovados",
                          f"usuario_id=eq.{d['usuario_id']}&status=eq.aprovado&select=ip,ip_fixo")
        if existentes:
            if not messagebox.askyesno("Atencao",
                "Este usuario ja tem um IP fixo aprovado.\n"
                "Aprovar este novo IP vai permitir acesso de dois IPs diferentes.\n\n"
                "Deseja continuar?"):
                return
        aprovar_dispositivo(d["id"])
        ip_txt = f"IP: {d.get('ip','')}  |  IP Real: {d.get('ip_real','')}"
        messagebox.showinfo("OK", f"Dispositivo aprovado.\n{ip_txt}")
        self._recarregar()

    def _bloquear_dispositivo(self):
        d = self._dispositivo_selecionado()
        if not d:
            return
        from auth import bloquear_dispositivo
        bloquear_dispositivo(d["id"])
        messagebox.showinfo("OK", "Dispositivo bloqueado.")
        self._recarregar()

    def _dispositivo_selecionado(self):
        tree = self._trees.get("dispositivos")
        if not tree:
            return None
        sel = tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um dispositivo.")
            return None
        vals = tree.item(sel[0])["values"]
        # Busca pelo IP real
        from auth import _get
        devs = _get("dispositivos_aprovados",
                    "select=*,usuarios(nome,username)&order=criado_em.desc")
        if isinstance(devs, list):
            for d in devs:
                if str(d.get("ip","")) == str(vals[1]):
                    return d
        return None

    # ── ABA HISTORICO ─────────────────────────────────────────────────────────
    def _aba_historico(self):
        f = self._conteudo

        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", pady=(0, 10))
        tk.Label(top, text="Historico de processamentos",
                 font=("Courier New", 10, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Button(top, text="Limpar historico",
                  font=("Courier New", 9), bg=CARD2, fg=TEXT_DIM,
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  command=self._exportar_hist_xlsx).pack(side="right")

        cols = ("Usuario", "Planilha", "XMLs", "Div.", "Horario", "Maquina", "IP")
        lrgs = [130, 200, 200, 50, 140, 130, 110]
        frame, tree = _tabela(f, cols, lrgs)
        frame.pack(fill="both", expand=True)
        self._trees["historico"] = tree

    def _exportar_hist_xlsx(self):
        from tkinter import filedialog
        dest = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            title="Exportar historico")
        if not dest:
            return
        try:
            from openpyxl import Workbook
            from auth import _get
            hist = _get("historico",
                        "select=*&order=concluido_em.desc&limit=10000")
            wb = Workbook()
            ws = wb.active
            ws.title = "Historico"
            ws.append(["Usuario", "Planilha", "XMLs",
                        "Divergencias", "Horario", "Maquina", "IP"])
            for r in (hist or []):
                xmls = ", ".join(r.get("xmls_processados") or [])
                ws.append([
                    r.get("usuario_nome",""),
                    r.get("planilha_gerada",""),
                    xmls,
                    r.get("divergencias", 0),
                    (r.get("concluido_em") or "")[:16],
                    r.get("nome_maquina",""),
                    r.get("ip","")
                ])
            wb.save(dest)
            messagebox.showinfo("OK", f"Exportado:\n{dest}")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _limpar_historico(self):
        if messagebox.askyesno("Confirmar", "Limpar todo o historico?"):
            from auth import _delete
            _delete("historico", "id=neq.00000000-0000-0000-0000-000000000000")
            self._recarregar()

    # ── ABA SESSOES ───────────────────────────────────────────────────────────
    def _aba_sessoes(self):
        f = self._conteudo

        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", pady=(0, 10))
        tk.Label(top, text="Sessoes ativas",
                 font=("Courier New", 10, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Button(top, text="Revogar selecionada",
                  font=("Courier New", 9), bg=ERROR_C, fg=WHITE,
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  command=self._revogar_sessao).pack(side="right")

        cols = ("Usuario", "IP Externo", "IP Real (maquina)", "Cidade", "Maquina", "Criado em", "Expira em")
        lrgs = [130, 115, 125, 120, 130, 130, 130]
        frame, tree = _tabela(f, cols, lrgs)
        frame.pack(fill="both", expand=True)
        self._trees["sessoes"] = tree

    def _revogar_sessao(self):
        tree = self._trees.get("sessoes")
        if not tree:
            return
        sel = tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione uma sessao.")
            return
        vals = tree.item(sel[0])["values"]
        # vals: (Usuario, IP, Cidade, Maquina, Criado em, Expira em)
        ip      = vals[1]
        maquina = vals[3]
        from auth import _delete
        _delete("sessoes", f"ip=eq.{ip}&nome_maquina=eq.{maquina}")
        messagebox.showinfo("OK", "Sessao revogada.")
        self._recarregar()

    # ── Carregar dados ────────────────────────────────────────────────────────
    def _recarregar(self):
        threading.Thread(target=self._fetch, daemon=True).start()

    def _aba_stats(self):
        self._build_stats()

    def _build_stats(self):
        f = self._conteudo
        tk.Label(f, text="Estatisticas de Uso",
                 font=("Courier New", 10, "bold"),
                 bg=BG, fg=TEXT).pack(anchor="w", pady=(0, 12))
        cards = tk.Frame(f, bg=BG)
        cards.pack(fill="x", pady=(0, 16))
        self._stat_labels = {}
        cores_cards = {
            "total":    "#1a3a1a",
            "usuarios": "#1a2a3a",
            "hoje":     "#3a2a1a",
            "bloqueios":"#3a1a1a",
        }
        for titulo, key in [
            ("Processamentos", "total"),
            ("Usuarios ativos", "usuarios"),
            ("Sessoes hoje",    "hoje"),
            ("Bloqueios",       "bloqueios"),
        ]:
            cor  = cores_cards.get(key, CARD2)
            card = tk.Frame(cards, bg=cor, padx=16, pady=14)
            card.pack(side="left", expand=True, fill="x", padx=(0, 6))
            tk.Label(card, text=titulo.upper(),
                     font=("Courier New", 7, "bold"),
                     bg=cor, fg="#aaaaaa").pack(anchor="w")
            lbl = tk.Label(card, text="...",
                           font=("Courier New", 26, "bold"),
                           bg=cor, fg="#ffffff")
            lbl.pack(anchor="w", pady=(6, 0))
            self._stat_labels[key] = lbl
        tk.Label(f, text="Processamentos por dia (ultimos 14 dias)",
                 font=("Courier New", 9), bg=BG, fg=TEXT_DIM).pack(
                     anchor="w", pady=(0, 4))
        self._canvas = tk.Canvas(f, bg=CARD2, height=160, highlightthickness=0)
        self._canvas.pack(fill="x")
        btn_f = tk.Frame(f, bg=BG)
        btn_f.pack(fill="x", pady=(12, 0))
        tk.Button(btn_f, text="Exportar historico (.xlsx)",
                  font=("Courier New", 9), bg=ACCENT, fg=WHITE,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._exportar_hist_xlsx).pack(side="left")

    def _fetch(self):
        from auth import listar_usuarios, listar_historico, _get, _get_count
        from datetime import datetime, timedelta, timezone
        try:
            users   = listar_usuarios()
            hist    = _get("historico",
                          "select=*&order=concluido_em.desc&limit=1000")
            sessoes = _get("sessoes",
                           "select=*,usuarios(nome)&order=criado_em.desc&limit=50")
            devs    = _get("dispositivos_aprovados",
                           "select=*,usuarios(nome,username)&order=criado_em.desc&limit=100")

            # Stats
            hoje    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            bloq    = _get_count("tentativas_login",
                                 f"sucesso=eq.false&criado_em=gte.{hoje}T00:00:00Z")
            sess_hj = _get_count("sessoes",
                                 f"criado_em=gte.{hoje}T00:00:00Z")

            # Agrupa historico por dia
            por_dia = {}
            for r in hist:
                d = (r.get("concluido_em") or "")[:10]
                if d:
                    por_dia[d] = por_dia.get(d, 0) + 1

            stats = {
                "total":    len(hist),
                "usuarios": len([u for u in users if u.get("ativo")]),
                "hoje":     sess_hj,
                "bloqueios": bloq,
                "por_dia":  por_dia,
            }
            self.after(0, lambda: self._popular(users, hist, sessoes, devs, stats))
        except Exception as e:
            print(f"Painel fetch erro: {e}")

    def _popular(self, users, hist, sessoes, devs=None, stats=None):
        # Usuarios
        tree = self._trees.get("usuarios")
        if tree:
            tree.get_children() and tree.delete(*tree.get_children())
            for u in users:
                ult = (u.get("ultimo_login") or "")[:16] or "Nunca"
                tree.insert("", "end", values=(
                    u.get("nome", ""),
                    u.get("username", ""),
                    u.get("papel", "").upper(),
                    "Sim" if u.get("ativo") else "Nao",
                    ult
                ))

        # Historico
        tree = self._trees.get("historico")
        if tree:
            tree.get_children() and tree.delete(*tree.get_children())
            for r in hist:
                xmls    = ", ".join(r.get("xmls_processados") or [])
                horario = (r.get("concluido_em") or "")[:16]
                tree.insert("", "end", values=(
                    r.get("usuario_nome", ""),
                    r.get("planilha_gerada", ""),
                    xmls,
                    r.get("divergencias", 0),
                    horario,
                    r.get("nome_maquina", ""),
                    r.get("ip", "")
                ))

        # Dispositivos
        tree = self._trees.get("dispositivos")
        if tree and devs and isinstance(devs, list):
            tree.get_children() and tree.delete(*tree.get_children())
            for d in devs:
                u = d.get("usuarios") or {}
                nome = u.get("nome","") if isinstance(u,dict) else ""
                criado = (d.get("criado_em") or "")[:16]
                primeiro = "SIM" if d.get("primeiro_ip") else "nao"
                status   = d.get("status","").upper()
                tree.insert("", "end", values=(
                    nome,
                    d.get("ip",""),
                    d.get("ip_real",""),
                    d.get("maquina",""),
                    d.get("cidade",""),
                    status,
                    primeiro,
                    criado
                ))

        # Stats
        if stats and hasattr(self, '_stat_labels'):
            for key, lbl in self._stat_labels.items():
                lbl.configure(text=str(stats.get(key, 0)))
            if hasattr(self, '_canvas') and stats.get("por_dia"):
                self.after(100, lambda: self._desenhar_grafico(stats["por_dia"]))

        # Sessoes
        tree = self._trees.get("sessoes")
        if tree and isinstance(sessoes, list):
            tree.get_children() and tree.delete(*tree.get_children())
            for s in sessoes:
                nome = (s.get("usuarios") or {}).get("nome", "")
                tree.insert("", "end", values=(
                    nome,
                    s.get("ip", ""),
                    s.get("ip_real", ""),
                    s.get("cidade", ""),
                    s.get("nome_maquina", ""),
                    (s.get("criado_em") or "")[:16],
                    (s.get("expira_em") or "")[:16]
                ))
