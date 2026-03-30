"""
Execute este script UMA VEZ para criar o usuario master.
Depois pode apagar.
"""
from auth import criar_usuario

print("=== Criacao do usuario Master ===")
nome  = input("Nome: ")
username = input("Username (ex: hudson.amorim): ")
senha = input("Senha (min 8 chars): ")

r = criar_usuario(nome, username, senha, papel="master")
if r["ok"]:
    print(f"\nOK! {r['mensagem']}")
    print("Agora pode apagar este arquivo.")
else:
    print(f"\nErro: {r['erro']}")
