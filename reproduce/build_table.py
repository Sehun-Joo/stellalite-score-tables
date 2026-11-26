"""Reproducible LR2IR 98% table build. Requires numpy/scipy; reads source DB only."""
from pathlib import Path
import argparse, collections, gzip, hashlib, html, json, math, sqlite3, time
import numpy as np
from scipy.special import ndtr, expit
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent

def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def extract(db):
    table = json.loads((ROOT/'insane-data.json').read_text(encoding='utf-8-sig'))
    con = sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro', uri=True)
    blocks=[]; audit=collections.Counter(); metadata=[]; options=collections.Counter()
    for j, row in enumerate(table):
        md5=row['md5'].lower()
        c=con.execute('SELECT title,artist,keys,judge_rank,play_count,play_people FROM chart WHERE md5=?',(md5,)).fetchone()
        metadata.append(dict(row, title=c[0] if c else row['title'], artist=c[1] if c else row.get('artist',''),total_plays=c[4] if c else 0,total_players=c[5] if c else 0))
        rs=con.execute('SELECT player_id,score,score_max,is_cheated,option_1,option_2,input FROM pb WHERE md5=?',(md5,)).fetchall()
        audit['raw_rows']+=len(rs)
        valid=[]
        for pid,s,m,cheat,o1,o2,inp in rs:
            options[str((o1,o2,inp))]+=1
            if cheat or m<=0 or s<=0 or s>m:
                audit['invalid_or_cheated_or_zero']+=1; continue
            # LR2 assist scores cannot be compared to normal seven-key EX scores.
            opts=(str(o1)+' '+str(o2)).upper()
            if any(x in opts for x in ['AUTO','5KEY','9KEY','BATTLE']):
                audit['assist']+=1; continue
            valid.append((pid,s,m))
        if valid:
            mode=collections.Counter(v[2] for v in valid).most_common(1)[0][0]
            for pid,s,m in valid:
                if m != mode:
                    audit['nonmodal_max_score']+=1; continue
                blocks.append((pid,j,s,m))
        if (j+1)%100==0: print('Extracted',j+1,flush=True)
    a=np.asarray(blocks,dtype=np.int64)
    np.savez_compressed(ROOT/'observations.npz', rows=a)
    dump(ROOT/'metadata.json',metadata); dump(ROOT/'data-audit.json',dict(audit))
    dump(ROOT/'option-counts.json',dict(options.most_common()))
    print('Extraction',dict(audit),'retained',len(a),flush=True)

def latent(p,j,t,P,J,iterations=180,variable=True):
    """Ridge ALS, positive chart slopes, Huber IRLS against abandoned/stale PBs.
    Player scale standardized after every iteration; chart slopes share a prior.
    """
    count=np.bincount(j,minlength=J)
    mu=np.bincount(j,weights=t,minlength=J)/np.maximum(count,1)
    a=np.full(J,0.65); theta=np.zeros(P); w=np.ones(len(t))
    for it in range(iterations):
        old=theta.copy()
        den=np.bincount(p,weights=w*a[j]**2,minlength=P)+0.5
        theta=np.bincount(p,weights=w*a[j]*(t-mu[j]),minlength=P)/den
        center=theta.mean(); scale=max(theta.std(),0.01)
        theta=(theta-center)/scale
        mu+=a*center; a*=scale
        sw=np.bincount(j,weights=w,minlength=J)
        sx=np.bincount(j,weights=w*theta[p],minlength=J)
        sy=np.bincount(j,weights=w*t,minlength=J)
        sxx=np.bincount(j,weights=w*theta[p]**2,minlength=J)
        sxy=np.bincount(j,weights=w*theta[p]*t,minlength=J)
        prior=float(np.median(a[count>20]))
        if variable:
            a=np.clip((sxy-sx*sy/np.maximum(sw,1)+20*prior)/(sxx-sx*sx/np.maximum(sw,1)+20),0.08,3)
        else:
            shared=np.sum(sxy-sx*sy/np.maximum(sw,1))/max(np.sum(sxx-sx*sx/np.maximum(sw,1)),1)
            a[:]=max(shared,0.08)
        mu=(sy-a*sx)/np.maximum(sw,1)
        resid=t-mu[j]-a[j]*theta[p]
        w=np.minimum(1,0.65/np.maximum(abs(resid),1e-8))
        delta=float(np.max(abs(theta-old)))
        if it%25==0: print('ALS',variable,it,'delta',round(delta,6),flush=True)
        if it>10 and delta<1e-4: break
    # Empirical residual variance (including tails), shrunk to population variance.
    r=t-mu[j]-a[j]*theta[p]
    variance=(np.bincount(j,weights=r*r,minlength=J)+30*np.mean(r*r))/(count+30)
    return theta,mu,a,np.sqrt(variance),it+1

def target_fit(theta,mu,a,p,j,y,J,target_fraction=.98):
    """Target-specific logistic calibration, with slopes/thresholds regularized
    toward the full-score latent model. Weakly supported thresholds are provisional.
    """
    b0=(-math.log1p(-target_fraction)-mu)/a
    slope0=np.clip(a/0.4,0.25,8)
    x=theta[p]
    def fg(z):
        b=z[:J]; loga=z[J:]; aa=np.exp(loga)
        eta=aa[j]*(x-b[j]); err=expit(eta)-y
        loss=np.logaddexp(0,eta).sum()-np.dot(y,eta)
        loss+=.5*np.sum(((b-b0)/1.0)**2)+.5*np.sum(((loga-np.log(slope0))/.5)**2)
        gb=np.bincount(j,weights=-err*aa[j],minlength=J)+(b-b0)
        ga=np.bincount(j,weights=err*eta,minlength=J)+(loga-np.log(slope0))/.25
        return loss,np.r_[gb,ga]
    fit=minimize(fg,np.r_[b0,np.log(slope0)],jac=True,method='L-BFGS-B',
                 bounds=[(-15,50)]*J+[(math.log(.1),math.log(12))]*J,
                 options={'maxiter':350,'ftol':1e-10})
    print(f'{100*target_fraction:.4f}% calibration',fit.success,fit.message,flush=True)
    if not fit.success: raise RuntimeError('Calibration failed to converge: '+str(fit.message))
    return fit.x[:J],np.exp(fit.x[J:])

def metrics(y,prob):
    q=np.clip(prob,1e-8,1-1e-8)
    return {'log_loss':float(-np.mean(y*np.log(q)+(1-y)*np.log1p(-q))),
            'brier':float(np.mean((q-y)**2)),'actual_rate':float(y.mean()),'predicted_rate':float(q.mean())}

def build(out):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    meta=json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
    rows=np.load(ROOT/'observations.npz')['rows']; J=len(meta)
    # Exclude accounts with too little overlap to separate their skill from charts.
    ids,cnt=np.unique(rows[:,0],return_counts=True)
    rows=rows[np.isin(rows[:,0],ids[cnt>=10])]
    ids,p=np.unique(rows[:,0],return_inverse=True); P=len(ids)
    j=rows[:,1]; y=(100*rows[:,2]>=98*rows[:,3]).astype(float)
    # Half-EX continuity correction handles perfect scores without infinity.
    t=-np.log((rows[:,3]-rows[:,2]+.5)/(rows[:,3]+.5))
    rng=np.random.default_rng(980012); train=rng.random(len(p))>=.15; test=~train
    report={'players':P,'observations':len(p),'charts':J,'holdout':int(test.sum()),'models':{}}
    fitted={}; predictions={}
    for variable,label in [(False,'shared_slope'),(True,'chart_slopes')]:
        theta,mu,a,sigma,it=latent(p[train],j[train],t[train],P,J,variable=variable)
        pr=ndtr((mu[j[test]]+a[j[test]]*theta[p[test]]+math.log(.02))/sigma[j[test]])
        report['models'][label]=metrics(y[test],pr)
        predictions[label]=pr
        fitted[label]=(theta,mu,a,sigma)
    theta,mu,a,sigma=fitted['chart_slopes']
    b98,a98=target_fit(theta,mu,a,p[train],j[train],y[train],J)
    pr=expit(a98[j[test]]*(theta[p[test]]-b98[j[test]]))
    report['models']['target98']=metrics(y[test],pr)
    predictions['target98']=pr
    # Near-target subgroup defined using training-only skill and chart estimates.
    near=abs(theta[p[test]]-(-math.log(.02)-mu[j[test]])/a[j[test]])<1
    report['near_target_holdout']=int(near.sum())
    if near.any(): report['target98_near_target']=metrics(y[test][near],pr[near])
    n=np.bincount(j[train],minlength=J); wins=np.bincount(j[train],weights=y[train],minlength=J)
    report['models']['raw_rate']=metrics(y[test],((wins+.5)/(n+1))[j[test]])
    predictions['raw_rate']=((wins+.5)/(n+1))[j[test]]
    report['near_target_models']={name:metrics(y[test][near],prob[near]) for name,prob in predictions.items()} if near.any() else {}
    candidates=['shared_slope','chart_slopes','target98']
    selection=report['near_target_models'] if near.sum()>=500 else report['models']
    chosen=min(candidates,key=lambda k:selection[k]['log_loss'])
    report['selection_metric']='near-target log loss' if near.sum()>=500 else 'overall log loss'
    report['chosen']=chosen
    dump(ROOT/'validation.json',report); print(json.dumps(report,indent=2),flush=True)
    theta,mu,a,sigma,it=latent(p,j,t,P,J,variable=chosen!='shared_slope')
    difficulty=(-math.log(.02)-mu)/a
    if chosen=='target98': difficulty,a98=target_fit(theta,mu,a,p,j,y,J)
    n=np.bincount(j,minlength=J); wins=np.bincount(j,weights=y,minlength=J).astype(int)
    supported=np.bincount(j,weights=(abs(theta[p]-difficulty[j])<1),minlength=J).astype(int)
    order=np.argsort(difficulty,kind='stable')
    groups=np.array_split(order,round(J/12)); table=[]; folders=[]; rankings=[]
    for g,indices in enumerate(groups,1):
        songs=[]
        for k in indices:
            row=meta[k]; rank=len(table)+1
            provisional=n[k]<100 or wins[k]<5 or supported[k]<30
            status='provisional' if provisional else 'supported'
            comment=f'98% rank {rank}/{J}; original ★{row["level"]}; {wins[k]}/{n[k]} achieved; {status}'
            item={key:row[key] for key in ['md5','sha256','title','artist','url','url_diff'] if row.get(key)}
            item.update(level=f'{g:03}',comment=comment)
            table.append(item)
            songs.append({key:item[key] for key in ['md5','sha256','title','artist'] if key in item})
            rankings.append(dict(rank=rank,folder=f'{g:03}',md5=row['md5'],title=row['title'],
                original_level=row['level'],difficulty98=float(difficulty[k]),
                observations=int(n[k]),achieved98=int(wins[k]),nearby_players=int(supported[k]),status=status,
                total_plays=row.get('total_plays',0),total_players=row.get('total_players',0),
                plays_per_player=row.get('total_plays',0)/max(row.get('total_players',0),1)))
        folders.append({'name':f'98% {g:03}  [{len(table)-len(indices)+1:04}–{len(table):04}]','songs':songs})
    header={'name':'Insane 98% — easiest to hardest','symbol':'98% ','data_url':'data.json',
            'level_order':[f'{g:03}' for g in range(1,len(groups)+1)]}
    dump(out/'header.json',header); dump(out/'data.json',table); dump(out/'rankings.json',rankings)
    native={'name':header['name'],'url':'','tag':'98%','folder':folders,'course':[]}
    dump(out/'insane-98-native.json',native)
    with gzip.open(out/'insane-98.bmt','wt',encoding='utf-8') as f: json.dump(native,f,ensure_ascii=False)
    dump(out/'validation.json',report)
    lines=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="bmstable" content="header.json">',
           '<title>Insane 98% difficulty table</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;background:#111827;color:#e5e7eb}table{border-collapse:collapse;width:100%}td,th{padding:8px;text-align:left;border-bottom:1px solid #374151}a{color:#93c5fd}</style>',
           '<h1>Insane 98% difficulty table</h1><p>Lower folder numbers are easier. Ranking estimates 98% EX personal-best difficulty, adjusted for player skill. Provisional means weak evidence; it is not a precise ordering.</p>',
           '<p>Historical LR2IR archive, May 2026. 1,035 charts, 86 folders. Scores and skill may reflect different dates and amounts of practice.</p>',
           '<p>Popularity and practice: the plays/player column is an aggregate exposure indicator, not a correction. Repeated practice can improve PBs; this archive cannot identify difficulty under equal practice budgets.</p>',
           '<table><thead><tr><th>Rank</th><th>Folder</th><th>Chart</th><th>Original</th><th>98% / players</th><th>Evidence</th><th>Plays/player</th></tr></thead><tbody>']
    for r in rankings:
        lines.append(f'<tr><td>{r["rank"]}</td><td>{r["folder"]}</td><td>{html.escape(r["title"])}</td><td>★{html.escape(str(r["original_level"]))}</td><td>{r["achieved98"]}/{r["observations"]}</td><td>{r["status"]}</td><td>{r["plays_per_player"]:.1f}</td></tr>')
    lines.append('</tbody></table></html>'); (out/'index.html').write_text('\n'.join(lines),encoding='utf-8')
    assert len(table)==1035 and len({r['md5'] for r in table})==1035
    assert all(10<=len(g)<=15 for g in groups)
    assert all(rankings[k]['difficulty98']<=rankings[k+1]['difficulty98'] for k in range(J-1))
    print('Built',len(table),'charts;',len(groups),'folders;',sum(r['status']=='provisional' for r in rankings),'provisional',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--db'); ap.add_argument('--out'); args=ap.parse_args()
    if args.db: extract(args.db)
    if args.out: build(args.out)
