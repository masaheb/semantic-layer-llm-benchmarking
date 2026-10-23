"""Run dbt's exact 11 benchmark questions (taken from dbt's published
llm_bench_dashboard.db), on Sonnet 5.5 via Bedrock, sequentially.

Usage:
  uv run python run_dbt11.py <semantic_layer|sql> <iterations>

The sql strategy uses ACME_enhanced_redshift.ddl: dbt's enhanced DDL (includes the
3 bridge models) with the schema repointed to acme_prod.
Results append to llm_bench.db, tagged via config_comment.
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

from llm_bench.config import SemanticLayerConfig, SQLConfig, validate_configs
from llm_bench.runners import run_matrix_benchmark
from llm_bench.utils.challenge_loader import load_challenges_from_ttl

DBT11 = [
    "How many claims do we have?",
    "How many claims have been placed by policy number?",
    "How many policies do we have?",
    "How many policies does each policy holder have by policy holder id?",
    "How many policies have agents sold by agent id?",
    "What is the average policy size which is the the total amount of premium divided by the number of policies?",
    "What is the average time to settle a claim by policy number?",
    "What is the total amount of premiums paid by policy number?",
    "What is the total amount of premiums that a policy holder has paid by policy number?",
    "What is the total amount of premiums that a policy holder has paid?",
    "What is the total loss amounts, which is the sum of loss payment, loss reserve amount by claim number?",
]
MODEL = "bedrock:us.anthropic.claude-sonnet-5-5"

strategy = sys.argv[1]
iters = int(sys.argv[2])
comment = f"dbt11 x{iters} {strategy} sonnet-5-5"

if strategy == "semantic_layer":
    cfg = SemanticLayerConfig(model_name=MODEL, number_of_iterations=iters,
                              selected_challenges=DBT11, config_comment=comment)
elif strategy == "sql":
    cfg = SQLConfig(model_name=MODEL, number_of_iterations=iters, selected_challenges=DBT11,
                    ddl_file="ACME_enhanced_redshift.ddl", config_comment=comment)
else:
    sys.exit(f"unknown strategy {strategy!r}")
validate_configs([cfg])

challenges = load_challenges_from_ttl("benchmark_questions.ttl", selected_challenges=DBT11)
logger.info(f"Loaded {len(challenges)} challenges")
if len(challenges) != 11:
    sys.exit(f"expected 11 challenges, got {len(challenges)}")

answers, _ = run_matrix_benchmark([cfg], challenges=challenges, parallel=False,
                                  parallel_challenges=False)
total = len(answers)
correct = sum(1 for a in answers if getattr(a, "is_correct", False))
print(f"\n==================== {comment} COMPLETE ====================")
print(f"answers: {total}  correct: {correct}  accuracy: {correct/total*100:.1f}%", flush=True)

# Lingering Flight SQL / asyncio threads can keep the interpreter alive after the
# run finishes. Results are already saved to DuckDB, so exit hard.
import os
os._exit(0)
