import xml.etree.ElementTree as ET
import re

NS = "http://www.portalfiscal.inf.br/nfe"

# Mapeamento de código de produto para tipo de assinatura
PRODUTO_TIPO = {
    "6031": "vs",   # VIDA E SAUDE
    "6033": "na",   # N.A. (Nosso Amiguinho)
    "8366": "najr", # N.A. JUNIOR
}

# Nomes alternativos para identificar pelo xProd caso cProd mude
NOME_TIPO = [
    ("vs",   ["VIDA E SAUDE", "V.S", "VS"]),
    ("na",   ["NOSSO AMIGUINHO", "N. A.", "N.A.", " NA "]),
    ("najr", ["JUNIOR", "N.A. JUNIOR", "N.AJR", "NAJR"]),
]


def _identificar_tipo(cprod: str, xprod: str) -> str | None:
    cprod = cprod.strip()
    if cprod in PRODUTO_TIPO:
        return PRODUTO_TIPO[cprod]
    xprod_upper = xprod.upper()
    for tipo, keywords in NOME_TIPO:
        if any(k in xprod_upper for k in keywords):
            return tipo
    return None


def parse_nfe_xml(path: str) -> dict:
    tree = ET.parse(path)
    root = tree.getroot()

    def find(node, tag):
        return node.find(f"{{{NS}}}{tag}")

    def findall(node, tag):
        return node.findall(f"{{{NS}}}{tag}")

    # Raiz da NF-e
    nfe = root.find(f"{{{NS}}}NFe")
    if nfe is None:
        nfe = root
    infNFe = find(nfe, "infNFe")

    # Número da NF
    ide = find(infNFe, "ide")
    numero_nf = find(ide, "nNF").text.strip()

    # Quantidades por tipo
    qtd = {"vs": 0, "na": 0, "najr": 0}
    valor_unit = {"vs": 0.0, "na": 0.0, "najr": 0.0}

    for det in findall(infNFe, "det"):
        prod = find(det, "prod")
        cprod = find(prod, "cProd").text
        xprod = find(prod, "xProd").text
        qcom  = float(find(prod, "qCom").text)
        vunit = float(find(prod, "vUnCom").text)

        tipo = _identificar_tipo(cprod, xprod)
        if tipo:
            qtd[tipo] += qcom
            valor_unit[tipo] = vunit

    # Resumos — campo infCpl em infAdic
    infAdic = find(infNFe, "infAdic")
    resumos = []
    if infAdic is not None:
        infCpl = find(infAdic, "infCpl")
        if infCpl is not None and infCpl.text:
            # Extrai números após "RESUMOS NROS"
            match = re.search(r"RESUMOS?\s+NROS?\s+([\d,\s]+)", infCpl.text, re.IGNORECASE)
            if match:
                nums = re.findall(r"\d+", match.group(1))
                resumos = [int(n) for n in nums]

    return {
        "numero_nf": numero_nf,
        "resumos": resumos,
        "vs":   int(qtd["vs"]),
        "na":   int(qtd["na"]),
        "najr": int(qtd["najr"]),
        "valor_vs":   valor_unit["vs"],
        "valor_na":   valor_unit["na"],
        "valor_najr": valor_unit["najr"],
    }


if __name__ == "__main__":
    import sys
    dados = parse_nfe_xml(sys.argv[1])
    print(dados)
