"""Export both observed choice outcomes for every bar in the safe-choice chart.
Run from any directory: .venv/bin/python export_choice_samples.py
"""
import html
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

from inspect_ai.log import read_eval_log
from analyze import SETTINGS, letter, model_name

ROOT = Path(__file__).resolve().parent
CONFIGS = [
    ('qwen3-14b (vllm)', 'baseline', 'Untrained, no prompt'),
    ('qwen3-14b (vllm)', 'ra_generic', '“Be risk-averse” prompt'),
    ('qwen3-14b (vllm)', 'ra_cara', 'Utility-function prompt'),
    ('qwen3-14b + sft', 'baseline', 'SFT'),
    ('qwen3-14b + dpo', 'baseline', 'DPO'),
    ('qwen3-14b + tie', 'baseline', 'Tie training'),
]
NAMES = {'lottery': 'Plain lottery', 'vignette': 'Vignette', 'environment': 'Environment'}


def blocks(message):
    if isinstance(message.content, str):
        return [('Message', message.content)] if message.content else []
    result = []
    for b in message.content:
        if b.type == 'reasoning':
            result.append(('Logged reasoning', '[Redacted in source]' if b.redacted else b.reasoning))
        elif b.type == 'text':
            result.append(('Response text', b.text))
        else:
            result.append((b.type, '[Non-text content omitted]'))
    return result


def length(row):
    return sum(len(t) for m in row['s'].messages if m.role == 'assistant' for _, t in blocks(m))


def choose(rows):
    """Median-length example, with deterministic tie-breaking."""
    mid = median(length(r) for r in rows)
    return min(rows, key=lambda r: (abs(length(r)-mid), str(r['s'].id), r['s'].epoch, str(r['path'])))


def main():
    groups = defaultdict(list)
    missing = defaultdict(int)
    for path in sorted((ROOT / 'logs/adapters').glob('*.eval')):
        log = read_eval_log(str(path), resolve_attachments=True)
        if log.status != 'success':
            continue
        setting = SETTINGS[log.eval.task.split('/')[-1]]
        key = (model_name(log.eval.model), log.eval.task_args['condition'], setting)
        for s in log.samples:
            score = next(iter(s.scores.values()))
            answer = score.answer if setting == 'environment' else letter(s)
            if answer in (None, '', 'none'):
                missing[key] += 1
                continue
            coop = score.value == 1 if setting == 'environment' else answer == s.target
            safe = coop if setting == 'lottery' else coop == (s.metadata['variant'] == 'normal')
            groups[key].append(dict(s=s, path=path, answer=answer, safe=safe, coop=coop))

    intro = '''# Actual responses on both sides of each choice

This accompanies the safe-choice chart, `figures/safe_choice.png`.
All six configurations are **Qwen3-14B**, evaluated on the same vLLM server; there are no frontier models in this chart.
Each section includes the full recorded prompt, available reasoning, response text, tool calls and tool results for selected episodes. Text is copied from the logs without shortening or correcting it. “Logged reasoning” is model-generated text, not an independently verified explanation of its behavior. No hidden or redacted reasoning is reconstructed.

**How to read the choices:** SAFE is the smaller, more reliable payout; LONG SHOT is the larger, less likely payout with higher expected dollars. “Safe” need not mean guaranteed. In normal deal scenarios SAFE = cooperate/report; in mirror scenarios SAFE = defect/accept the bribe. Thus a safe-choice rate of 50% can mean always cooperating. The lottery scorer's target is safe; the vignette scorer's target is cooperation, so its correctness label alone does not identify safety.

**Selection:** One example per observed outcome for each of 18 chart bars. Prefer an identical question ID with both outcomes across repeated runs, choosing the ID with the most observations on its rarer side (ties by ID). Within each side, choose the response nearest its median assistant-text length (ties by ID and epoch). If no question has both outcomes, select median-length examples from each side across that entire bar. This is a reproducible illustrative selection, not a claim that a trace is statistically representative of all reasoning. Counts show how common each outcome really was. A missing outcome is explicitly marked; no substitute is taken from another run/configuration. Rare counterexamples receive equal space here but not equal statistical weight.

The experiment used five repeated runs per question, at temperature 0.6. Counts below exclude unparsed/no-decision samples, matching the chart. Percentages are unrounded here to distinguish 99% from 100%. See `results.md` for experimental caveats. Source log paths, sample IDs and epochs make every selection traceable.
'''
    out = [intro, '## Coverage\n', '| Configuration | Setting | Safe | Long shot | Safe rate | No decision |\n|---|---|---:|---:|---:|---:|']
    sections = []
    manifest = []
    for model, condition, label in CONFIGS:
        for setting, name in NAMES.items():
            key = (model, condition, setting)
            rows = groups[key]
            assert rows, key
            safe_n = sum(r['safe'] for r in rows)
            out.append(f'| {label} | {name} | {safe_n} | {len(rows)-safe_n} | {safe_n/len(rows):.1%} | {missing[key]} |')
            anchor = f'section-{len(sections)+1}'
            body = [f'## {label} — {name}', f'Model: `{model}`. Condition: `{condition}`. **{safe_n}/{len(rows)} safe ({safe_n/len(rows):.1%}); {len(rows)-safe_n}/{len(rows)} long shot.**']
            by_id = defaultdict(list)
            for r in rows:
                by_id[r['s'].id].append(r)
            paired = [k for k, rs in by_id.items() if {r['safe'] for r in rs} == {True, False}]
            if paired:
                ident = min(paired, key=lambda k: (-min(sum(r['safe'] for r in by_id[k]), sum(not r['safe'] for r in by_id[k])), str(k)))
                pool = by_id[ident]
                body.append('The two examples below answer **the identical question** in different repeated runs.')
            else:
                pool = rows
                body.append('No identical question produced both outcomes; selections use the available outcomes across this configuration and setting.')
            for safe in (True, False):
                side = 'SAFE' if safe else 'LONG SHOT'
                candidates = [r for r in pool if r['safe'] == safe]
                body.append(f'### {side}')
                if not candidates:
                    body.append(f'**No {side} choice was observed among the {len(rows)} valid responses.**')
                    continue
                row = choose(candidates)
                s = row['s']
                meta = s.metadata
                source = row['path'].relative_to(ROOT).as_posix()
                decision = '' if setting == 'lottery' else ('; cooperates/reports' if row['coop'] else '; defects/takes the offer')
                body.append(f"**Observed choice: {row['answer']}{decision}.** Sample `{s.id}`, epoch **{s.epoch}**.\n\nSource: `{source}`.")
                body.append(f"Safe payout: **${meta['payment']:,} at {meta['p_honored']:.0%}** (EV ${meta['payment']*meta['p_honored']:,.0f}); long shot: **${meta['payoff']:,} at {meta['p_success']:.0%}** (EV ${meta['payoff']*meta['p_success']:,.0f}). Otherwise $0. Variant: **{meta.get('variant') or 'lottery'}**; scenario: **{meta.get('family') or 'lottery'}**.")
                if not any(m.role == 'system' for m in s.messages):
                    body.append('**System prompt:** none recorded.')
                for i, m in enumerate(s.messages, 1):
                    body.append(f'#### Message {i}: {m.role}')
                    for kind, text in blocks(m):
                        if text:
                            body.append(f'**{kind}**\n\n```text\n{text}\n```')
                    for call in getattr(m, 'tool_calls', None) or []:
                        body.append(f'**Tool call:** `{call.function}`\n\n```json\n{json.dumps(call.arguments, indent=2, ensure_ascii=False)}\n```')
                manifest.append(dict(configuration=label, setting=setting, side=side, log=source, sample_id=s.id, epoch=s.epoch, answer=row['answer']))
            sections.append((anchor, f'{label} — {name}', '\n\n'.join(body)))
    overview = '\n'.join(out)
    out.extend(['\n## Contents\n']+[f'- [{title}](#{anchor})' for anchor, title, _ in sections])
    out.extend(f'\n<a id="{anchor}"></a>\n\n'+body for anchor, _, body in sections)
    target = ROOT / 'choice_samples.md'
    target.write_text('\n'.join(out)+'\n')
    # Standalone browser copy with collapsible sections and preserved verbatim text.
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>Choice samples</title><style>body{max-width:1050px;margin:40px auto;padding:0 24px;font:17px/1.55 system-ui;color:#202124}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.6 ui-monospace,monospace}summary{cursor:pointer;font-weight:650;padding:18px;background:#edf2f7}details{margin:16px 0;border:1px solid #ddd}details pre{padding:20px}a{color:#155ab6}</style><body>', '<pre>'+html.escape(overview)+'</pre>', '<nav><ol>']
    parts.extend(f'<li><a href="#{a}" onclick="document.getElementById(\'{a}\').open=true">{html.escape(t)}</a></li>' for a,t,_ in sections)
    parts.append('</ol></nav>')
    parts.extend(f'<details id="{a}"><summary>{html.escape(t)}</summary><pre>{html.escape(b)}</pre></details>' for a,t,b in sections)
    parts.append('</body></html>')
    target.with_suffix('.html').write_text('\n'.join(parts))
    target.with_suffix('.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Exported {len(manifest)} samples across {len(sections)} sections to {target}')
    print('\n'.join(out[2:21]))


if __name__ == '__main__':
    main()
