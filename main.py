"""
CPB Alocacao - Ponto de entrada com splash screen e auto-update
"""
import sys


def _tarefa_startup(progresso):
    """Roda em background durante o splash: update + login prep."""
    progresso(0.1, "Verificando atualizacoes...")
    try:
        from updater import verificar_e_atualizar, reiniciar
        precisa = verificar_e_atualizar()
        if precisa:
            progresso(1.0, "Reiniciando...")
            reiniciar()
            return {"reiniciar": True}
    except Exception:
        pass

    progresso(0.5, "Carregando modulos...")
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
        if not resultado or resultado.get("reiniciar"):
            return

        from login import TelaLogin

        def ao_logar(r):
            from app import App
            App(usuario=r).mainloop()

        TelaLogin(on_success=ao_logar).mainloop()

    Splash(tarefa_fn=_tarefa_startup, ao_concluir=ao_concluir).mainloop()


if __name__ == "__main__":
    iniciar()
