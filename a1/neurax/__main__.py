"""CLI: python -m neurax {doctor,analyze,watch,train,serve}."""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path


def main(argv=None):
    p=argparse.ArgumentParser(prog='neurax',description='Local-first scientific data triage and research workflow')
    subs=p.add_subparsers(dest='command',required=True)
    a=subs.add_parser('analyze',help='Drop datasets into data/raw; generate read-only inventory, QA cues and recommendations')
    a.add_argument('--data',default='data/raw');a.add_argument('--out',default='runs/latest')
    a.add_argument('--max-files',type=int,default=500);a.add_argument('--online',action='store_true',
                    help='Opt in to reading 3 allowlisted public documentation URLs only; never upload data')
    g=subs.add_parser('go',help='One-command data scan + optional NASA POWER D1 + gate-checked training')
    g.add_argument('--data',default='data/raw');g.add_argument('--out',default='runs/latest')
    g.add_argument('--online',action='store_true');g.add_argument('--auto-train',action='store_true')
    g.add_argument('--power-input',default=None);g.add_argument('--region-id',default=None)
    w=subs.add_parser('watch',help='Poll directory and re-analyze when files change; Ctrl-C to stop')
    w.add_argument('--data',default='data/raw');w.add_argument('--out',default='runs/latest')
    w.add_argument('--interval',type=int,default=10)
    t=subs.add_parser('train',help='Train/evaluate optional 1-month rainfall forecast')
    t.add_argument('--input',required=True);t.add_argument('--out',default='runs/latest/forecast')
    t.add_argument('--target',default='precip_sum_mm');t.add_argument('--date-column',default='period_start')
    t.add_argument('--region',default=None)
    n=subs.add_parser('normalize-power',help='Convert NASA POWER daily CSV/JSON to provenance-aware monthly D1')
    n.add_argument('--input',required=True);n.add_argument('--region-id',required=True)
    n.add_argument('--out',default='data/processed/D1');n.add_argument('--source-manifest',default=None)
    ai=subs.add_parser('ai',help='AI-led investigation: scan data, let a local/opt-in remote LLM examine reports and call safe tools')
    ai.add_argument('--data',default='data/raw');ai.add_argument('--out',default='runs/latest')
    ai.add_argument('--model',default=os.getenv('NEURAX_LLM_MODEL',''))
    ai.add_argument('--base-url',default=os.getenv('NEURAX_LLM_BASE_URL','http://127.0.0.1:11434/v1'))
    ai.add_argument('--allow-remote',action='store_true',help='Explicitly allow sending bounded metadata to a remote LLM')
    ai.add_argument('--share-rows',action='store_true',help='Allow sending up to 5 rows of selected tables to the configured LLM')
    ai.add_argument('--web',action='store_true',help='Allow Crossref bibliographic lookup and bounded official technical page reads')
    ai.add_argument('--steps',type=int,default=8)
    ai.add_argument('--project-docs',default=None,help='Optional local checkout path for current NeuraX docs')
    native=subs.add_parser('finalize-native',help='Validate Codex/Antigravity drafted decision JSON without any LLM request')
    native.add_argument('--candidate',required=True,help='Agent-produced JSON candidate inside the run directory')
    native.add_argument('--run-dir',default='runs/latest')
    bundle=subs.add_parser('bundle',help='Build an immutable read-only evidence snapshot; no ranking or training')
    bundle.add_argument('--run-dir',required=True)
    bundle.add_argument('--coverage-dir',required=True)
    bundle.add_argument('--review-dir',required=True)
    bundle.add_argument('--case-dir',required=True)
    bundle.add_argument('--out',required=True)
    bundle.add_argument('--year',type=int,default=2025)
    check_bundle=subs.add_parser('validate-bundle',help='Check snapshot integrity and inspection boundaries, not scientific approval')
    check_bundle.add_argument('--bundle-dir',required=True)
    a1=subs.add_parser('agrotwin',help='Compute an evidence-gap A1 run; never invent crop approval')
    a1.add_argument('--input',help='AnalysisInput JSON; omit for the cached My Thanh study case')
    a1.add_argument('--out',default='runs/agrotwin')
    d=subs.add_parser('doctor',help='Check hardware and optional readers')
    s=subs.add_parser('serve',help='Start localhost API (FastAPI/uvicorn required)')
    s.add_argument('--host',default='127.0.0.1');s.add_argument('--port',type=int,default=8000)
    s.add_argument('--run-dir',default='runs/latest')
    args=p.parse_args(argv)
    if args.command=='agrotwin':
        from .agrotwin.inputs import AnalysisInput
        from .agrotwin.data import load
        from .agrotwin.service import analyze
        body=json.loads(Path(args.input).read_text(encoding='utf-8')) if args.input else {
            'aoi_id':'MT-BLOCK-01','geometry':load('case.json')['geometry'],
            'period':{'start':'2025-01-01','end':'2026-01-01'},'source_mode':'offline','farm':{}}
        print(json.dumps(analyze(AnalysisInput.model_validate(body),Path(args.out)),ensure_ascii=False,indent=2));return 0
    if args.command=='validate-bundle':
        from .evidence_bundle import validate_evidence_bundle
        print(json.dumps(validate_evidence_bundle(Path(args.bundle_dir)),ensure_ascii=False,indent=2));return 0
    if args.command=='bundle':
        from .evidence_bundle import build_evidence_bundle
        result=build_evidence_bundle(Path(args.run_dir),Path(args.coverage_dir),Path(args.review_dir),
                                     Path(args.case_dir),Path(args.out),args.year)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    if args.command=='finalize-native':
        from .native_review import finalize_native_decision
        result=finalize_native_decision(Path(args.candidate),Path(args.run_dir))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    if args.command=='ai':
        from .ai_agent import CompatibleLLM, run_ai_review
        client=CompatibleLLM(args.model,args.base_url,os.getenv('NEURAX_LLM_API_KEY'),
                             allow_remote=args.allow_remote)
        result=run_ai_review(Path(args.data),Path(args.out),client,
                            allow_rows=args.share_rows,allow_web=args.web,steps=args.steps,
                             project_docs=Path(args.project_docs) if args.project_docs else None)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    if args.command=='normalize-power':
        from .normalize import normalize_power
        output=normalize_power(Path(args.input),args.region_id,Path(args.out),Path(args.source_manifest) if args.source_manifest else None)
        print(json.dumps(output,ensure_ascii=False,indent=2));return 0
    if args.command=='doctor':
        from .recommend import machine_info
        from importlib.util import find_spec
        print(json.dumps({'hardware':machine_info(),'readers':{x:find_spec(x) is not None for x in
           ['pandas','openpyxl','pyarrow','xarray','rasterio','fiona','h5py','pypdf','docx','pptx','sklearn','fastapi','uvicorn']}},
           ensure_ascii=False,indent=2));return 0
    if args.command=='go':
        from .report import run_analysis
        from .core import write_json,timestamp
        from .normalize import normalize_power
        from .train import train_forecast
        root=Path(args.data).resolve();dest=Path(args.out).resolve()
        run_analysis(root,dest,online=args.online)
        summary={'generated_at':timestamp(),'scan':'complete','normalize':'not_requested','train':'not_requested',
                 'training_metrics':None,'caution':'Auto training alone does not establish scientific validity; independently review QA, provenance and crop constraints.'}
        candidate=None
        if args.power_input:
            if not args.region_id:raise ValueError('--region-id is required with --power-input to prevent invented AOI')
            power_path=Path(args.power_input).resolve()
            if not power_path.is_relative_to(root):raise ValueError('--power-input must be located under --data')
            source=root/'_source.json'
            manifest=normalize_power(power_path,args.region_id,dest/'D1',source if source.exists() else None)
            candidate=dest/'D1'/'features.csv'
            summary['normalize']='complete';summary['normalized_months']=manifest['n_months']
            # Data is not silently relabeled as verified even if downloadable from an official API.
            write_json(dest/'D1'/'README-report.json',{'warning':manifest['warnings'],'source_verification':manifest['source_metadata'].get('verification_status','unknown')})
        if args.auto_train:
            if candidate is None:
                possible=[]
                for pth in root.rglob('*.csv'):
                    if pth.is_symlink() or pth.stat().st_size>200*1024*1024:continue
                    try:
                        with pth.open(encoding='utf-8-sig') as f:headers=f.readline().strip().split(',')
                        if {'period_start','precip_sum_mm'}.issubset(headers):possible.append(pth)
                    except (OSError,UnicodeError):pass
                if len(possible)==1:candidate=possible[0]
                else:summary['train']='skipped: '+('no canonical monthly CSV found' if not possible else 'multiple candidates: operator selection required')
            if candidate:
                try:
                    # Observed data needs evidence; otherwise analyze only, never silently treat as validated.
                    source_path=root/'_source.json'
                    if source_path.exists():
                        import json as _json
                        meta=_json.loads(source_path.read_text(encoding='utf-8'))
                        if meta.get('data_mode')=='observed' and meta.get('verification_status')!='verified':
                            raise ValueError('Observed data source is not verified; validate _source.json first.')
                    metrics=train_forecast(candidate,dest/'forecast',region=args.region_id)
                    summary['train']='complete (candidate evaluated)';summary['training_metrics']=metrics['metrics']
                    summary['selected_method']=metrics['model']
                except (ValueError,FileNotFoundError) as ex:summary['train']='skipped: '+str(ex)
        write_json(dest/'go_summary.json',summary)
        print(_json_dumps(summary));print('Report: '+str(dest/'report.md'))
        return 0
    if args.command=='analyze':
        from .report import run_analysis
        folder=run_analysis(Path(args.data),Path(args.out),online=args.online,max_files=args.max_files)
        print('Generated: '+str(folder));print('Read report: '+str(folder/'report.md'));return 0
    if args.command=='watch':
        if args.interval<2:p.error('--interval must be >=2 seconds')
        from .report import run_analysis
        root=Path(args.data);previous=None
        print('Watching '+str(root.resolve())+' (no remote uploads; Ctrl-C to stop)')
        try:
            while True:
                snap=tuple(sorted((p.relative_to(root).as_posix(),p.stat().st_size,p.stat().st_mtime_ns)
                    for p in root.rglob('*') if p.is_file() and not p.is_symlink() and not p.name.startswith('.')))
                if snap!=previous:
                    # Two observations for file stability, to avoid inspecting partially copied datasets.
                    time.sleep(min(2,args.interval))
                    again=tuple(sorted((p.relative_to(root).as_posix(),p.stat().st_size,p.stat().st_mtime_ns)
                        for p in root.rglob('*') if p.is_file() and not p.is_symlink() and not p.name.startswith('.')))
                    if snap==again:
                        run_analysis(root,Path(args.out)); print('Re-analyzed at '+time.strftime('%H:%M:%S'));previous=snap
                time.sleep(args.interval)
        except KeyboardInterrupt:print('Stopped.');return 0
    if args.command=='train':
        from .train import train_forecast
        result=train_forecast(Path(args.input),Path(args.out),target=args.target,date_col=args.date_column,region=args.region)
        print(json.dumps({'output':str(args.out),'evaluation':result},ensure_ascii=False,indent=2));return 0
    if args.command=='serve':
        import uvicorn
        os.environ['NEURAX_RUN_DIR']=str(Path(args.run_dir).resolve())
        uvicorn.run('neurax.api:app',host=args.host,port=args.port,log_level='info');return 0
    return 1

def _json_dumps(x):
    return json.dumps(x,ensure_ascii=False,indent=2)

if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,FileNotFoundError,FileExistsError) as ex:
        print(f'ERROR: {ex}',file=sys.stderr);sys.exit(2)
