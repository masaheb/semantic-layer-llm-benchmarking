"""Full semantic_layer benchmark run: all 43 questions, Claude Haiku (Bedrock), 2 iters.

Results append to llm_bench.db (DuckDB). Modest parallelism to stay within limits.
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

cfg = SemanticLayerConfig(
    model_name="bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0",
    number_of_iterations=2,
    config_comment="SL-only, Haiku, all questions",
)
validate_configs([cfg])

challenges = load_challenges_from_ttl("benchmark_questions.ttl", selected_challenges=None)
logger.info(f"Loaded {len(challenges)} challenges")

answers, results_df = run_matrix_benchmark(
    [cfg],
    challenges=challenges,
    parallel=False,
    parallel_challenges=True,
    challenge_max_workers=3,
)

total = len(answers)
correct = sum(1 for a in answers if getattr(a, "is_correct", False))
print("\n==================== RUN COMPLETE ====================")
print(f"answers: {total}  correct: {correct}  accuracy: {correct/total*100:.1f}%" if total else "no answers")
print("results_df shape:", results_df.shape)
