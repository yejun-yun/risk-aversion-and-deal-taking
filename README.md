# Risk aversion and deal-taking

Does risk aversion make language models take safer deals? Experiments compare prompted Qwen3-14B and RiskAverseOOD adapters on lotteries, vignettes, and tool-based decisions.

[Results](results/README.md) · [Experiment design](docs/experiment.md) · [Prompts](docs/prompts.md) · [Response samples](results/samples/choice_samples.md)

## Run

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13+.

```bash
uv sync
cp .env.example .env  # add OPENROUTER_API_KEY
./scripts/run.sh
```

For the paper's adapters, authenticate with Modal and run:

```bash
uv run --with modal==1.1.0 modal token new
./scripts/run_adapters.sh
```

Runs incur API or GPU charges. Raw logs are not included; new runs save to `logs/`.

```bash
uv run python analysis/analyze.py
uv run python analysis/figures.py
```

## Files

| Folder | Contents |
|---|---|
| `experiments/` | Vignette, agent, lottery, and paper-validation tasks |
| `data/` | Scenario definitions |
| `scripts/` | Evaluation runners |
| `serving/` | Modal model server |
| `analysis/` | Analysis, plotting, and sample export |
| `docs/` | Experiment design and prompts |
| `results/` | Findings, figures, and response samples |
