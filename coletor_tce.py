import os
import re
import json
import asyncio
import unicodedata
from datetime import datetime
from playwright.async_api import async_playwright

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
            "educacao": ["educação", "educacao", "manutenção e desenvolvimento do ensino", "ensino"],
            "pessoal_consolidado": ["pessoal consolidado", "despesa com pessoal - consolidado", "consolidado", "pessoal"],
            "pessoal_executivo": ["pessoal executivo", "poder executivo", "executivo"],
            "pessoal_legislativo": ["pessoal legislativo", "poder legislativo", "legislativo"],
            "despesas_x_receitas_correntes": ["despesas x receitas", "receitas correntes", "capag", "relação entre despesas"],
            "divida_consolidada_liquida": ["dívida consolidada", "divida consolidada", "endividamento"]
        }
    },
    "receitas": {
        "rota": "gestaoOrcamentaria/receitas",
        "mapeamento_indicadores": {
            "receitas_x_despesas": ["receitas x despesas", "comparativo", "prevista", "arrecadada"],
            "evolucao_anual_receita": ["evolução anual", "evolucao anual", "histórico anual"],
            "arrecadacao_comparada_ano_anterior": ["ano anterior", "comparada", "variação"],
            "receitas_proprias": ["receitas próprias", "receitas proprias", "própria"],
            "transferencias_estado": ["transferências do estado", "estado", "icms", "ipva"],
            "transferencias_uniao": ["transferências da união", "união", "uniao", "fpm"],
            "evolucao_mensal_receita": ["evolução mensal", "evolucao mensal", "mensal"]
        }
    },
    "despesas": {
        "rota": "gestaoOrcamentaria/despesas",
        "mapeamento_indicadores": {
            "composicao_despesa_liquidada": ["composição", "composicao", "liquidada"],
            "despesas_pagas_ano_anterior": ["ano anterior", "despesas pagas"],
            "evolucao_empenhadas_liquidadas_pagas": ["empenhadas", "liquidadas", "pagas"],
            "evolucao_mensal_despesas": ["evolução mensal", "evolucao mensal"],
            "despesas_correntes": ["despesas correntes", "correntes", "custeio"],
            "despesas_capital": ["despesas de capital", "capital", "investimentos"],
            "distribuicao_despesas_liquidadas": ["distribuição", "distribuicao", "função"]
        }
    },
    "dividaConsolidada": {
        "rota": "gestaoFiscal/endividamento",
        "mapeamento_indicadores": {
            "evolucao_mensal": ["evolução mensal", "evolucao mensal", "bimestral", "quadrimestral"],
            "evolucao_anual": ["evolução anual", "evolucao anual"],
            "evolucao_percentual_anual": ["percentual", "% da rcl", "dcl"]
        }
    },
    "fundeb": {
        "rota": "gestaoFiscal/educacaoFundeb",
        "mapeamento_indicadores": {
            "destinado": ["destinado", "enviado", "contribuição"],
            "recebido": ["recebido", "retorno", "transferência"],
            "evolucao_anual_municipio": ["evolução anual", "resultado"],
            "evolucao_anual_magisterio": ["magistério", "magisterio", "profissionais", "70%"]
        }
    },
    "receitaCorrenteLiquida": {
        "rota": "gestaoFiscal/receitaCorrenteLiquida",
        "mapeamento_indicadores": {
            "evolucao_mensal_rcl": ["evolução mensal", "evolucao mensal"],
            "evolucao_anual_rcl": ["evolução anual", "evolucao anual"],
            "rcl_ajustada_endividamento": ["ajustada", "endividamento", "rcl"]
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
        chaves_ignorar = {"guid", "cor", "color", "icone", "icon", "tooltip", "style", "classeCss"}
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
        "titulo_pagina": "",
        "indicadores_mapeados": {},
        "quadros_extraidos_tela": [],
        "series_api": {}
    }

    if tirar_print:
        os.makedirs(pasta_ente_print, exist_ok=True)
        caminho_print = os.path.join(pasta_ente_print, f"{chave_pagina}_{ano}.jpg")
        resultado_pagina["print_auditoria"] = caminho_print

    page = await context.new_page()

    # Intercepta TODAS as respostas JSON ou XHR/Fetch vindas do TCE-ES
    async def interceptar_response(response):
        try:
            url_resp = response.url
            # Ignora apenas arquivos de tradução ou fontes/imagens
            if any(ign in url_resp.lower() for ign in ["assets/i18n", ".woff", ".png", ".svg", ".css", ".js"]):
                return

            content_type = response.headers.get("content-type", "").lower()
            if "json" in content_type or "api" in url_resp.lower() or "service" in url_resp.lower():
                if response.status == 200:
                    texto_resp = await response.text()
                    if texto_resp and (texto_resp.strip().startswith("{") or texto_resp.strip().startswith("[")):
                        dados_json = json.loads(texto_resp)
                        # Cria uma chave limpa baseada na URL da API
                        partes_url = [p for p in url_resp.split("?")[0].split("/") if p and not p.startswith("http") and "tcees.tc.br" not in p]
                        nome_endpoint = "_".join(partes_url[-3:]) if len(partes_url) >= 3 else "_".join(partes_url)
                        
                        chave_identificada = classificar_endpoint_ou_bloco(
                            nome_endpoint + " " + texto_resp[:400],
                            mapeamento
                        )
                        chave_final = f"{chave_identificada}__{nome_endpoint}" if chave_identificada else nome_endpoint
                        resultado_pagina["series_api"][chave_final] = limpar_payload_api(dados_json)
        except Exception:
            pass

    page.on("response", interceptar_response)

    try:
        # 1. Abre a página com domcontentloaded e aguarda o Angular renderizar
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # 2. Espera até que os textos de carregamento sumam E números reais (R$ ou %) apareçam na tela
        try:
            await page.wait_for_function(
                """() => {
                    const txt = document.body ? document.body.innerText : '';
                    const carregando = txt.includes('Obtendo os dados') || txt.includes('Carregando');
                    const temNumeros = /(\\d+[,.]\\d+)|R\\$|%/.test(txt);
                    return !carregando && temNumeros && txt.length > 300;
                }""",
                timeout=25000
            )
        except Exception:
            # Caso demore mais ou seja uma página sem R$, aguarda 6 segundos fixos
            await asyncio.sleep(6.0)

        # 3. Sempre faz um scroll rápido para disparar gráficos que só carregam ao rolar a tela (lazy load)
        await page.evaluate("""async () => {
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
        await asyncio.sleep(2.5)

        if tirar_print:
            await page.screenshot(path=caminho_print, full_page=True, type="jpeg", quality=85)

        resultado_pagina["titulo_pagina"] = await page.title()

        # 4. Extração inteligente do DOM: pega qualquer card, painel, tabela ou bloco que contenha números
        cards_extraidos = await page.evaluate("""() => {
            const blocos = [];
            const textosVistos = new Set();

            // Seletores amplos para pegar componentes Angular, Bootstrap, Material e tabelas do TCE-ES
            const seletores = [
                'mat-card', '.card', '.painel', '.box', 'section', 'table',
                '[class*="card"]', '[class*="quadro"]', '[class*="painel"]',
                '[class*="indicador"]', '[class*="bloco"]', '[class*="chart"]',
                '[class*="grafico"]', 'app-card', 'div.row > div[class*="col-"]'
            ].join(', ');

            const elementos = Array.from(document.querySelectorAll(seletores));

            elementos.forEach(el => {
                const texto = (el.innerText || '').trim();
                // Ignora blocos gigantes (a página inteira) ou muito curtos
                if (texto.length > 8 && texto.length < 2000 && !textosVistos.has(texto)) {
                    const numeros = texto.match(/(?:R\\$\\s*)?-?\\d{1,3}(?:\\.\\d{3})*(?:,\\d+)?%?/g) || [];
                    if (numeros.length > 0) {
                        textosVistos.add(texto);
                        const linhas = texto.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                        blocos.push({
                            titulo: linhas.slice(0, 2).join(' | '),
                            linhas: linhas,
                            texto_busca: texto,
                            valores_brutos: numeros
                        });
                    }
                }
            });

            // Fallback: se nenhum seletor específico bateu, divide o texto visível da página em blocos com números
            if (blocos.length === 0 && document.body) {
                const linhasBody = (document.body.innerText || '')
                    .split('\\n')
                    .map(l => l.trim())
                    .filter(l => l.length > 0);
                
                for (let i = 0; i < linhasBody.length; i++) {
                    const l = linhasBody[i];
                    const nums = l.match(/(?:R\\$\\s*)?-?\\d{1,3}(?:\\.\\d{3})*(?:,\\d+)?%?/g);
                    if (nums) {
                        const contexto = linhasBody.slice(Math.max(0, i - 2), Math.min(linhasBody.length, i + 2));
                        blocos.push({
                            titulo: contexto[0] || 'Item',
                            linhas: contexto,
                            texto_busca: contexto.join(' | '),
                            valores_brutos: nums
                        });
                    }
                }
            }
            return blocos;
        }""")

        for c in cards_extraidos:
            valores_limpos = []
            for val_str in c["valores_brutos"]:
                num_float = converter_numero_br(val_str)
                if num_float is not None:
                    valores_limpos.append({
                        "valor": num_float,
                        "formatado": val_str.strip(),
                        "unidade": "%" if "%" in val_str else ("R$" if "R$" in val_str else "numero")
                    })

            if not valores_limpos:
                continue

            # Guarda no array estruturado de quadros da tela
            resultado_pagina["quadros_extraidos_tela"].append({
                "titulo": c["titulo"],
                "detalhes": c["linhas"],
                "metricas": valores_limpos
            })

            # Se também bater com um dos seus indicadores-chave nomeados, adiciona direto em indicadores_mapeados
            chave_card = classificar_endpoint_ou_bloco(c["texto_busca"], mapeamento)
            if chave_card and chave_card not in resultado_pagina["indicadores_mapeados"]:
                resultado_pagina["indicadores_mapeados"][chave_card] = {
                    "rotulo_original": c["titulo"],
                    "metricas": valores_limpos
                }

        print(
            f"   ✓ [{ano}] {slug_ente} | {chave_pagina}: "
            f"{len(resultado_pagina['series_api'])} APIs capturadas, "
            f"{len(resultado_pagina['quadros_extraidos_tela'])} quadros com números extraídos."
        )

    except Exception as e:
        print(f"   [!] Erro em {slug_ente} ({ano}) - {chave_pagina}: {e}")
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
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        # Simula um navegador Chrome real no Windows em português do Brasil
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
                print(f"\n🔄 Co
