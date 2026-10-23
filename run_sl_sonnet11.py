"""Benchmark run matching dbt's methodology: 11-question subset, Sonnet 5.5 (Bedrock),
semantic_layer strategy, on the REMODELED project (3 bridge models added).

Results append to llm_bench.db.
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

from llm_bench.config import SemanticLayerConfig, validate_configs
from llm_bench.runners import run_matrix_benchmark
from llm_bench.utils.challenge_loader import load_challenges_from_ttl

# 11-question subset: each maps to a metric/dimension combination the modeled
# Semantic Layer supports (claims, policies, loss, premium, policy size,
# time-to-settle, loss ratio, policies-per-holder, policies-per-agent).
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

cfg = SemanticLayerConfig(
    model_name="bedrock:us.anthropic.claude-sonnet-5-5",
    number_of_iterations=2,
    selected_challenges=SUBSET,
    config_comment="SL-only, Sonnet 5.5, 11-question subset, remodeled project",
)
validate_configs([cfg])

challenges = load_challenges_from_ttl("benchmark_questions.ttl", selected_challenges=SUBSET)
logger.info(f"Loaded {len(challenges)} challenges (subset)")

answers, results_df = run_matrix_benchmark(
    [cfg], challenges=challenges, parallel=False,
    parallel_challenges=False,  # sequential: avoids Bedrock concurrency/throttling
)

total = len(answers)
correct = sum(1 for a in answers if getattr(a, "is_correct", False))
print("\n==================== RUN COMPLETE ====================")
print(f"answers: {total}  correct: {correct}  accuracy: {correct/total*100:.1f}%" if total else "no answers")
