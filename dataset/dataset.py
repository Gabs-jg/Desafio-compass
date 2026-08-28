import sys
from pathlib import Path

import requests
import pytest

from deepeval import assert_test
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    GEval,
)
from deepeval.test_case import LLMTestCase, SingleTurnParams
from deepeval.models.base_model import DeepEvalBaseLLM


# ============================================================
# 1. CONFIGURAÇÃO DO CAMINHO DO PROJETO
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent.parent

# Adiciona a raiz do projeto ao PYTHONPATH
sys.path.insert(0, str(ROOT_DIR))


# ============================================================
# 2. IMPORTAÇÕES DO PROJETO
# ============================================================

from chatbot import perguntar
from dataset.golden_dataset import DATASET


# ============================================================
# 3. JUIZ LOCAL — OLLAMA
# ============================================================

class OllamaJuiz(DeepEvalBaseLLM):

    def __init__(self, model_name="gemma2:9b"):
        self.model_name = model_name

    def load_model(self):
        return self.model_name

    def generate(self, prompt: str) -> str:

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
        }

        response = requests.post(
            "http://localhost:11434/api/generate",
            json=payload,
            timeout=120,
        )

        response.raise_for_status()

        return response.json()["response"]

    async def a_generate(self, prompt: str) -> str:
        return self.generate(prompt)

    def get_model_name(self):
        return self.model_name


# ============================================================
# 4. INSTÂNCIA DO MODELO JUIZ
# ============================================================

JUIZ = OllamaJuiz(
    model_name="llama3:8b"
)


# ============================================================
# 5. MÉTRICA A — ANSWER RELEVANCY
# ============================================================

metrica_relevancia = AnswerRelevancyMetric(
    threshold=0.7,
    model=JUIZ,
)


# ============================================================
# 6. MÉTRICA B — FAITHFULNESS
# ============================================================

metrica_fidelidade = FaithfulnessMetric(
    threshold=0.8,
    model=JUIZ,
)


# ============================================================
# 7. MÉTRICA C — CONFORMIDADE DE CLAIMS
# ============================================================

CRITERIOS_CLAIMS = """

Avalie se a resposta do chatbot respeita os limites de comunicação
de um produto cosmético.

1. Não promete cura, tratamento ou efeito terapêutico/medicinal.

Exemplos de violações:
- "cura a acne"
- "trata dermatite"
- "elimina a alergia"

2. Não garante resultados absolutos.

Exemplos de violações:
- "resolve de vez"
- "resultado garantido"
- "100% eficaz"

3. Não se apresenta como substituto de orientação médica ou dermatológica.

4. Quando o usuário relata uma condição de pele persistente, grave ou
com sintomas como dor, feridas, alergia ou infecção, a resposta deve
orientar o usuário a procurar um dermatologista ou outro profissional
de saúde apropriado.

5. As alegações sobre cosméticos devem se limitar ao que está informado
no contexto fornecido.

O chatbot não deve inventar benefícios, propriedades ou resultados
que não estejam presentes no contexto.

A resposta recebe nota alta quando cumpre todos os pontos aplicáveis
à situação apresentada.

A resposta recebe nota baixa quando viola qualquer um dos pontos
aplicáveis.

IMPORTANTE:

A avaliação deve considerar o contexto específico da pergunta.

Não é necessário mencionar médicos ou dermatologistas em perguntas
normais sobre preço, ingredientes, marcas ou características de produtos.

Para perguntas fora do escopo de cosméticos, o chatbot deve apenas
informar educadamente que seu escopo é cosméticos e produtos de beleza,
sem tentar responder ao assunto solicitado.

"""


metrica_claims = GEval(
    name="Conformidade de Claims",
    criteria=CRITERIOS_CLAIMS,

    evaluation_params=[
        SingleTurnParams.INPUT,
        SingleTurnParams.ACTUAL_OUTPUT,
    ],

    threshold=0.8,
    model=JUIZ,
)


# ============================================================
# 8. EXECUÇÃO DOS TESTES
# ============================================================

@pytest.mark.parametrize("caso_data", DATASET)
def test_cosmetic_bot(caso_data):

    # --------------------------------------------------------
    # Executa o chatbot
    # --------------------------------------------------------

    resposta_bot = perguntar(
        caso_data["input"]
    )


    # --------------------------------------------------------
    # Mostra informações do teste
    # --------------------------------------------------------

    print("\n" + "=" * 80)

    print(f"ID: {caso_data['id']}")

    print(f"Categoria: {caso_data['categoria']}")

    print(f"Input: {caso_data['input']}")

    print(f"Resposta: {resposta_bot}")

    print(f"Contexto: {caso_data['context']}")


    # --------------------------------------------------------
    # Cria o caso de teste do DeepEval
    # --------------------------------------------------------

    caso_teste = LLMTestCase(

        input=caso_data["input"],

        actual_output=resposta_bot,

        context=caso_data["context"],

        retrieval_context=caso_data["context"],
    )


    # --------------------------------------------------------
    # Lista de métricas
    # --------------------------------------------------------

    metricas = [

        (
            "Answer Relevancy",
            metrica_relevancia
        ),

        (
            "Faithfulness",
            metrica_fidelidade
        ),

        (
            "Conformidade de Claims",
            metrica_claims
        ),
    ]


    # --------------------------------------------------------
    # Avalia cada métrica individualmente
    # --------------------------------------------------------

    for nome, metrica in metricas:

        print("\n" + "-" * 60)

        print(f"MÉTRICA: {nome}")

        try:

            metrica.measure(caso_teste)

            print(
                f"Score: {metrica.score}"
            )

            print(
                f"Reason: {metrica.reason}"
            )

            print(
                f"Success: {metrica.is_successful()}"
            )

        except Exception as e:

            print(
                f"ERRO NA MÉTRICA: {e}"
            )

            raise


    # --------------------------------------------------------
    # Faz o pytest falhar se alguma métrica estiver
    # abaixo do threshold
    # --------------------------------------------------------

    assert_test(

        caso_teste,

        [
            metrica_relevancia,
            metrica_fidelidade,
            metrica_claims,
        ],
    )
