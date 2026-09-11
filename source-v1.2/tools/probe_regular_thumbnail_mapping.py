"""Read-only identity comparison; output only aggregated findings."""
import sys, json
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fh6garage.auction_thumbnails import read_thumbnail_manifest, _header_livery_token
from fh6garage.parsers import read_header_file
from fh6garage.models import LiveryRecord
containers = Path(sys.argv[1]); cache = Path(sys.argv[2])
rows = read_thumbnail_manifest(cache)
stats = Counter()
examples = []
for folder in containers.iterdir():
    kind = folder.name.split('_',1)[0]
    if kind not in ('Livery','SoulBoundLivery') or not folder.is_dir(): continue
    stats[kind+'.total'] += 1
    try:
        header = read_header_file(folder/'header',kind)
        r = LiveryRecord(folder.name,folder,kind,header)
        token = _header_livery_token(r)
        matched = {row.path for row in rows if row.livery_token == token and row.car_id == header.car_id}
        existing = [p for p in matched if p.is_file()]
        stats[kind+'.token_rows'] += bool(matched)
        stats[kind+'.existing_single'] += len(existing)==1
        stats[kind+'.existing_multiple'] += len(existing)>1
        stats[kind+'.folder_thumb'] += (folder/'bigThumb.webp').is_file() or (folder/'BigThumb.webp').is_file()
        if kind=='Livery' and existing and len(examples)<3:
            examples.append({'container':folder.name,'car_id':header.car_id,'token':token,'cache_files':[p.name for p in existing]})
    except Exception as exc: stats[kind+'.errors']+=1
result = {'manifest_rows':len(rows),'with_design_token':sum(bool(r.livery_token) for r in rows), 'stats':dict(stats), 'examples':examples, 'read_only':True}
out = Path(sys.argv[3]);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result,indent=2))
