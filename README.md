# CPB Alocacao — SELS-SC

![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![version](https://img.shields.io/badge/version-2.0-orange)
![author](https://img.shields.io/badge/author-Welbber%20Marques-lightgrey)

> **Uso exclusivo da SELS-SC.** Este repositório é disponibilizado apenas para fins de demonstração. A execução é restrita aos membros autorizados da Secretaria de Evangelismo e Literatura do Sul do Brasil — Seção Santa Catarina.

---

## Sobre

Ferramenta desktop para preenchimento automático de planilhas de alocação CPB a partir de XMLs de Notas Fiscais (NF-e). Suporta processamento paralelo de múltiplos XMLs com automação via Chrome (Selenium).

## Funcionalidades

- Importação de múltiplos XMLs de NF-e simultaneamente
- Preenchimento automático da planilha modelo CPB
- Processamento paralelo com painel de logs por XML
- Sistema de login com autenticação local (PBKDF2)
- Controle de acesso por papel: `master` e `membro`
- Restrição geográfica: Florianópolis e São José — SC
- Detecção de VPN, proxy e Tor no acesso
- Painel master: gerenciamento de usuários e dispositivos
- Histórico de processamentos
- Temas claro e escuro

## Estrutura

```
├── main.py                  # Ponto de entrada
├── build_exe.spec           # Configuração do executável (PyInstaller)
├── requirements.txt         # Dependências
├── assets/                  # Logos e ícones
│   ├── app_icon.ico
│   ├── logo_adventista.png
│   └── logo_sels.png
├── ui/                      # Interface e telas
│   ├── app.py               # Janela principal
│   ├── login.py             # Tela de login
│   ├── splash.py            # Tela de carregamento
│   ├── painel_master.py     # Painel administrativo
│   └── preferencias.py     # Preferências do usuário
├── core/                    # Lógica de negócio
│   ├── auth.py              # Autenticação (JSON local)
│   ├── xml_parser.py        # Leitura de XMLs NF-e
│   ├── excel_writer.py      # Preenchimento da planilha
│   └── site_scraper.py      # Automação Chrome (Selenium)
├── utils/                   # Utilitários
│   └── notificacao.py       # Notificações por email
└── scripts/                 # Scripts internos
    └── criar_master.py      # Criação do usuário master
```

## Licença

MIT © 2026 [Welbber Marques](https://github.com/WelbberMarques)
