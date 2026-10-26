import os
import re
import json
import asyncio
import unicodedata
from datetime import datetime
from playwright.async_api import async_playwright

MODO_EXECUCAO = os.getenv("MODO_EXECUCAO", "mensal")
BLOCO_ID = os.getenv("BLOCO", "todos")  # Pode ser '1', '2', '3', '4' ou 'todos'
GERAR_PRINTS = os.getenv("GERAR_PRINTS", "false").lower() == "true"

ANO_ATUAL = datetime.now().year
PASTA_DADOS = "dados"
PASTA_MUNICIPIOS = os.path.join(PASTA_DADOS, "por_ente")
PASTA_PRINTS = "prints_edicao_impressa"
ARQUIVO_JSON_CONSOLIDADO = os.path.join(PASTA_DADOS, "tce_es_consolidado.json")

os.makedirs(PASTA_MUNICIPIOS, exist_ok=True)
if GERAR_PRINTS:
    os.makedirs(PASTA_PRINTS, exist_ok=True)

MUNICIPIOS_ES = [
    "Afonso Cláudio", "Água Doce do Norte", "Águia Branca", "Alegre", "Alfredo Chaves",
    "Alto Rio Novo", "Anchieta", "Apiacá", "Aracruz", "Atílio Vivácqua",
    "Baixo Guandu", "Barra de São Francisco", "Boa Esperança", "Bom Jesus do Norte", "Brejetuba",
    "Cachoeiro de Itapemirim", "Cariacica", "Castelo", "Colatina", "Conceição da Barra",
    "Conceição do Castelo", "Divino de São Lourenço", "Domingos Martins", "Dores do Rio Preto", "Ecoporanga",
    "Fundão", "Governador Lindenberg", "Guaçuí", "Guarapari", "Ibatiba",
    "Ibiraçu", "Ibitirama", "Iconha", "Irupi", "Itaguaçu",
    "Itapemirim", "Itarana", "Iúna", "Jaguaré", "Jerônimo Monteiro",
    "João Neiva", "Laranja da Terra", "Linhares", "Mantenópolis", "Marataízes",
    "Marechal Floriano", "Marilândia", "Mimoso do Sul", "Montanha", "Mucurici",
    "Muniz Freire", "Muqui", "Nova Venécia", "Pancas", "Pedro Canário",
    "Pinheiros", "Piúma", "Ponto Belo", "Presidente Kennedy", "Rio Bananal",
    "Rio Novo do Sul", "Santa Leopoldina", "Santa Maria de Jetibá", "Santa Teresa", "São Domingos do Norte",
    "São Gabriel da Palha", "São José do Calçado", "São Mateus", "São Roque do Canaã", "Serra",
    "Sooretama", "Vargem Alta", "Venda Nova do Imigrante", "Viana", "Vila Pavão",
    "Vila Valério", "Vila Velha", "Vitória"
]

PAGINAS_ALVO = {
    "visaoGeral": "visaoGeral",
    "receitas": "gestaoOrcamentaria/receitas",
    "despesas": "gestaoOrcamentaria/despesas",
    "dividaConsolidada": "gestaoFiscal/endividamento",
    "fundeb": "gestaoFiscal/educacaoFundeb",
    "receitaCorrenteLiquida": "gestaoFiscal/receitaCorrenteLiquida"
}

REGEX_NUMEROS_BR = re.compile(r"(?:R\$\s*)?-?\d{1,3}(?:\.\d{3})*(?:,\d+)?%?")

def gerar_slug(nome):
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", nome) if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", sem_acento).strip().lower()
    return re.sub(r"[\s]+", "-", slug)

def converter_numero_br(texto):
    if isinstance(texto, (int, float)):
        return texto
    if not isinstance(texto, str):
        return None
    limpo = re.sub(r"[R$\s%]", "", texto).replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None

def extrair_metricas_de_texto(texto):
    encontrados = REGEX_NUMEROS_BR.findall(texto or "")
    metricas = []
    for val_str in encontrados:
        val_str_limpo = val_str.strip()
        if not val_str_limpo:
            continue
        num_float = converter_numero_br(val_str_limpo)
        if num_float is not None:
            metricas.append({
                "valor": num_float,
                "formatado": val_str_limpo,
                "unidade": "%" if "%" in val_str_limpo else ("R$" if "R$" in val_str_limpo else "numero")
            })
    return metricas

async def coletar_pagina_json(context, tipo_ente, slug_ente, ano, chave_pagina, rota):
    tirar_print = GERAR_PRINTS and (ano == ANO_ATUAL)

    if tipo_ente == "Estado":
        url = f"https://paineldecontrole.tcees.tc.br/estado/{ano}/{rota}"
        pasta_ente_print = os.path.join(PASTA_PRINTS, "estado-es")
    else:
        url = f"https://paineldecontrole.tcees.tc.br/municipio/{ano}/{slug_ente}/{rota}"
        pasta_ente_print = os.path.join(PASTA_PRINTS, slug_ente)

    resultado_pagina = {
        "url_fonte": url,
        "quadros": []
    }

    if tirar_print:
        os.makedirs(pasta_ente_print, exist_ok=True)
        caminho_print = os.path.join(pasta_ente_print, f"{chave_pagina}_{ano}.jpg")
        resultado_pagina["print_auditoria"] = caminho_print

    page = await context.new_page()

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        try:
            await page.wait_for_function(
                r"""() => {
                    const txt = document.body ? document.body.innerText : '';
                    const carregando = txt.includes('Obtendo os dados') || txt.includes('Carregando');
                    const temNumeros = /(\d+[,.]\d+)|R\$|%/.test(txt);
                    return !carregando && temNumeros && txt.length > 200;
                }""",
                timeout=25000
            )
        except Exception:
            await asyncio.sleep(6.0)

        await page.evaluate(r"""async () => {
            await new Promise((resolve) => {
                let totalHeight = 0, distance = 600;
                let timer = setInterval(() => {
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if(totalHeight >= document.body.scrollHeight || totalHeight > 10000){
                        clearInterval(timer);
                        window.scrollTo(0, 0);
                        resolve();
                    }
                }, 150);
            });
        }""")
        await asyncio.sleep(2.0)

        if tirar_print:
            await page.screenshot(path=caminho_print, full_page=True, type="jpeg", quality=85)

        quadros_dom = await page.evaluate(r"""() => {
            const blocos = [];
            const vistos = new Set();
            const seletores = 'mat-card, .card, .painel, .box, section, table, article, [class*="card"], [class*="quadro"], [class*="indicador"]';
            
            document.querySelectorAll(seletores).forEach(el => {
                const texto = (el.innerText || '').trim();
                if (texto.length > 5 && texto.length < 1500 && !vistos.has(texto)) {
                    vistos.add(texto);
                    const linhas = texto.split('\n').map(l => l.trim()).filter(l => l.length > 0);
                    if (linhas.length > 0) {
                        blocos.push({
                            titulo: linhas.slice(0, 2).join(' | '),
                            linhas: linhas
                        });
                    }
                }
            });
            return blocos;
        }""")

        for q in quadros_dom:
            texto_bloco = " ".join(q["linhas"])
            metricas = extrair_metricas_de_texto(texto_bloco)
            if metricas:
                resultado_pagina["quadros"].append({
                    "titulo": q["titulo"],
                    "metricas": metricas
                })

        print(f"   [OK] [{ano}] {slug_ente} | {chave_pagina}: {len(resultado_pagina['quadros'])} quadros limpos.")

    except Exception as e:
        print(f"   [ERRO] {slug_ente} ({ano}) - {chave_pagina}: {e}")
    finally:
        await page.close()

    return resultado_pagina

async def main():
    if os.path.exists(ARQUIVO_JSON_CONSOLIDADO):
        with open(ARQUIVO_JSON_CONSOLIDADO, "r", encoding="utf-8") as f:
            base_consolidada = json.load(f)
    else:
        base_consolidada = {"ultima_atualizacao": "", "entes": {}}

    if MODO_EXECUCAO == "teste_rapido":
        print("MODO TESTE RAPIDO: Coletando Estado do ES e Afonso Claudio (2025 e 2026)...")
        anos_alvo = [2025, ANO_ATUAL]
        entes_alvo = [
            {"tipo": "Estado", "nome": "Espírito Santo", "slug": "estado-es"},
            {"tipo": "Município", "nome": "Afonso Cláudio", "slug": "afonso-claudio"}
        ]
    elif MODO_EXECUCAO == "historico_completo":
        anos_alvo = list(range(2019, ANO_ATUAL + 1))
        
        # Divide os 78 municípios em 4 blocos de ~20 cidades + o Estado no Bloco 1
        total_mun = len(MUNICIPIOS_ES)
        tamanho_bloco = total_mun // 4
        
        mun_selecionados = MUNICIPIOS_ES
        if BLOCO_ID == "1":
            mun_selecionados = MUNICIPIOS_ES[:tamanho_bloco]
        elif BLOCO_ID == "2":
            mun_selecionados = MUNICIPIOS_ES[tamanho_bloco:tamanho_bloco*2]
        elif BLOCO_ID == "3":
            mun_selecionados = MUNICIPIOS_ES[tamanho_bloco*2:tamanho_bloco*3]
        elif BLOCO_ID == "4":
            mun_selecionados = MUNICIPIOS_ES[tamanho_bloco*3:]

        entes_alvo = []
        if BLOCO_ID in ["1", "todos"]:
            entes_alvo.append({"tipo": "Estado", "nome": "Espírito Santo", "slug": "estado-es"})
            
        for m in mun_selecionados:
            entes_alvo.append({"tipo": "Município", "nome": m, "slug": gerar_slug(m)})
            
        print(f"--- EXECUTANDO BLOCO: {BLOCO_ID} ({len(mun_selecionados)} municipios selecionados) ---")
    else:
        anos_alvo = [ANO_ATUAL]
        entes_alvo = [{"tipo": "Estado", "nome": "Espírito Santo", "slug": "estado-es"}] + [
            {"tipo": "Município", "nome": m, "slug": gerar_slug(m)} for m in MUNICIPIOS_ES
        ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1080},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        )

        for ente in entes_alvo:
            slug = ente["slug"]
            
            if slug not in base_consolidada["entes"]:
                base_consolidada["entes"][slug] = {
                    "nome": ente["nome"],
                    "tipo": ente["tipo"],
                    "anos": {}
                }

            for ano in anos_alvo:
                ano_str = str(ano)
                
                anos_salvos = base_consolidada["entes"][slug].get("anos", {})
                if ano_str in anos_salvos and len(anos_salvos[ano_str]) >= len(PAGINAS_ALVO):
                    print(f"-> [CHECKPOINT] Pulando {ente['nome']} ({ano_str}) - ja coletado.")
                    continue

                print(f"--- Coletando {ente['nome']} ({ano_str}) ---")
                
                if ano_str not in base_consolidada["entes"][slug]["anos"]:
                    base_consolidada["entes"][slug]["anos"][ano_str] = {}

                dados_ano = base_consolidada["entes"][slug]["anos"][ano_str]

                for chave_pagina, rota in PAGINAS_ALVO.items():
                    if chave_pagina in dados_ano and dados_ano[chave_pagina].get("quadros"):
                        continue

                    dados_ano[chave_pagina] = await coletar_pagina_json(
                        context, ente["tipo"], slug, ano, chave_pagina, rota
                    )

                base_consolidada["entes"][slug]["anos"][ano_str] = dados_ano

                caminho_ente_json = os.path.join(PASTA_MUNICIPIOS, f"{slug}.json")
                with open(caminho_ente_json, "w", encoding="utf-8") as f:
                    json.dump(base_consolidada["entes"][slug], f, ensure_ascii=False, indent=2)

                base_consolidada["ultima_atualizacao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(ARQUIVO_JSON_CONSOLIDADO, "w", encoding="utf-8") as f:
                    json.dump(base_consolidada, f, ensure_ascii=False)

        await browser.close()

    print(f"Concluido! JSON salvo em: {ARQUIVO_JSON_CONSOLIDADO}")

if __name__ == "__main__":
    asyncio.run(main())
