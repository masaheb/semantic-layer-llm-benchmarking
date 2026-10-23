"""Minimal smoke test: one semantic_layer question, one iteration, on Bedrock.

Proves the full loop: LLM generates an SL query -> executed against the dbt
Semantic Layer (Redshift) -> compared to the gold answer. Near-zero cost.
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

cfg = SemanticLayerConfig(
    model_name="bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0",
    number_of_iterations=1,
    selected_challenges=["How many policies do we have?"],
)
validate_configs([cfg])

answers, results_df = run_matrix_benchmark(
    [cfg], parallel=False, parallel_challenges=False
)

print("\n==================== SMOKE TEST RESULT ====================")
for a in answers:
    print(f"method={a.method}  correct={getattr(a, 'is_correct', None)}")
    print(f"generated SQL:\n{getattr(a, 'sql', None)}")
    print(f"comparison_error: {getattr(a, 'comparison_error', None)}")
print("\nresults_df shape:", results_df.shape)
if not results_df.empty:
    print(results_df.to_string())
