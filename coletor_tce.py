import os
import re
import json
import asyncio
import unicodedata
from datetime import datetime
from playwright.async_api import async_playwright

# Lê as variáveis enviadas pelo GitHub Actions
MODO_EXECUCAO = os.getenv("MODO_EXECUCAO", "mensal")  # 'teste_rapido', 'historico_completo' ou 'mensal'
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
    "visaoGeral": {
        "rota": "visaoGeral",
        "mapeamento_indicadores": {
            "saude": ["saúde", "saude", "aplicação em saúde"],
            "educacao": ["educação", "educacao", "manutenção e desenvolvimento do ensino"],
            "pessoal_consolidado": ["pessoal consolidado", "despesa com pessoal - consolidado", "consolidado"],
            "pessoal_executivo": ["pessoal executivo", "poder executivo", "executivo"],
            "pessoal_legislativo": ["pessoal legislativo", "poder legislativo", "legislativo"],
            "despesas_x_receitas_correntes": ["despesas x receitas correntes", "operações de crédito", "capag", "relação entre despesas correntes"],
            "divida_consolidada_liquida": ["dívida consolidada líquida", "divida consolidada liquida", "endividamento"]
        }
    },
    "receitas": {
        "rota": "gestaoOrcamentaria/receitas",
        "mapeamento_indicadores": {
            "receitas_x_despesas": ["receitas x despesas", "comparativo receita", "prevista", "arrecadada"],
            "evolucao_anual_receita": ["evolução anual", "evolucao anual", "histórico anual"],
            "arrecadacao_comparada_ano_anterior": ["ano anterior", "comparada ao ano anterior", "variação"],
            "receitas_proprias": ["receitas próprias", "receitas proprias", "arrecadação própria"],
            "transferencias_estado": ["transferências do estado", "transferencias do estado", "icms", "ipva"],
            "transferencias_uniao": ["transferências da união", "transferencias da uniao", "fpm"],
            "evolucao_mensal_receita": ["evolução mensal", "evolucao mensal", "mensal"]
        }
    },
    "despesas": {
        "rota": "gestaoOrcamentaria/despesas",
        "mapeamento_indicadores": {
            "composicao_despesa_liquidada": ["composição da despesa liquidada", "composicao"],
            "despesas_pagas_ano_anterior": ["despesas pagas em relação ao ano anterior", "ano anterior"],
            "evolucao_empenhadas_liquidadas_pagas": ["empenhadas", "liquidadas", "pagas"],
            "evolucao_mensal_despesas": ["evolução mensal", "evolucao mensal"],
            "despesas_correntes": ["despesas correntes", "custeio"],
            "despesas_capital": ["despesas de capital", "investimentos"],
            "distribuicao_despesas_liquidadas": ["distribuição das despesas", "distribuicao", "função"]
        }
    },
    "dividaConsolidada": {
        "rota": "gestaoFiscal/endividamento",
        "mapeamento_indicadores": {
            "evolucao_mensal": ["evolução mensal", "evolucao mensal", "bimestral", "quadrimestral"],
            "evolucao_anual": ["evolução anual", "evolucao anual"],
            "evolucao_percentual_anual": ["evolução percentual", "percentual anual", "% da rcl"]
        }
    },
    "fundeb": {
        "rota": "gestaoFiscal/educacaoFundeb",
        "mapeamento_indicadores": {
            "destinado": ["destinado", "enviado ao fundeb", "contribuição"],
            "recebido": ["recebido", "retorno do fundeb", "transferência recebida"],
            "evolucao_anual_municipio": ["evolução anual do município", "evolucao anual", "resultado líquido"],
            "evolucao_anual_magisterio": ["magistério", "magisterio", "profissionais da educação", "70%"]
        }
    },
    "receitaCorrenteLiquida": {
        "rota": "gestaoFiscal/receitaCorrenteLiquida",
        "mapeamento_indicadores": {
            "evolucao_mensal_rcl": ["evolução mensal", "evolucao mensal"],
            "evolucao_anual_rcl": ["evolução anual", "evolucao anual"],
            "rcl_ajustada_endividamento": ["ajustada", "endividamento", "rcl ajustada"]
        }
    }
}

def gerar_slug(nome):
    sem_acento = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn')
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', sem_acento).strip().lower()
    return re.sub(r'[\s]+', '-', slug)

def converter_numero_br(texto):
    if isinstance(texto, (int, float)):
        return texto
    if not isinstance(texto, str):
        return None
    limpo = re.sub(r'[R$\s%]', '', texto).replace('.', '').replace(',', '.')
    try:
        return float(limpo)
    except ValueError:
        return None

def limpar_payload_api(dados):
    if isinstance(dados, list):
        return [limpar_payload_api(item) for item in dados if item is not None]
    elif isinstance(dados, dict):
        dicionario_limpo = {}
        chaves_ignorar = {"id", "guid", "cor", "color", "icone", "icon", "tooltip", "ordem", "style", "classeCss"}
        for k, v in dados.items():
            if k not in chaves_ignorar and v is not None and v != "":
                dicionario_limpo[k] = limpar_payload_api(v)
        return dicionario_limpo
    return dados

def classificar_endpoint_ou_bloco(identificador_texto, mapeamento):
    texto_lower = identificador_texto.lower()
    for chave_limpa, termos_busca in mapeamento.items():
        if any(termo in texto_lower for termo in termos_busca):
            return chave_limpa
    return None

async def coletar_pagina_json(context, tipo_ente, slug_ente, ano, chave_pagina, info_pagina):
    rota = info_pagina["rota"]
    mapeamento = info_pagina["mapeamento_indicadores"]
    tirar_print = GERAR_PRINTS and (ano == ANO_ATUAL)

    if tipo_ente == "Estado":
        url = f"https://paineldecontrole.tcees.tc.br/estado/{ano}/{rota}"
        pasta_ente_print = os.path.join(PASTA_PRINTS, "estado-es")
    else:
        url = f"https://paineldecontrole.tcees.tc.br/municipio/{ano}/{slug_ente}/{rota}"
        pasta_ente_print = os.path.join(PASTA_PRINTS, slug_ente)

    resultado_pagina = {
        "url_fonte": url,
        "indicadores": {},
        "series_dados": {}
    }

    if tirar_print:
        os.makedirs(pasta_ente_print, exist_ok=True)
        caminho_print = os.path.join(pasta_ente_print, f"{chave_pagina}_{ano}.jpg")
        resultado_pagina["print_auditoria"] = caminho_print

    page = await context.new_page()

    async def interceptar_response(response):
        try:
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type and response.status == 200:
                url_resp = response.url
                if not any(ign in url_resp for ign in [".json", "assets", "i18n", "config"]):
                    dados_json = await response.json()
                    nome_endpoint = url_resp.split("paineldecontrole.tcees.tc.br")[-1].split("?")[0].strip("/")
                    chave_identificada = classificar_endpoint_ou_bloco(
                        nome_endpoint + " " + json.dumps(dados_json, ensure_ascii=False)[:300],
                        mapeamento
                    )
                    chave_final = chave_identificada or nome_endpoint.split("/")[-1]
                    resultado_pagina["series_dados"][chave_final] = limpar_payload_api(dados_json)
        except Exception:
            pass

    page.on("response", interceptar_response)

    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        try:
            await page.wait_for_function(
                "() => !document.body.innerText.includes('Obtendo os dados') && !document.body.innerText.includes('Carregando...')",
                timeout=12000
            )
        except Exception:
            pass

        if tirar_print:
            await page.evaluate("""async () => {
                await new Promise((resolve) => {
                    let totalHeight = 0, distance = 500;
                    let timer = setInterval(() => {
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        if(totalHeight >= document.body.scrollHeight){
                            clearInterval(timer);
                            window.scrollTo(0, 0);
                            resolve();
                        }
                    }, 120);
                });
            }""")
            await asyncio.sleep(2.0)
            await page.screenshot(path=caminho_print, full_page=True, type="jpeg", quality=85)
        else:
            await asyncio.sleep(0.4)

        cards_extraidos = await page.evaluate("""() => {
            const cards = [];
            const seletores = 'mat-card, .card, .painel, .box, section, [class*="card"], [class*="quadro"]';
            const elementos = Array.from(document.querySelectorAll(seletores));
            const vistos = new Set();

            elementos.forEach(el => {
                const texto = (el.innerText || '').trim();
                if (texto.length > 5 && texto.length < 1500 && !vistos.has(texto)) {
                    vistos.add(texto);
                    const linhas = texto.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                    const numeros = texto.match(/(?:R\\$\\s*)?-?\\d{1,3}(?:\\.\\d{3})*(?:,\\d+)?%?/g) || [];
                    if (linhas.length > 0 && numeros.length > 0) {
                        cards.push({
                            titulo: linhas.slice(0, 2).join(' - '),
                            texto_busca: texto,
                            valores_brutos: numeros
                        });
                    }
                }
            });
            return cards;
        }""")

        for c in cards_extraidos:
            chave_card = classificar_endpoint_ou_bloco(c["texto_busca"], mapeamento)
            if chave_card:
                valores_numericos = []
                for val_str in c["valores_brutos"]:
                    num_float = converter_numero_br(val_str)
                    if num_float is not None:
                        valores_numericos.append({
                            "valor": num_float,
                            "unidade": "%" if "%" in val_str else ("R$" if "R$" in val_str else "numero")
                        })
                if valores_numericos:
                    resultado_pagina["indicadores"][chave_card] = (
                        valores_numericos[0] if len(valores_numericos) == 1 else valores_numericos
                    )

    except Exception as e:
        print(f"[!] Erro em {slug_ente} ({ano}) - {chave_pagina}: {e}")
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
        print("⚡ MODO TESTE RÁPIDO: Coletando Estado do ES e Afonso Cláudio (2025 e 2026)...")
        anos_alvo = [2025, ANO_ATUAL]
        entes_alvo = [
            {"tipo": "Estado", "nome": "Espírito Santo", "slug": "estado-es"},
            {"tipo": "Município", "nome": "Afonso Cláudio", "slug": "afonso-claudio"}
        ]
    elif MODO_EXECUCAO == "historico_completo":
        anos_alvo = list(range(2019, ANO_ATUAL + 1))
        entes_alvo = [{"tipo": "Estado", "nome": "Espírito Santo", "slug": "estado-es"}] + [
            {"tipo": "Município", "nome": m, "slug": gerar_slug(m)} for m in MUNICIPIOS_ES
        ]
    else:
        anos_alvo = [ANO_ATUAL]
        entes_alvo = [{"tipo": "Estado", "nome": "Espírito Santo", "slug": "estado-es"}] + [
            {"tipo": "Município", "nome": m, "slug": gerar_slug(m)} for m in MUNICIPIOS_ES
        ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1080}, locale="pt-BR")

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
                print(f"🔄 Coletando {ente['nome']} ({ano_str})...")
                dados_ano = {}

                for chave_pagina, info_pagina in PAGINAS_ALVO.items():
                    dados_ano[chave_pagina] = await coletar_pagina_json(
                        context, ente["tipo"], slug, ano, chave_pagina, info_pagina
                    )

                base_consolidada["entes"][slug]["anos"][ano_str] = dados_ano

            caminho_ente_json = os.path.join(PASTA_MUNICIPIOS, f"{slug}.json")
            with open(caminho_ente_json, "w", encoding="utf-8") as f:
                json.dump(base_consolidada["entes"][slug], f, ensure_ascii=False, indent=2)

            base_consolidada["ultima_atualizacao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(ARQUIVO_JSON_CONSOLIDADO, "w", encoding="utf-8") as f:
                json.dump(base_consolidada, f, ensure_ascii=False)

        await browser.close()

    print(f"\n✅ Concluído! JSON salvo em: {ARQUIVO_JSON_CONSOLIDADO}")

if __name__ == "__main__":
    asyncio.run(main())
