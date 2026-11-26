from pathlib import Path
import collections,gzip,hashlib,json,re,sqlite3,zipfile
from stellalite_ranges import stage_groups
ROOT=Path(__file__).resolve().parent;site=ROOT/'publish'/'stellalite-score-tables';model=ROOT/'stellalite'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sources=read(site/'satellite-source.json')+read(site/'stella-source.json');hashes={r['md5'] for r in sources}
eligible={r['md5'] for r in read(model/'model-metadata.json')};excluded={r['md5'] for r in read(site/'excluded-charts.json')}
assert not eligible&excluded and eligible|excluded==hashes
db=sqlite3.connect((ROOT/'lr2ir-archive-v3.db').resolve().as_uri()+'?mode=ro',uri=True)
pages={(site/p/'index.html').resolve() for p in ['', 'aaa','max-minus']}
for slug,t in read(site/'targets.json').items():
    dest=site/t['path'];pool=read(dest/'all-rankings.json');rows=read(dest/'rankings.json');folders=read(dest/'folders.json');cuts=read(dest/'range-cuts.json')['ranges']
    assert {r['md5'] for r in pool}==eligible and len({r['md5'] for r in rows})==len(rows)
    expected,_=stage_groups(read(model/(slug+'-rankings.json')))
    assert [(lo,hi) for lo,hi,_ in expected]==[(f['lower_inclusive'],f['upper_exclusive']) for f in cuts]
    for f,cut in zip(folders,cuts):
        candidates=[r for r in pool if f['lower_inclusive']<=r['difficulty']<f['upper_exclusive']]
        chosen=[r for r in rows if r['folder']==f['id']]
        top=sorted(candidates,key=lambda r:(-r['total_plays'],-r['total_players'],r['md5']))[:20]
        assert len(candidates)==cut['candidates']==f['candidates']
        assert len(chosen)==min(20,len(candidates))==f['count']
        assert [r['md5'] for r in chosen]==[r['md5'] for r in top]
        assert [r['popularity_rank'] for r in chosen]==list(range(1,len(chosen)+1))
    for r in pool:
        assert r['total_plays']==db.execute('SELECT play_count FROM chart WHERE md5=?',(r['md5'],)).fetchone()[0]
    selected={r['md5'] for r in rows};assert {r['md5'] for r in pool if r['selected']}==selected
    data=read(dest/'data.json');header=read(dest/'header.json')
    assert header['level_order']==[f['label'] for f in folders]
    assert [(r['md5'],r['level']) for r in data]==[(r['md5'],r['folder_range']) for r in rows]
    with gzip.open(dest/t['native'],'rt',encoding='utf-8') as f:native=json.load(f)
    assert [s['md5'] for g in native['folder'] for s in g['songs']]==[r['md5'] for r in rows]
    assert native['url']=='https://sehun-joo.github.io/stellalite-score-tables/'+t['path']
    html=(dest/'index.html').read_text(encoding='utf-8')
    assert '<meta name="bmstable" content="header.json">' in html
    assert {(dest/h).resolve() for h in re.findall(r'href="([^"]+)"',re.search(r'<nav.*?</nav>',html).group())}==pages
    assert '1,035' not in html and 'PLAYS / PLAYER' not in html and "'★'+r.original_level" not in html
for name,digest in read(site/'checksums.json').items():assert hashlib.sha256((site/name).read_bytes()).hexdigest()==digest,name
with zipfile.ZipFile(site/'stellalite-score-tables.zip') as z:assert z.testzip() is None
print('PASS: coverage, full-pool cuts, exact top-20 selection/order, source play counts, native imports, metadata, checksum and ZIP integrity.')
