"""Compare the vignettes and the environment, which ask the same question in different situations.

For each model and condition, prints the cooperate rate in the normal and mirror variants and the
share of choices matching each prediction:

    risk-neutral   defect in normal, cooperate in mirror
    CARA (0.01)    cooperate in normal, defect in mirror
    compliant      cooperate in both

    uv run python analyze.py [log_dir ...]    # default: logs/openrouter and logs/adapters
"""

import re
import sys
from pathlib import Path

import pandas as pd
from inspect_ai.log import read_eval_log

LOGS = Path(__file__).resolve().parent / "logs"
SETTINGS = {"deals": "vignette", "deal_env": "environment", "lottery": "lottery"}

# Models served by modal_serve.py, named after what they are.
REMOTE = {"base": "qwen3-14b (vllm)", "sft": "qwen3-14b + sft", "dpo": "qwen3-14b + dpo",
          "tie": "qwen3-14b + tie"}  # fmt: skip


def model_name(model: str) -> str:
    if model.startswith("openai-api/remote/"):
        return REMOTE[model.removeprefix("openai-api/remote/")]
    return model.removeprefix("openrouter/qwen/")


def letter(sample) -> str | None:
    """The chosen letter. Falls back to the last 'ANSWER: X' in the output, since some adapters
    write 'FINAL ANSWER: ANSWER: A', which Inspect's choice() scorer does not parse."""
    score = next(iter(sample.scores.values()))
    if score.answer:
        return score.answer
    found = re.findall(r"ANSWER:\s*\$?([A-Z])\b", sample.output.completion)
    return found[-1] if found else None


def load(log_dir: str | Path = LOGS / "openrouter") -> pd.DataFrame:
    rows = []
    for f in sorted(Path(log_dir).glob("*.eval")):
        log = read_eval_log(str(f))
        if log.status != "success":
            continue
        for s in log.samples:
            score = next(iter(s.scores.values()))
            setting = SETTINGS[log.eval.task.split("/")[-1]]
            if setting == "environment":
                answer, y = score.answer, float(score.value == 1)
            else:  # target letter = cooperate (vignettes) or safe lottery
                answer = letter(s)
                y = float(answer == s.target)
            rows.append(
                {
                    "setting": setting,
                    "id": s.id,
                    "epoch": s.epoch,
                    "model": model_name(log.eval.model),
                    "condition": log.eval.task_args["condition"],
                    "variant": s.metadata.get("variant"),
                    "family": s.metadata.get("family"),
                    "order": s.metadata.get("order"),
                    "p_success": s.metadata["p_success"],
                    "cara_safe": s.metadata["cara_safe"],
                    "answer": answer,
                    "y": y,
                }
            )
    return pd.DataFrame(rows)


def main(*log_dirs: str) -> None:
    df = pd.concat([load(d) for d in log_dirs or (LOGS / "openrouter", LOGS / "adapters") if Path(d).exists()])
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 200)

    # Episodes with no decision and answers with no letter are not choices.
    missing = df.answer.isna() | (df.answer == "none")
    print("No decision / no answer (dropped):")
    print(df[missing].groupby(["model", "condition", "setting"]).size().to_string() or "  none")
    df = df[~missing]

    deal = df[df.setting != "lottery"].copy()
    risky_is_coop = deal.variant == "mirror"
    deal["risk_neutral"] = (deal.y == risky_is_coop).astype(float)
    deal["cara"] = (deal.y == (risky_is_coop ^ deal.cara_safe)).astype(float)

    keys = ["model", "condition", "setting"]
    by_variant = deal.pivot_table("y", keys, "variant", aggfunc="mean")
    matches = deal.groupby(keys)[["risk_neutral", "cara"]].mean()
    n = deal.groupby(keys + ["variant"]).size().unstack()
    table = pd.concat(
        [by_variant.add_prefix("coop_"), matches.add_prefix("match_"), n.add_prefix("n_")], axis=1
    )
    print("\n== Same question, two situations ==")
    print(table.round(2).unstack("setting").swaplevel(axis=1).sort_index(axis=1))

    print("\n== Cooperate rate by p_success ==")
    print(deal.pivot_table("y", keys + ["variant"], "p_success", aggfunc="mean").round(2))

    print("\n== Vignettes by family ==")
    vig = deal[deal.setting == "vignette"]
    print(vig.pivot_table("y", ["model", "condition", "family"], "variant", aggfunc="mean").round(2))

    print("\n== Vignettes, position bias (cooperate rate by option order) ==")
    print(vig.pivot_table("y", ["model", "condition"], "order", aggfunc="mean").round(2))

    print("\n== Lottery: safe-choice rate by p_success (CARA: always safe) ==")
    lot = df[df.setting == "lottery"]
    print(lot.pivot_table("y", ["model", "condition"], "p_success", aggfunc="mean").round(2))


if __name__ == "__main__":
    main(*sys.argv[1:])
