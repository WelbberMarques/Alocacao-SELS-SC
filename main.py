"""
CPB Alocacao - Ponto de entrada
"""
import sys
import os

_root = os.path.dirname(os.path.abspath(__file__))
for _d in ("ui", "core", "utils"):
    _p = os.path.join(_root, _d)
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _tarefa_startup(progresso):
    progresso(0.3, "Carregando modulos...")
    try:
        import openpyxl, selenium, requests
    except Exception:
        pass

    progresso(0.9, "Pronto.")
    import time; time.sleep(0.3)
    return {"ok": True}


def iniciar():
    from splash import Splash

    def ao_concluir(resultado):
        if not resultado:
            return

        from login import TelaLogin

        def ao_logar(r):
            from app import App
            App(usuario=r).mainloop()

        TelaLogin(on_success=ao_logar).mainloop()

    Splash(tarefa_fn=_tarefa_startup, ao_concluir=ao_concluir).mainloop()


if __name__ == "__main__":
    iniciar()
