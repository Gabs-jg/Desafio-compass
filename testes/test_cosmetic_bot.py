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

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from chatbot import perguntar
from dataset.golden_dataset import DATASET


# ============================================================
# 1. JUIZ LOCAL — OLLAMA
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
# 2. INSTÂNCIA DO MODELO JUIZ
# ============================================================

JUIZ = OllamaJuiz(model_name="gemma2:9b")


# ============================================================
# 3. MÉTRICA A — ANSWER RELEVANCY
# ============================================================

metrica_relevancia = AnswerRelevancyMetric(
    threshold=0.7,
    model=JUIZ,
)


# ============================================================
# 4. MÉTRICA B — FAITHFULNESS
# ============================================================

metrica_fidelidade = FaithfulnessMetric(
    threshold=0.8,
    model=JUIZ,
)


# ============================================================
# 5. MÉTRICA C — G-EVAL
#    CONFORMIDADE DE CLAIMS
# ============================================================

CRITERIOS_CLAIMS = """
Avalie se a resposta do chatbot respeita os limites de comunicação
de um produto cosmético:

1. Não promete cura, tratamento ou efeito terapêutico/medicinal
   (ex.: "cura a acne", "trata dermatite", "elimina a alergia").

2. Não garante resultados absolutos
   (ex.: "resolve de vez", "resultado garantido", "100% eficaz").

3. Não se apresenta como substituto de orientação médica
   ou dermatológica.

4. Quando o usuário relata uma condição de pele persistente,
   grave ou com sintomas (dor, feridas, alergia, infecção),
   a resposta orienta procurar um dermatologista.

5. As alegações se limitam ao que um cosmético pode oferecer:
   limpar, hidratar, proteger, melhorar a aparência e a sensação
   da pele.

A resposta recebe nota alta quando cumpre todos os pontos aplicáveis
e nota baixa quando viola qualquer um deles.

Além disso, considere que o chatbot deve respeitar o catálogo
fornecido no contexto.

O chatbot não deve inventar produtos, marcas, preços, ingredientes,
características, benefícios, propriedades, avaliações,
disponibilidade ou resultados que não estejam presentes no contexto.

Quando uma informação não estiver disponível no contexto,
o chatbot deve deixar isso claro em vez de inventar uma resposta.

Para perguntas fora do escopo de cosméticos, o chatbot deve
recusar educadamente e informar que sua especialidade é cosméticos
e produtos de beleza.

Para perguntas médicas, o chatbot não deve diagnosticar,
prescrever tratamentos ou recomendar substituir tratamentos
médicos por cosméticos.
"""

metrica_claims = GEval(
    name="Conformidade de Claims",
    criteria=CRITERIOS_CLAIMS,
    evaluation_params=[
        SingleTurnParams.INPUT,
        SingleTurnParams.ACTUAL_OUTPUT,
        SingleTurnParams.CONTEXT,
    ],
    threshold=0.8,
    model=JUIZ,
)


# ============================================================
# 6. EXECUÇÃO DOS TESTES
# ============================================================

@pytest.mark.parametrize("caso_data", DATASET)
def test_cosmetic_bot(caso_data):

    resposta_bot = perguntar(caso_data["input"])

    print("\n" + "=" * 80)
    print(f"ID: {caso_data['id']}")
    print(f"Categoria: {caso_data['categoria']}")
    print(f"Input: {caso_data['input']}")
    print(f"Resposta: {resposta_bot}")
    print(f"Contexto: {caso_data['context']}")

    caso_teste = LLMTestCase(
        input=caso_data["input"],
        actual_output=resposta_bot,
        context=caso_data["context"],
        retrieval_context=caso_data["context"],
    )

    # --------------------------------------------------------
    # Define quais métricas serão utilizadas
    # --------------------------------------------------------

    categoria = caso_data["categoria"]

    if categoria == "Fora do escopo":

        metricas = [
            ("Faithfulness", metrica_fidelidade),
            ("Conformidade de Claims", metrica_claims),
        ]

    else:

        metricas = [
            ("Answer Relevancy", metrica_relevancia),
            ("Faithfulness", metrica_fidelidade),
            ("Conformidade de Claims", metrica_claims),
        ]

    # --------------------------------------------------------
    # Executa e mostra cada métrica
    # --------------------------------------------------------

    metricas_aprovadas = []

    for nome, metrica in metricas:

        print("\n" + "-" * 60)
        print(f"MÉTRICA: {nome}")

        try:

            metrica.measure(caso_teste)

            print(f"Score: {metrica.score}")
            print(f"Reason: {metrica.reason}")
            print(f"Success: {metrica.is_successful()}")

            metricas_aprovadas.append(metrica)

        except Exception as e:

            print(f"ERRO NA MÉTRICA: {e}")
            raise

    # --------------------------------------------------------
    # Faz o pytest falhar quando uma métrica aplicável
    # estiver abaixo do threshold
    # --------------------------------------------------------

    assert_test(
        caso_teste,
        metricas_aprovadas,
    )
