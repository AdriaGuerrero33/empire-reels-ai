"""Empire Reels AI local CLI. Run from backend: python empire.py input.mp4."""
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from app.config import get_settings
from app import media
from app.pipeline.analyze import run_analysis, load_analysis
from app.pipeline.planner import plan_all
from app.render.renderer import render_plan
from app.render.subtitles import srt_from_words
from app.pipeline.styles import STYLE_ORDER

def main():
    parser=argparse.ArgumentParser(description='Empire Reels AI — edición local en español')
    parser.add_argument('video',type=Path)
    parser.add_argument('--duration',default='auto',help='auto or requested clip seconds')
    parser.add_argument('--style',choices=STYLE_ORDER,help='Render only this style')
    parser.add_argument('--preview',action='store_true',help='Low resolution preview')
    parser.add_argument('--analyze-only',action='store_true')
    args=parser.parse_args()
    source=args.video.resolve()
    if not source.is_file():
        parser.error('No se encuentra el vídeo')
    settings=get_settings(); settings.ensure_dirs()
    info=media.describe(source)
    digest=hashlib.sha256()
    with source.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    project=settings.projects_dir/digest.hexdigest()[:16]
    project.mkdir(parents=True,exist_ok=True)
    analysis=load_analysis(project)
    if analysis is None:
        analysis,metrics=run_analysis(project,source,info,'es',lambda value,msg:print(f'{value:.0%} {msg}',flush=True))
        (project/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.analyze_only:
        print(project); return 0
    duration='auto' if args.duration=='auto' else float(args.duration)
    plans,warnings=plan_all(analysis,{'format':'9:16','duration':duration,'brand':{}},info,[args.style] if args.style else None)
    for warning in warnings: print('AVISO:',warning)
    out=project/'renders'; out.mkdir(exist_ok=True)
    results=[]
    for style,plan in plans.items():
        (project/f'plan_{style}.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
        try:
            result=render_plan(plan,analysis['transcript']['words'],source,info,out,style,quality='preview' if args.preview else 'final',on_progress=lambda value:print(f'{style}: {value:.0%}',flush=True))
            (out/f'{style}.srt').write_text(srt_from_words(result['words']),encoding='utf-8')
            results.append({'style':style,'ok':True,'validation':result['validation']})
        except Exception as exc:
            results.append({'style':style,'ok':False,'error':str(exc)})
            print(f'ERROR {style}: {exc}',flush=True)
        (project/'results.json').write_text(json.dumps({'results':results,'warnings':warnings},ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(project/'EmpireReels_resultados.zip','w',zipfile.ZIP_STORED) as archive:
        for result in results:
            if result['ok']:
                for ext in ['mp4','srt']:
                    file=out/f"{result['style']}.{ext}"
                    if file.exists(): archive.write(file,file.name)
    print(f"{sum(r['ok'] for r in results)}/{len(results)} correctos. Carpeta: {project}")
    return 0 if all(r['ok'] for r in results) else 1

if __name__=='__main__':
    raise SystemExit(main())

