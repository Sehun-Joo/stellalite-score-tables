"""Independent Stella+Satellite model; never select by popularity before fitting."""
from pathlib import Path
import collections,json,math,sqlite3
import numpy as np
from scipy.special import expit,ndtr
from build_table import latent,metrics,dump
from fit_target_separable import target_fit
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'stellalite'
if not (OUT/'observations.npz').exists():
    con=sqlite3.connect((ROOT/'lr2ir-archive-v3.db').resolve().as_uri()+'?mode=ro',uri=True)
    cheaters={r[0] for r in con.execute('SELECT player_id FROM user WHERE is_cheater=1')}
    seen=set();meta=[];blocks=[];excluded=[];audit=collections.Counter()
    for table in ['sl','st']:
        source=json.loads((OUT/(table+'-source.json')).read_text(encoding='utf-8'))
        for row in source:
            md5=row['md5'].lower()
            if md5 in seen:continue
            seen.add(md5)
            c=con.execute('SELECT play_count,play_people,keys FROM chart WHERE md5=?',(md5,)).fetchone()
            if not c:excluded.append(dict(row,table=table,reason='Absent from May 2026 archive'));continue
            valid=[]
            for pid,s,m,cheat,o1,o2 in con.execute('SELECT player_id,score,score_max,is_cheated,option_1,option_2 FROM pb WHERE md5=?',(md5,)):
                audit['raw_pbs']+=1
                if cheat or pid in cheaters or m<=0 or s<=0 or s>m:audit['invalid_zero_or_flagged']+=1;continue
                if any(x in (o1+' '+o2).upper() for x in ['AUTO','5KEY','9KEY','BATTLE']):audit['assist']+=1;continue
                valid.append((pid,s,m))
            if valid:
                mode=collections.Counter(v[2] for v in valid).most_common(1)[0][0]
                valid=[v for v in valid if v[2]==mode]
            if len(valid)<30:excluded.append(dict(row,table=table,reason='Fewer than 30 comparable PBs',usable_pbs=len(valid)));continue
            j=len(meta);meta.append(dict(row,md5=md5,original_level=table+str(row['level']),table=table,total_plays=c[0],total_players=c[1]))
            blocks.extend((pid,j,s,m) for pid,s,m in valid)
            if len(meta)%500==0:print('Extracted',len(meta),'charts',len(blocks),'PBs',flush=True)
    np.savez_compressed(OUT/'observations.npz',rows=np.asarray(blocks,dtype=np.int64))
    dump(OUT/'metadata.json',meta);dump(OUT/'excluded.json',excluded);dump(OUT/'extraction-audit.json',dict(audit))
raw=np.load(OUT/'observations.npz')['rows'];meta=json.loads((OUT/'metadata.json').read_text(encoding='utf-8'))
ids,n=np.unique(raw[:,0],return_counts=True);rows=raw[np.isin(raw[:,0],ids[n>=10])];del raw
# Recheck eligibility after excluding players with insufficient overlap.
counts=np.bincount(rows[:,1],minlength=len(meta));keep=np.flatnonzero(counts>=30)
excluded=json.loads((OUT/'excluded.json').read_text(encoding='utf-8'))
excluded.extend(dict(meta[k],reason='Fewer than 30 PBs after player-overlap filter') for k in np.flatnonzero(counts<30))
remap=np.full(len(meta),-1);remap[keep]=np.arange(len(keep));rows=rows[np.isin(rows[:,1],keep)];rows[:,1]=remap[rows[:,1]]
meta=[meta[k] for k in keep];dump(OUT/'model-metadata.json',meta);dump(OUT/'model-excluded.json',excluded)
ids,p=np.unique(rows[:,0],return_inverse=True);P=len(ids);J=len(meta);j=rows[:,1]
t=-np.log((rows[:,3]-rows[:,2]+.5)/(rows[:,3]+.5))
print('Model cohort',J,'charts',P,'players',len(rows),'PBs',flush=True)
dump(OUT/'cohort.json',dict(charts=J,players=P,pbs=len(rows),excluded=len(excluded),source_charts=len(meta)+len(excluded),snapshot_date='2026-11-26',score_archive='2026-05-29'))
rng=np.random.default_rng(20261126);trainplayers=rng.random(P)<.8;train=trainplayers[p]
reference=(~train)&(rng.random(len(p))<.5);test=(~train)&~reference
_,pt=np.unique(p[train],return_inverse=True)
models=[]
for name,pp,jj,tt,nplayers in [('train',pt,j[train],t[train],int(pt.max()+1)),('full',p,j,t,P)]:
    cache=OUT/(name+'-model.npz')
    if not cache.exists():
        th,mu,a,sigma,it=latent(pp,jj,tt,nplayers,J,variable=True)
        np.savez_compressed(cache,theta=th,mu=mu,a=a,sigma=sigma)
    c=np.load(cache);models.append([c[k] for k in ['theta','mu','a','sigma']])
theta,mu,a,sigma=models[0];fulltheta,fullmu,fulla,fullsigma=models[1]
pr,jr,tr=p[reference],j[reference],t[reference];w=np.ones(len(pr));skill=np.zeros(P)
for it in range(40):
    old=skill.copy();skill=np.bincount(pr,weights=w*a[jr]*(tr-mu[jr]),minlength=P)/(np.bincount(pr,weights=w*a[jr]**2,minlength=P)+.5)
    resid=tr-mu[jr]-a[jr]*skill[pr];w=np.minimum(1,.65/np.maximum(abs(resid),1e-8))
    if np.max(abs(old-skill))<1e-5:break
test &= np.bincount(pr,minlength=P)[p]>=5
n=np.bincount(j,minlength=J)
for slug,label,num,den in [('aaa','AAA',8,9),('max-minus','MAX−',17,18),('98','98%',98,100)]:
    if (OUT/(slug+'-rankings.json')).exists():continue
    target=num/den;threshold=-math.log1p(-target);y=(den*rows[:,2]>=num*rows[:,3]).astype(float)
    bh,ah=target_fit(theta,mu,a,pt,j[train],y[train],J,target)
    qj,qp,qy=j[test],p[test],y[test];near=abs(skill[qp]-(threshold-mu[qj])/a[qj])<1
    nh=np.bincount(j[train],minlength=J);wins=np.bincount(j[train],weights=y[train],minlength=J)
    pred={'target_specific':expit(ah[qj]*(skill[qp]-bh[qj])),'score_curve':ndtr((mu[qj]+a[qj]*skill[qp]-threshold)/sigma[qj]),'raw_rate':((wins+.5)/(nh+1))[qj]}
    validation=dict(target=label,evaluation_records=int(test.sum()),evaluated_players=len(np.unique(qp)),near_target_records=int(near.sum()),overall={k:metrics(qy,v) for k,v in pred.items()},near_target={k:metrics(qy[near],v[near]) for k,v in pred.items()})
    dump(OUT/(slug+'-validation.json'),validation)
    print('VALIDATION',slug,json.dumps(validation),flush=True)
    b,aa=target_fit(fulltheta,fullmu,fulla,p,j,y,J,target)
    np.savez_compressed(OUT/(slug+'-parameters.npz'),b=b,a=aa)
    achieved=np.bincount(j,weights=y,minlength=J).astype(int);nearby=np.bincount(j,weights=(abs(fulltheta[p]-b[j])<1),minlength=J).astype(int)
    ranking=[]
    for rank,k in enumerate(np.argsort(b,kind='stable'),1):
        m=meta[k];provisional=n[k]<100 or min(achieved[k],n[k]-achieved[k])<5 or nearby[k]<30
        ranking.append(dict(rank=rank,md5=m['md5'],title=m['title'],original_level=m['original_level'],difficulty=float(b[k]),observations=int(n[k]),achieved=int(achieved[k]),nearby_players=int(nearby[k]),status='provisional' if provisional else 'supported',total_plays=m['total_plays'],total_players=m['total_players'],plays_per_player=m['total_plays']/max(m['total_players'],1)))
    dump(OUT/(slug+'-rankings.json'),ranking)
    print('COMPLETED',slug,'provisional',sum(r['status']=='provisional' for r in ranking),flush=True)
