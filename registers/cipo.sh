#!/bin/bash
# cipo.sh TEXT [display]  -> the Canadian Trademarks Database results text for TEXT
q="$1"
url=$(python -c "
import json,sys,urllib.parse as u
p=json.dumps({'domIntlFilter':'1','searchfield1':'all','textfield1':sys.argv[1],'display':'list','maxReturn':'1000','nicetextfield1':None,'cipotextfield1':None},separators=(',',':'))
print('https://ised-isde.canada.ca/cipo/trademark-search/srch?payload='+u.quote(u.quote(p,safe=''),safe=''))" "$q")
node "$(dirname "$0")/render.mjs" "$url" 9 2>&1 | grep -v "^\s*$"
