"""
Splash screen - CPB Alocacao
Exibe logo e barra de carregamento ao iniciar
"""
import tkinter as tk
import threading
import time

BG     = "#0a0a0a"
CARD   = "#111111"
ACCENT = "#555555"
TEXT   = "#c8c8c8"
DIM    = "#444444"
BORDER = "#2c2c2c"


class Splash(tk.Tk):
    def __init__(self, tarefa_fn, ao_concluir):
        """
        tarefa_fn: funcao que roda em background (recebe callback de progresso)
        ao_concluir: chamada com o resultado quando tarefa terminar
        """
        super().__init__()
        self._tarefa_fn  = tarefa_fn
        self._ao_concluir = ao_concluir
        self._resultado   = None

        self.overrideredirect(True)   # sem barra de titulo
        self.configure(bg=BG)
        self.resizable(False, False)

        w, h = 420, 280
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        self._build()
        self.after(100, self._iniciar)

    def _build(self):


        # Borda superior
        tk.Frame(self, bg=ACCENT, height=3).pack(fill="x")

        # Logo circulo
        tk.Frame(self, bg=BG, height=20).pack()
        # Logo SELS
        from pathlib import Path
        _base = Path(__file__).parent
        _paths = [_base / "assets", _base / "assents", _base]

        def _find(nome):
            for p in _paths:
                f = p / nome
                if f.exists():
                    return f
            return None

        self._splash_imgs = []
        try:
            from PIL import Image, ImageTk
            f = _find("logo_sels.png")
            if f:
                img = Image.open(f).resize((160, 80), Image.LANCZOS)
                ph  = ImageTk.PhotoImage(img)
                self._splash_imgs.append(ph)
                tk.Label(self, image=ph, bg=BG).pack(pady=(0,4))
            else:
                raise FileNotFoundError
        except Exception:
            tk.Label(self, text="SELS-SC",
                     font=("Courier New", 24, "bold"),
                     bg=BG, fg=TEXT).pack(pady=(8,0))

        tk.Label(self, text="Alocacao CPB",
                 font=("Courier New", 10),
                 bg=BG, fg=DIM).pack(pady=(2, 0))

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=40, pady=14)

        self._status = tk.Label(self, text="Iniciando...",
                                font=("Courier New", 9),
                                bg=BG, fg=DIM)
        self._status.pack()

        track = tk.Frame(self, bg=BORDER, height=4)
        track.pack(fill="x", padx=40, pady=(8, 0))
        self._fill = tk.Frame(track, bg=ACCENT, height=4)
        self._fill.place(x=0, y=0, relwidth=0, height=4)

        tk.Frame(self, bg=BG, height=10).pack()
        tk.Label(self, text="SELS-SC © 2026",
                 font=("Courier New", 7),
                 bg=BG, fg=BORDER).pack()

    def progresso(self, pct: float, msg: str = ""):
        """Atualiza barra e mensagem — thread-safe."""
        def _update():
            self._fill.place(x=0, y=0, relwidth=min(pct, 1.0), height=3)
            if msg:
                self._status.configure(text=msg)
            self.update_idletasks()
        self.after(0, _update)

    def _iniciar(self):
        def worker():
            try:
                resultado = self._tarefa_fn(self.progresso)
                self._resultado = resultado
            except Exception as e:
                self._resultado = {"erro": str(e)}
            self.after(200, self._finalizar)

        threading.Thread(target=worker, daemon=True).start()

    def _finalizar(self):
        self.destroy()
        self._ao_concluir(self._resultado)
