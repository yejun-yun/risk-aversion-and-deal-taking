"""Figures for results.md, from the Modal runs in logs/adapters/ (untrained and trained models on
the same server).

    uv run python figures.py    # writes figures/*.png
"""

import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from inspect_ai.log import read_eval_log

from analyze import LOGS, SETTINGS, load, model_name

OUT = Path(__file__).parent / "figures"

# (model, condition) -> label, in plot order.
ROWS = {
    ("qwen3-14b (vllm)", "baseline"): "Untrained",
    ("qwen3-14b (vllm)", "ra_generic"): "Untrained + ra_generic prompt",
    ("qwen3-14b (vllm)", "ra_cara"): "Untrained + ra_cara prompt",
    ("qwen3-14b + sft", "baseline"): "SFT adapter",
    ("qwen3-14b + dpo", "baseline"): "DPO adapter",
    ("qwen3-14b + tie", "baseline"): "Tie adapter",
}
COLORS = {"lottery": "#9e9e9e", "vignette": "#4c78a8", "environment": "#f58518"}


def data():
    df = load(LOGS / "adapters")
    df = df[~(df.answer.isna() | (df.answer == "none"))].copy()
    deal = df.setting != "lottery"
    # CARA match: cooperate in normal, defect in mirror. In the lottery, picking safe.
    df["cara"] = df.y
    df.loc[deal, "cara"] = (df.y[deal] == (df.variant[deal] == "normal")).astype(float)
    df["label"] = [ROWS.get((m, c)) for m, c in zip(df.model, df.condition)]
    return df[df.label.notna()]


# The model writes out u(w) = 1 - exp(-0.01w) or similar.
UTILITY = re.compile(r"exp\(\s*-\s*0\.01|e\^\(?-0\.01", re.IGNORECASE)


def utility_use(log_dir=LOGS / "adapters"):
    """Per sample: whether the model's reasoning or answer writes out the CARA utility function."""
    rows = []
    for f in sorted(Path(log_dir).glob("*.eval")):
        log = read_eval_log(str(f), resolve_attachments=True)
        label = ROWS.get((model_name(log.eval.model), log.eval.task_args["condition"]))
        for s in log.samples:
            text = "".join(
                m.content if isinstance(m.content, str)
                else "".join(getattr(b, "reasoning", None) or getattr(b, "text", "") or "" for b in m.content)
                for m in s.messages if m.role == "assistant"
            )  # fmt: skip
            rows.append({"label": label, "setting": SETTINGS[log.eval.task.split("/")[-1]],
                         "id": s.id, "epoch": s.epoch, "uses": bool(UTILITY.search(text))})  # fmt: skip
    return pd.DataFrame(rows)


SETTING_NAMES = {"lottery": "Plain lottery", "vignette": "Vignette\n(asked what it would do)",
                 "environment": "Environment\n(acts as an agent)"}  # fmt: skip
PROMPTED = ["Untrained", "Untrained + ra_generic prompt", "Untrained + ra_cara prompt"]  # fmt: skip
TRAINED = ["Untrained", "SFT adapter", "DPO adapter", "Tie adapter"]
SHORT = {"Untrained": "Untrained, no prompt", "Untrained + ra_generic prompt": '"Be risk-averse" prompt',
         "Untrained + ra_cara prompt": "Utility-function prompt", "SFT adapter": "SFT",
         "DPO adapter": "DPO", "Tie adapter": "Tie training"}  # fmt: skip
LINE = {"Untrained": "#7f7f7f", "Untrained + ra_generic prompt": "#1f77b4", "Untrained + ra_cara prompt": "#d62728",
        "SFT adapter": "#9467bd", "DPO adapter": "#8c564b", "Tie adapter": "#2ca02c"}  # fmt: skip


def grouped_bars(ax, table, labels, legend_y=-0.12):
    """Horizontal bars: one group per model, one bar per setting, value printed at the end."""
    y = np.arange(len(labels))
    h = 0.27
    for k, (s, name) in enumerate(SETTING_NAMES.items()):
        g = table.loc[labels, s]
        ax.barh(y + (k - 1) * h, g["mean"], h, xerr=g["ci"], color=COLORS[s],
                label=name.replace("\n", " "), error_kw={"elinewidth": 0.7, "capsize": 2})  # fmt: skip
        for yy, v, e in zip(y + (k - 1) * h, g["mean"], g["ci"]):
            ax.text(v + e + 0.015, yy, f"{v:.0%}", va="center", fontsize=8)
    ax.set_yticks(y, [SHORT[label] for label in labels])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.12)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1])
    ax.xaxis.set_major_formatter(plt.matplotlib.ticker.PercentFormatter(1))
    ax.grid(axis="x", alpha=0.3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, legend_y), ncol=3, fontsize=9)


def by_setting(df, col):
    """Mean and 95% interval per model and setting. Repeated samples of the same question are not
    independent, so the interval treats each distinct question as one observation."""
    per_question = df.groupby(["label", "setting", "id"])[col].mean()
    g = per_question.groupby(["label", "setting"]).agg(["mean", "std", "size"])
    g["ci"] = (1.96 * g["std"] / np.sqrt(g["size"])).fillna(0)
    return g.unstack("setting").swaplevel(axis=1)


def fig_safe_choice(df):
    labels = PROMPTED + TRAINED[1:]
    fig, ax = plt.subplots(figsize=(9, 6.2))
    grouped_bars(ax, by_setting(df, "cara"), labels)
    ax.axhline(2.5, color="k", lw=0.8)
    ax.text(1.11, 1.0, "prompted", rotation=270, va="center", ha="center", fontsize=9, color="#555")
    ax.text(1.11, 4.0, "trained", rotation=270, va="center", ha="center", fontsize=9, color="#555")
    ax.set_xlabel("How often the model picks the safe option")
    ax.set_title("Same choice, three settings: how often does each model pick the safe option?")
    fig.text(0.5, -0.04, "100% = always risk-averse.   0% = always takes the long shot "
             "(risk-neutral).\nIn the vignette and environment, a model that always reports or confesses "
             "scores 50%.", ha="center", fontsize=9, color="#444")  # fmt: skip
    fig.tight_layout()
    fig.savefig(OUT / "safe_choice.png", dpi=150, bbox_inches="tight")


def fig_utility(use):
    fig, ax = plt.subplots(figsize=(9, 4.2))
    grouped_bars(ax, by_setting(use[use.label.isin(TRAINED)], "uses"), TRAINED, legend_y=-0.2)
    ax.set_xlabel("Share of answers whose reasoning writes out u(w) = 1 - exp(-0.01w)")
    ax.set_title("How often each model uses its trained utility function")
    fig.tight_layout()
    fig.savefig(OUT / "utility_use.png", dpi=150, bbox_inches="tight")


def fig_variant_split(df, col, filename, title):
    """Normal and mirror rates, with intervals over distinct questions as above."""
    labels = list(ROWS.values())
    deal = df[df.setting != "lottery"]
    per_question = deal.groupby(["label", "setting", "variant", "id"])[col].mean()
    summary = per_question.groupby(["label", "setting", "variant"]).agg(["mean", "std", "size"])
    summary["ci"] = (1.96 * summary["std"] / np.sqrt(summary["size"])).fillna(0)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    y = np.arange(len(labels))
    for ax, setting in zip(axes, ("vignette", "environment")):
        for offset, variant, color in ((-0.19, "normal", "#4c78a8"), (0.19, "mirror", "#f58518")):
            g = summary.xs((setting, variant), level=("setting", "variant")).loc[labels]
            # Clip displayed intervals to the possible range of a rate.
            errors = np.array([np.minimum(g["ci"], g["mean"]),
                               np.minimum(g["ci"], 1 - g["mean"])])
            ax.barh(y + offset, g["mean"], 0.34, xerr=errors, color=color,
                    label=variant.capitalize(), error_kw={"elinewidth": 0.7, "capsize": 2})
            for yy, value, upper in zip(y + offset, g["mean"], errors[1]):
                ax.text(value + upper + 0.015, yy, f"{value * 100:g}%", va="center", fontsize=9)
        ax.set_title("Vignettes (asked)" if setting == "vignette" else "Environment (acts)")
        ax.set_xlim(0, 1.18)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1])
        ax.xaxis.set_major_formatter(plt.matplotlib.ticker.PercentFormatter(1))
        ax.grid(axis="x", alpha=0.25)
        ax.set_axisbelow(True)
        ax.axhline(2.5, color="k", lw=0.6)
        ax.set_xlabel("Reporting rate" if col == "y" else "Safe-choice rate")
    axes[0].set_yticks(y, [SHORT[label] for label in labels])
    axes[0].invert_yaxis()
    fig.suptitle(title)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=2,
               bbox_to_anchor=(0.6, 0.045))
    fig.text(0.6, 0.015, "Normal: reporting is safe.   Mirror: not reporting is safe.",
             ha="center", fontsize=9, color="#444")
    fig.tight_layout(rect=(0, 0.12, 1, 0.96))
    fig.savefig(OUT / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    df = data()
    fig_safe_choice(df)
    fig_variant_split(df, "cara", "safe_choice_by_variant.png", "Safe choices, split by normal and mirror versions")
    use = utility_use()
    fig_utility(use)
    # Vignettes: CARA match when the model does and doesn't write out the utility function.
    vig = df[df.setting == "vignette"].merge(use, on=["label", "setting", "id", "epoch"])
    print(vig.groupby(["label", "uses"]).cara.agg(["mean", "size"]).round(2))
