"""
Tela de login - CPB Alocacao
CustomTkinter version
"""
import customtkinter as ctk
from pathlib import Path
import threading

# Tema global
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG       = "#0a0a0a"
CARD     = "#111111"
ACCENT   = "#555555"
ERROR_C  = "#cc4444"
TEXT     = "#c8c8c8"
TEXT_DIM = "#707070"


class TelaLogin(ctk.CTk):
    def __init__(self, on_success):
        super().__init__()
        self.on_success = on_success
        self._running   = False

        self.title("SELS-SC | CPB Alocacao")
        self.geometry("420x680")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self._center()

        # Icone
        try:
            import sys as _sys
            _base = Path(_sys.executable).parent if getattr(_sys, "frozen", False) \
                    else Path(__file__).resolve().parent.parent
            for ico in [_base/"assets"/"app_icon.ico", _base/"app_icon.ico"]:
                if ico.exists():
                    self.iconbitmap(str(ico))
                    break
        except Exception:
            pass

        self._build()
        self.after(100, self._fade_in)

    def _center(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"420x680+{(sw-420)//2}+{(sh-680)//2}")

    def _fade_in(self, alpha=0.0):
        alpha = min(alpha + 0.08, 1.0)
        self.attributes("-alpha", alpha)
        if alpha < 1.0:
            self.after(15, lambda: self._fade_in(alpha))

    def _build(self):
        # Logo SELS
        import sys as _sys
        _base = Path(_sys.executable).parent if getattr(_sys, "frozen", False) \
                else Path(__file__).resolve().parent.parent
        _paths = [_base/"assets", _base/"assents", _base]

        def _find(nome):
            for p in _paths:
                f = p / nome
                if f.exists():
                    return f
            return None

        ctk.CTkFrame(self, height=24, fg_color=BG).pack()

        # Logo circular
        try:
            from PIL import Image
            f = _find("logo_sels.png")
            if not f:
                raise FileNotFoundError
            img = Image.open(f).convert("RGBA")
            # Mostra proporcional — largura 200px
            w, h = img.size
            novo_w = 200
            novo_h = int(h * novo_w / w)
            img = img.resize((novo_w, novo_h), Image.LANCZOS)
            ctk_img = ctk.CTkImage(img, size=(novo_w, novo_h))
            ctk.CTkLabel(self, image=ctk_img, text="",
                         fg_color=BG).pack()
        except Exception:
            ctk.CTkFrame(self, width=160, height=50,
                         fg_color=ACCENT, corner_radius=8).pack()

        ctk.CTkLabel(self, text="Alocacao CPB",
                     font=ctk.CTkFont("Courier New", 12),
                     text_color=TEXT_DIM, fg_color=BG).pack(pady=(6,0))

        ctk.CTkFrame(self, height=20, fg_color=BG).pack()

        # Card login
        card = ctk.CTkFrame(self, fg_color=CARD,
                            corner_radius=12)
        card.pack(padx=36, fill="x")

        ctk.CTkFrame(card, height=20, fg_color=CARD).pack()

        # Username
        ctk.CTkLabel(card, text="USERNAME",
                     font=ctk.CTkFont("Courier New", 9, "bold"),
                     text_color=TEXT_DIM, fg_color=CARD,
                     anchor="w").pack(fill="x", padx=24)

        self._username = ctk.CTkEntry(
            card,
            font=ctk.CTkFont("Courier New", 12),
            fg_color="#1a1a1a", text_color=TEXT,
            border_color="#333333", border_width=1,
            corner_radius=8, height=42)
        self._username.pack(fill="x", padx=24, pady=(4,0))

        ctk.CTkFrame(card, height=14, fg_color=CARD).pack()

        # Senha
        ctk.CTkLabel(card, text="SENHA",
                     font=ctk.CTkFont("Courier New", 9, "bold"),
                     text_color=TEXT_DIM, fg_color=CARD,
                     anchor="w").pack(fill="x", padx=24)

        self._senha = ctk.CTkEntry(
            card,
            font=ctk.CTkFont("Courier New", 12),
            fg_color="#1a1a1a", text_color=TEXT,
            border_color="#333333", border_width=1,
            corner_radius=8, height=42, show="*")
        self._senha.pack(fill="x", padx=24, pady=(4,0))

        # Mostrar senha
        self._mostrar = ctk.CTkCheckBox(
            card, text="Mostrar senha",
            font=ctk.CTkFont("Courier New", 9),
            text_color=TEXT_DIM, fg_color=ACCENT,
            hover_color="#777777", border_color="#444444",
            command=self._toggle_senha)
        self._mostrar.pack(anchor="e", padx=24, pady=(8,0))

        ctk.CTkFrame(card, height=16, fg_color=CARD).pack()

        # Botao entrar
        self._btn = ctk.CTkButton(
            card, text="ENTRAR",
            font=ctk.CTkFont("Courier New", 13, "bold"),
            fg_color=ACCENT, hover_color="#777777",
            text_color="#ffffff", corner_radius=8,
            height=46, command=self._login)
        self._btn.pack(fill="x", padx=24)

        ctk.CTkFrame(card, height=20, fg_color=CARD).pack()

        # Status
        self._status = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont("Courier New", 9),
            text_color=TEXT_DIM, fg_color=BG,
            wraplength=340)
        self._status.pack(pady=(12,0))

        # Rodape
        ctk.CTkFrame(self, height=16, fg_color=BG).pack(expand=True)
        ctk.CTkFrame(self, height=1, fg_color="#222222").pack(fill="x", padx=40)
        ctk.CTkFrame(self, height=12, fg_color=BG).pack()

        # Logo adventista
        try:
            from PIL import Image
            f2 = _find("logo_adventista.png")
            if f2:
                img2 = Image.open(f2).resize((42,42)).convert("RGBA")
                ctk_img2 = ctk.CTkImage(img2, size=(42,42))
                ctk.CTkLabel(self, image=ctk_img2, text="",
                             fg_color=BG).pack()
        except Exception:
            pass

        ctk.CTkFrame(self, height=8, fg_color=BG).pack()
        ctk.CTkLabel(self, text="Developed by Welbber Marques",
                     font=ctk.CTkFont("Courier New", 11, "bold"),
                     text_color=TEXT_DIM, fg_color=BG).pack()
        ctk.CTkLabel(self, text="Special thanks to Diego Campos",
                     font=ctk.CTkFont("Courier New", 10),
                     text_color=TEXT_DIM, fg_color=BG).pack(pady=(3,14))

        # Bindings
        self._senha.bind("<Return>", lambda e: self._login())
        self._username.bind("<Return>", lambda e: self._senha.focus())
        self._username.focus()

    def _toggle_senha(self):
        self._senha.configure(
            show="" if self._mostrar.get() else "*")

    def _animar_btn(self, dots=0):
        if not self._running:
            return
        self._btn.configure(text="Verificando" + "." * (dots % 4))
        self.after(350, lambda: self._animar_btn(dots + 1))

    def _login(self):
        username = self._username.get().strip()
        senha    = self._senha.get().strip()
        if not username or not senha:
            self._status.configure(
                text="Preencha username e senha.",
                text_color=ERROR_C)
            return
        self._running = True
        self._btn.configure(state="disabled")
        self._status.configure(text="Conectando...", text_color=TEXT_DIM)
        self._animar_btn()
        threading.Thread(target=self._fazer_login,
                         args=(username, senha), daemon=True).start()

    def _fazer_login(self, username, senha):
        try:
            from auth import fazer_login
            resultado = fazer_login(username, senha)
        except Exception as e:
            self.after(0, lambda: self._erro(f"Erro de conexao: {e}"))
            return
        if resultado.ok:
            self.after(0, lambda: self._sucesso(resultado))
        else:
            self.after(0, lambda: self._erro(resultado.erro))

    def _sucesso(self, resultado):
        self._running = False
        self.destroy()
        self.on_success(resultado)

    def _erro(self, msg):
        self._running = False
        self._btn.configure(state="normal", text="ENTRAR")
        self._status.configure(text=msg, text_color=ERROR_C)
