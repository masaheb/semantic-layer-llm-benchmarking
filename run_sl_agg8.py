"""SL run on the 8 AGGREGATE-answerable questions (the 3 detail-listing questions
are out of semantic-layer scope by design and excluded). Sonnet 5.5, sequential."""
import sys, warnings
import nest_asyncio
from loguru import logger
sys.path.insert(0, "src")
nest_asyncio.apply(); warnings.filterwarnings("ignore")
logger.remove(); logger.add(sys.stdout, level="INFO")

from llm_bench.config import SemanticLayerConfig, validate_configs
from llm_bench.runners import run_matrix_benchmark
from llm_bench.utils.challenge_loader import load_challenges_from_ttl

AGG8 = [
    "How many claims do we have?",
    "How many policies do we have?",
    "How many claims have been placed by policy number?",
    "What is the average time to settle a claim by policy number?",
    "How many policies does each policy holder have by policy holder id?",
    "How many policies have agents sold by agent id?",
    "What is the total amount of premiums paid by policy number?",
    "What is the average policy size which is the the total amount of premium divided by the number of policies?",
]
cfg = SemanticLayerConfig(model_name="bedrock:us.anthropic.claude-sonnet-5-5",
                          number_of_iterations=2, selected_challenges=AGG8,
                          config_comment="SL, Sonnet 5.5, 8 aggregate questions")
validate_configs([cfg])
challenges = load_challenges_from_ttl("benchmark_questions.ttl", selected_challenges=AGG8)
logger.info(f"Loaded {len(challenges)} challenges")
answers, _ = run_matrix_benchmark([cfg], challenges=challenges, parallel=False, parallel_challenges=False)
total = len(answers); correct = sum(1 for a in answers if getattr(a, "is_correct", False))
print("\n==================== SL AGG8 COMPLETE ====================")
print(f"answers: {total}  correct: {correct}  accuracy: {correct/total*100:.1f}%" if total else "no answers")
