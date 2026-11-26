const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const base='work/publish/stellalite-score-tables/';
class Element{constructor(){this.children=[];this.value='';this.textContent='';this.disabled=false;this.handlers={};}replaceChildren(...x){this.children=x;}append(...x){this.children.push(...x);}addEventListener(k,f){this.handlers[k]=f;}}
const ids=['chart-total','folder','search','previous','next','folder-total','average','size-range','definition','difficulty-label','achievement-label','native','validation','notes','import-url','caution','rows','range','count'];
let count=0;
for(const [path,target] of [['','98'],['aaa/','aaa'],['max-minus/','max-minus']]){
 const page=fs.readFileSync(base+path+'index.html','utf8'),ui=Object.fromEntries(ids.map(id=>[id,new Element()]));
 vm.runInNewContext(page.match(/<script>([\s\S]*?)<\/script>/)[1],{document:{getElementById:k=>ui[k],createElement:()=>new Element()}});
 const rows=JSON.parse(fs.readFileSync(base+path+'rankings.json','utf8')),folders=JSON.parse(fs.readFileSync(base+path+'folders.json','utf8'));
 assert.equal(ui['chart-total'].textContent,rows.length.toLocaleString());assert.equal(ui['import-url'].href,'https://sehun-joo.github.io/stellalite-score-tables/'+path);
 assert.equal(ui.folder.value,'001');assert.equal(ui.previous.disabled,true);
 ui.next.onclick();assert.equal(ui.folder.value,'002');ui.previous.onclick();assert.equal(ui.folder.value,'001');
 for(const f of folders){ui.folder.value=f.id;ui.folder.handlers.change();const selected=rows.filter(r=>r.folder===f.id);assert.equal(ui.rows.children.length,selected.length);selected.forEach((r,i)=>{assert.equal(ui.rows.children[i].children[1].textContent,r.title);assert.equal(ui.rows.children[i].children[0].textContent,i+1);assert.equal(ui.rows.children[i].children[6].textContent,r.total_plays.toLocaleString());});count++;}
 assert.equal(ui.next.disabled,true);ui.folder.value='all';ui.folder.handlers.change();assert.equal(ui.rows.children.length,rows.length);
 ui.search.value=rows[0].title.toLowerCase();ui.search.handlers.input();assert.ok(ui.rows.children.length>=1);ui.search.value='no-such-stellalite-chart-xyz';ui.search.handlers.input();assert.equal(ui.rows.children.length,0);
}
console.log('PASS: all three live-page scripts, '+count+' range renders, popularity ordering, total plays, target import URLs, navigation and search.');
