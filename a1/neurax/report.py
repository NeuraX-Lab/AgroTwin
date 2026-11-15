"""Write audit outputs and human-usable reports from evidence-gated assessment."""
from __future__ import annotations
import json
from pathlib import Path
from .core import write_json, timestamp
from .inspect import scan
from .recommend import analyze_fit, build_model_plan, machine_info, research_tasks
from .research import fetch_sources


def report_md(scan,fit,plan):
    lines=['# NeuraX automatic dataset reconnaissance','',f"Generated (UTC): {timestamp()}",
        f"Scope: **{fit['challenge']}**. Mode: **candidate assessment**, not an agronomic validation.",'',
        '## Inventory',f"Inspected {scan['file_count_inspected']} files. {'Limit reached.' if scan['truncated_to_max_files'] else ''}",'',
        '| Path | Kind | Bytes | Inspection |','|---|---|---:|---|']
    for file in scan['files']:
        lines.append(f"| `{file['path'].replace('|','/')}` | {file['kind']} | {file['size_bytes']} | {file['status']} |")
    lines += ['', '## What the files support (candidates; not scientific conclusions)','']
    lines += ['- '+x for x in fit['strengths']]
    lines += ['', '## Missing evidence / blockers','']
    lines += ['- '+x for x in fit['gaps']]
    lines += ['', '## Recommended product direction',
        '**Conditional:** explainable Field Shift crop-rotation decision support if NASA-derived features and Bich-approved agronomic constraints exist.',
        'Do not call a scenario a forecast, label an unlabeled dataset as supervised, or infer field yield or soil health from a single sensor.',
        '', '## Model choice and machine route',
        '- Main: domain rules, constraint filter, weighted ranking. No training needed.',
        '- Optional: one-month rainfall forecast: seasonal-naive then histogram gradient boosting; accept only with time-ordered holdout.',
        f"- Local route: {plan['hardware_route']['primary']}. Cloud fallback: `{plan['hardware_route']['cloud_fallback']}`.",
        f"- Approximate tabular in-memory footprint: {plan['hardware_route']['estimated_tabular_memory_gb']} GB (very rough, not a benchmark).",
        '', '## Team fit / responsibilities','']
    for k,v in fit['owner_assessment'].items():lines.append(f'- **{k}**: {v}')
    lines += ['', '## Critical questions','']
    for q in fit['questions']:lines.append('- '+q)
    lines += ['', '## Outputs','- `inventory.json`: data file metadata and bounded previews',
        '- `fit.json`: Field Shift suitability, missing gates, owner assignments',
        '- `model_plan.json`: candidate models, target/input/output, configs and local/cloud route',
        '- `research_queue.json`: online research queries with primary official URLs',
        '- `online_sources.json`: only if `--online` explicitly requested; results can fail offline',
        '', '_Synthetic data, declared NASA provenance and actual verified measurements are distinct. Human review required._','']
    return '\n'.join(lines)


def run_analysis(data:Path,out:Path,online=False,max_files=500):
    data=Path(data).resolve();out=Path(out).resolve()
    # Avoid recursion scanning output as data.
    if out==data or data in out.parents:raise ValueError('Output directory cannot be nested under the data input directory')
    out.mkdir(parents=True,exist_ok=True)
    inv=scan(data,max_files=max_files)
    fit=analyze_fit(inv,data)
    machine=machine_info()
    plan=build_model_plan(fit,inv,machine)
    research=research_tasks(fit)
    write_json(out/'inventory.json',inv)
    write_json(out/'fit.json',fit)
    write_json(out/'model_plan.json',plan)
    write_json(out/'machine.json',machine)
    write_json(out/'research_queue.json',research)
    (out/'report.md').write_text(report_md(inv,fit,plan),encoding='utf-8')
    if online:
        write_json(out/'online_sources.json',fetch_sources())
    write_json(out/'run_manifest.json',{
        'generated_at':timestamp(),'input_root':str(data),'output_root':str(out),'mode':'inspection_only',
        'online_fetch_opt_in':bool(online),'trained_model':False,'api_running':False,'files':inv['file_count_inspected']})
    return out
