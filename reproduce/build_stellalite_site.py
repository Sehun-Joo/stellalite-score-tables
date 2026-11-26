"""Lock ranges on the full fitted pool, then choose 20 by archived total plays."""
from pathlib import Path
import gzip,hashlib,json,re,shutil,zipfile
from stellalite_ranges import stage_groups
ROOT=Path(__file__).resolve().parent;MODEL=ROOT/'stellalite';SOURCE=ROOT/'publish'/'bms-98-table';SITE=ROOT/'publish'/'stellalite-score-tables'
BASE='https://sehun-joo.github.io/stellalite-score-tables/'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
SITE.mkdir(exist_ok=True);meta={r['md5']:r for r in read(MODEL/'model-metadata.json')};cohort=read(MODEL/'cohort.json');targets={}
for slug,label,num,den,code in [('98','98%',98,100,'D98'),('aaa','AAA',8,9,'DAAA'),('max-minus','MAX−',17,18,'DMAX−')]:
    path='' if slug=='98' else slug+'/';dest=SITE/path;dest.mkdir(exist_ok=True)
    pool=read(MODEL/(slug+'-rankings.json'))
    groups,tail=stage_groups(pool)
    # Cut specification is persisted BEFORE any popularity selection takes place.
    cuts=[dict(id=f'{i:03}',lower_inclusive=lo,upper_exclusive=hi,candidates=len(g)) for i,(lo,hi,g) in enumerate(groups,1)]
    dump(dest/'range-cuts.json',dict(base_step=.155,tail_start=tail,method='Full-pool ability ranges, gap snapping, smooth upper-tail widening; computed before popularity selection',ranges=cuts))
    folders=[];rows=[];data=[];native=[]
    for cut,(_,_,group) in zip(cuts,groups):
        key=cut['id'];lo,hi=cut['lower_inclusive'],cut['upper_exclusive'];tag=f'{key} | {lo:.3f}–{hi:.3f}'
        for r in group:r.update(folder=key,folder_range=tag)
        selected=sorted(group,key=lambda r:(-r['total_plays'],-r['total_players'],r['md5']))[:20]
        folders.append(dict(id=key,label=tag,lower_inclusive=lo,upper_exclusive=hi,count=len(selected),candidates=len(group),provisional=sum(r['status']=='provisional' for r in selected)))
        songs=[]
        for pos,r in enumerate(selected,1):
            r['popularity_rank']=pos;rows.append(r);m=meta[r['md5']]
            e={k:m[k] for k in ['md5','sha256','title','artist','url','url_diff'] if m.get(k)}
            e.update(level=tag,comment=f'{label}: {code}={r["difficulty"]:.4f}; {r["total_plays"]:,} archived plays; popularity #{pos} in range; original {r["original_level"]}; {r["status"]}')
            data.append(e);songs.append({k:e[k] for k in ['md5','sha256','title','artist'] if k in e})
        native.append(dict(name=f'SL{code} {tag} ({len(selected)})',songs=songs))
    selected_hashes={r['md5'] for r in rows}
    for r in pool:r['selected']=r['md5'] in selected_hashes
    header=dict(name=f'Stellalite {label} — most-played scoring stages',symbol='SL'+code+' ',data_url='data.json',level_order=[f['label'] for f in folders])
    for name,value in [('header.json',header),('data.json',data),('rankings.json',rows),('all-rankings.json',pool),('folders.json',folders)]:dump(dest/name,value)
    native_name=f'stellalite-{slug}.bmt'
    with gzip.open(dest/native_name,'wt',encoding='utf-8') as f:json.dump(dict(name=header['name'],url=BASE+path,tag='SL'+code,folder=native,course=[]),f,ensure_ascii=False)
    shutil.copy2(MODEL/(slug+'-validation.json'),dest/'validation.json')
    targets[slug]=dict(id=slug,label=label,numerator=num,denominator=den,code=code,path=path,native=native_name,validation='validation.json',rows=rows,folders=folders,provisional=sum(r['status']=='provisional' for r in rows),zero_success=sum(r['achieved']==0 for r in rows),pool_count=len(pool))
    print(slug,len(rows),'selected;',len(folders),'ranges;',sum(len(g)<20 for _,_,g in groups),'ranges below 20',flush=True)
payload=json.dumps(targets,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
for slug,t in targets.items():
    page=(SOURCE/t['path']/'index.html').read_text(encoding='utf-8')
    start=page.index('const targets=');end=page.index(', defaultTarget=',start);page=page[:start]+'const targets='+payload+page[end:]
    page=page.replace('https://sehun-joo.github.io/bms-98-table/',BASE).replace('https://github.com/Sehun-Joo/bms-98-table','https://github.com/Sehun-Joo/stellalite-score-tables')
    page=page.replace('Insane BMS ·','Stellalite ·').replace('BMS / INSANE / SCORE DIFFICULTY','BMS / STELLA + SATELLITE / SCORE PRACTICE').replace('not ★ levels','not original sl/st levels')
    page=page.replace('Pick a score goal. Find your next chart.','Pick a goal. Practice the most-played charts.')
    page=page.replace('Each goal has its own player-adjusted difficulty ranking.',f'Up to 20 charts per fixed difficulty range, chosen and sorted by archived total plays. Ranges are determined from all {cohort["charts"]:,} eligible charts before selection. Each goal has its own player-adjusted difficulty ranking.')
    page=page.replace('<strong>1,035</strong><span>charts per goal</span>','<strong id="chart-total"></strong><span>selected charts</span>')
    page=page.replace("'All folders · 1,035 charts'","`All folders · ${t.rows.length} charts`")
    page=page.replace("$('folder-total').textContent", "$('chart-total').textContent=t.rows.length.toLocaleString();$('folder-total').textContent")
    page=page.replace('${f.label} · ${f.count} charts','${f.label} · ${f.count} / ${f.candidates} charts')
    page=page.replace('<th>RANK</th>','<th>POPULARITY</th>').replace('<th>PLAYS / PLAYER</th>','<th>TOTAL PLAYS</th>')
    page=page.replace('[r.rank,r.title,','[r.popularity_rank,r.title,').replace("'★'+r.original_level","r.original_level").replace('r.plays_per_player.toFixed(1)','r.total_plays.toLocaleString()')
    page=page.replace(' · ${f.provisional} provisional in this folder',' · ${f.candidates} eligible in range · ${f.provisional} provisional · sorted by total plays')
    page=re.sub(r'<details>.*?</details>','<details><summary>How these tables work</summary><p>AAA = 8/9 EX; MAX− = 17/18 EX; 98% = 98/100 EX. Ranges are ordered by fitted difficulty. Each range contains at most 20 charts, ordered by total archived LR2IR play count, including repeated plays. A range with fewer than 20 eligible charts stays smaller; charts are never pulled across a boundary to fill it.</p><p>These are May 2026 popularity counts, not current counts or unique-player counts. Selection favors frequently played charts and does not correct practice bias. Unsupported target estimates are marked provisional. The models were fitted to the full eligible pool, before popularity selection.</p><p><a href="METHOD_LINK">Coverage, methods and validation</a> · <a href="ZIP_LINK">Download all three tables</a></p></details>',page,flags=re.S)
    prefix='../' if t['path'] else ''
    page=page.replace('METHOD_LINK',prefix+'score-targets.html').replace('ZIP_LINK',prefix+'stellalite-score-tables.zip')
    page=page.replace('All original chart hashes retained.','Current Stella + Satellite membership, archived LR2IR scores.')
    (SITE/t['path']/'index.html').write_text(page,encoding='utf-8')
dump(SITE/'targets.json',{k:{a:b for a,b in t.items() if a not in ['rows','folders']} for k,t in targets.items()})
for src,dest in [('model-excluded.json','excluded-charts.json'),('cohort.json','coverage.json'),('extraction-audit.json','extraction-audit.json'),('sl-source.json','satellite-source.json'),('st-source.json','stella-source.json')]:shutil.copy2(MODEL/src,SITE/dest)
comparisons=[]
for slug,t in targets.items():
    v=read(MODEL/(slug+'-validation.json'));n=v['near_target'];comparisons.append(f'<tr><td>{t["label"]}</td><td>{v["evaluation_records"]:,}</td><td>{v["near_target_records"]:,}</td><td>{n["target_specific"]["log_loss"]:.4f}</td><td>{n["score_curve"]["log_loss"]:.4f}</td><td>{n["raw_rate"]["log_loss"]:.4f}</td></tr>')
notes=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stellalite methods</title><style>body{{font:17px/1.6 system-ui;max-width:1000px;margin:40px auto;padding:0 22px;background:#10151e;color:#e7ebf2}}a{{color:#87c5ff}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #364153}}.scroll{{overflow:auto}}</style><a href="index.html">← Tables</a><h1>Stellalite: difficulty ranges first, popularity second</h1><p>Membership comes from the official <a href="https://stellabms.xyz/sl/table.html">Satellite</a> and <a href="https://stellabms.xyz/st/table.html">Stella</a> tables, fetched 26 November 2026. Score and total-play data come from the <a href="https://github.com/zkldi/lr2ir-dataset">29 May 2026 LR2IR archive</a>.</p><p>{cohort['source_charts']:,} current charts → {cohort['charts']:,} modeled charts, {cohort['players']:,} players, {cohort['pbs']:,} comparable personal bests. {cohort['excluded']:,} charts lacked archive coverage or sufficient comparable scores. See <a href="excluded-charts.json">all exclusions and reasons</a>. Counts are for charts, so different charts of one song can appear.</p><h2>Model and evidence</h2><p>One PB per player/chart; exclude zero/invalid/flagged scores, flagged users, assist options and nonmodal maximum scores. Players need at least 10 extracted charts; retained charts need at least 30 usable PBs after that player filter. A robust regularized full-score model estimates player ability and chart response. Separate regularized logistic fits estimate each target's 50% historical-PB achievement threshold. The three targets are AAA = 8/9, MAX− = 17/18 and 98% = 98/100, tested with exact integer arithmetic.</p><p>The scale is fitted separately to this Stella + Satellite cohort; its numbers should not be compared directly with the Insane tables. Popularity is not used to fit difficulty. Practice exposure, old scores and personal strengths remain confounders; predictions are not next-attempt success probabilities. Provisional means fewer than 100 PBs, fewer than five successes or misses, or fewer than 30 players within one ability unit of the fitted threshold.</p><h2>Predetermined cuts and selection</h2><p>For each target, first calculate every boundary from the full eligible difficulty distribution and save it in range-cuts.json. Use the same progression rule as the finer Insane edition: 0.155 ability-unit base steps; snap a boundary within ±20% of its step toward the largest nearby adjacent-score gap of at least 0.01. Above the full pool's 90th percentile, widen steps smoothly by a factor of 1 + 0.6 × (nominal lower boundary − tail start). Empty ranges are omitted. This is a practice-design heuristic, not a learned human training curve. Bounds include the lower value and exclude the upper value; displayed bounds are rounded.</p><p>Only after fixing those ranges, sort each range by total archived chart play_count descending and keep its first 20 charts. Ties use unique-player count descending, then MD5. Never move boundaries or borrow charts to reach 20. Display and export follow the same popularity order within each difficulty range. Each target provides all-rankings.json with the entire modeled pool and selection flags, and rankings.json with selected charts.</p><h2>Held-out-player validation</h2><p>80% of players train the chart models. For held-out players, half their records estimate ability and half are evaluated, requiring at least five reference charts. The near-target subset uses training-only score-model parameters. Scores below are log loss; lower is better. Evaluation covers the eligible pool before popularity selection. This is a fixed split, not a guarantee of future performance.</p><div class="scroll"><table><tr><th>Goal</th><th>Evaluation PBs</th><th>Near-target PBs</th><th>Target model</th><th>Full-score curve</th><th>Raw success rate</th></tr>{''.join(comparisons)}</table></div><p><a href="stellalite-score-tables.zip">Complete offline package</a>. Each top-level goal link opens a distinct importable URL. Native .bmt files are offered on each page. No song files are distributed. The existing Insane sites remain unchanged.</p></html>'''
(SITE/'score-targets.html').write_text(notes,encoding='utf-8')
(SITE/'README.md').write_text('''# Stellalite scoring practice tables

Stella + Satellite, independently ranked for AAA (8/9), MAX− (17/18), and 98%.

https://sehun-joo.github.io/stellalite-score-tables/

Difficulty ranges are set using the entire eligible pool first. Each range then contains up to 20 charts by archived LR2IR total plays, displayed in descending popularity order. Sparse ranges stay smaller. See score-targets.html for coverage, exclusions, exact boundaries, model validation and limitations.

Distinct import URLs: root for 98%, aaa/ for AAA, max-minus/ for MAX−. No song files or player-level records are included. Original chart identifiers and links are retained; no blanket license is claimed over third-party metadata.

Reproduction scripts expect the original workspace layout and the local lr2ir-archive-v3.db. Python model dependencies: NumPy and SciPy. Snapshot manifests are included. Run fit_stellalite.py, then build_stellalite_site.py; its HTML template is from the original bms-98-table repository.
''',encoding='utf-8')
(SITE/'.nojekyll').write_text('');(SITE/'.gitattributes').write_text('* -text\n')
(SITE/'reproduce').mkdir(exist_ok=True)
for name in ['fit_stellalite.py','stellalite_ranges.py','build_stellalite_site.py','build_table.py','fit_target_separable.py','test_stellalite_site.py','test_stellalite_ui.cjs']:shutil.copy2(ROOT/name,SITE/'reproduce'/name)
files=[p for p in SITE.rglob('*') if p.is_file() and '.git' not in p.parts and p.suffix!='.zip' and p.name!='checksums.json']
dump(SITE/'checksums.json',{p.relative_to(SITE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
with zipfile.ZipFile(SITE/'stellalite-score-tables.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in files+[SITE/'checksums.json']:z.write(p,Path('stellalite-score-tables')/p.relative_to(SITE))
shutil.copy2(SITE/'stellalite-score-tables.zip',ROOT.parent/'outputs'/'stellalite-score-tables.zip')
