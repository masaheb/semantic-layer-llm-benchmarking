"""Text-to-SQL comparison run: same 11 questions, Sonnet 5.5 (Bedrock), sequential.

The LLM writes raw SQL from the ACME DDL; generated SQL is qualified to acme_prod
and executed via the SL SQL passthrough, then compared to gold. Direct head-to-head
against the semantic_layer run.
"""
import sys
import warnings

import nest_asyncio
from loguru import logger

sys.path.insert(0, "src")
nest_asyncio.apply()
warnings.filterwarnings("ignore")
logger.remove()
logger.add(sys.stdout, level="INFO")

from llm_bench.config import SQLConfig, validate_configs
from llm_bench.runners import run_matrix_benchmark
from llm_bench.utils.challenge_loader import load_challenges_from_ttl

SUBSET = [
    "How many claims do we have?",
    "How many policies do we have?",
    "What is the total loss amounts, which is the sum of loss payment, loss reserve amount by claim number?",
    "How many claims have been placed by policy number?",
    "What is the average time to settle a claim by policy number?",
    "How many policies does each policy holder have by policy holder id?",
    "How many policies have agents sold by agent id?",
    "What is the total amount of premiums paid by policy number?",
    "What is the average policy size which is the the total amount of premium divided by the number of policies?",
    "What are all the premiums that have been paid by policy holders?",
    "What is the premium amount of all policies by policy number?",
]

cfg = SQLConfig(
    model_name="bedrock:us.anthropic.claude-sonnet-5-5",
    number_of_iterations=2,
    selected_challenges=SUBSET,
    ddl_file="ACME_small.ddl",
    config_comment="text-to-SQL, Sonnet 5.5, 11-question subset",
)
validate_configs([cfg])

challenges = load_challenges_from_ttl("benchmark_questions.ttl", selected_challenges=SUBSET)
logger.info(f"Loaded {len(challenges)} challenges (subset)")

answers, results_df = run_matrix_benchmark(
    [cfg], challenges=challenges, parallel=False, parallel_challenges=False,
)

total = len(answers)
correct = sum(1 for a in answers if getattr(a, "is_correct", False))
print("\n==================== TEXT-TO-SQL RUN COMPLETE ====================")
print(f"answers: {total}  correct: {correct}  accuracy: {correct/total*100:.1f}%" if total else "no answers")
