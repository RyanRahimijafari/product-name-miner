#!/bin/bash
# wipo.sh TERM "Option text" -> parsed result list (first page, most relevant first)
js=$(mktemp)
trap 'rm -f "$js"' EXIT
cat > "$js" <<JS
(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const inp=document.querySelectorAll('input.b-input__text-input')[0];
const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set; setter.call(inp,'$1'); inp.dispatchEvent(new Event('input',{bubbles:true})); inp.dispatchEvent(new Event('change',{bubbles:true}));
const sel=document.querySelector('select.b-input__dropdown-input'); const opts=[...sel.options].map(o=>o.text.trim());
const want=opts.findIndex(o=>o.startsWith('$2')); sel.selectedIndex=want; sel.dispatchEvent(new Event('change',{bubbles:true}));
await sleep(700);
[...document.querySelectorAll('button')].find(b=>/^\s*Search\s*$/.test(b.innerText)).click();
await sleep(9000);
const seen=new Map(); const re=/([^\n]+)\nOwner\n([^\n]+)\nNice class\n([^\n]+)\nIPR\n([^\n]+)\nCountry of filing\n([^\n]+)\nStatus\n([^\n]+)\nNumber\n([^\n]+)/g;
for(let i=0;i<30;i++){ const tx=document.body.innerText; let m; while((m=re.exec(tx))) seen.set(m[7],m); window.scrollBy(0,500); document.querySelectorAll('*').forEach(e=>{ if(e.scrollHeight>e.clientHeight+200 && getComputedStyle(e).overflowY!=='visible'){e.scrollTop+=500} }); await sleep(350);}
const head=(document.body.innerText.match(/Displaying[^\n]*/)||[''])[0];
return 'MODE='+opts[want]+' | '+head+'\n'+[...seen.values()].map(m=>[m[1],m[2],'cl '+m[3],m[5],m[6],m[7]].join(' | ')).join('\n');})()
JS
node "$(dirname "$0")/render.mjs" "https://branddb.wipo.int/en/similarname" 8 "$js" 1 2>&1 | sed -n '/^\[js\]/,/^\[url\]/p' | grep -v "^\[url\]"
