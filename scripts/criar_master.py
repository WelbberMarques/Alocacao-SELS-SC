"""
Execute este script UMA VEZ para criar o usuario master.
"""
import sys
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "core"))

from auth import criar_usuario

print("=== Criacao do usuario Master ===")
nome     = input("Nome: ")
username = input("Username (ex: hudson.amorim): ")
senha    = input("Senha (min 8 chars): ")

r = criar_usuario(nome, username, senha, papel="master")
if r["ok"]:
    print(f"\nOK! {r['mensagem']}")
else:
    print(f"\nErro: {r['erro']}")
