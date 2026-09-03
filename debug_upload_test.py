import os,sys,tempfile,shutil,base64
from pathlib import Path
REPO_ROOT=Path('/Users/amitsethi/Downloads/HeartlakeCricketApp')
SOURCE_DATA_DIR=REPO_ROOT/'app'/'data'
for p in [SOURCE_DATA_DIR/'seed.json', SOURCE_DATA_DIR/'cricketclubapp.db', SOURCE_DATA_DIR/'store_cache.json', SOURCE_DATA_DIR/'dashboard_cache.json']:
    if not p.exists():
        raise SystemExit(f'missing {p}')
runtime_root=Path(tempfile.mkdtemp(prefix='cricketclubapp-'))
for d in ['data','uploads','duplicates']:
    (runtime_root/d).mkdir(parents=True, exist_ok=True)
for src,dst in [(SOURCE_DATA_DIR/'seed.json', runtime_root/'data'/'seed.json'), (SOURCE_DATA_DIR/'cricketclubapp.db', runtime_root/'data'/'cricketclubapp.db'), (SOURCE_DATA_DIR/'store_cache.json', runtime_root/'data'/'store_cache.json'), (SOURCE_DATA_DIR/'dashboard_cache.json', runtime_root/'data'/'dashboard_cache.json')]:
    shutil.copy2(src,dst)
os.environ['APP_ENV']='local'
os.environ['CRICKETCLUBAPP_DATA_ROOT']=str(runtime_root/'data')
os.environ['CRICKETCLUBAPP_DATABASE_FILE']=str(runtime_root/'data'/'cricketclubapp.db')
os.environ['CRICKETCLUBAPP_CACHE_FILE']=str(runtime_root/'data'/'store_cache.json')
os.environ['CRICKETCLUBAPP_DASHBOARD_CACHE_FILE']=str(runtime_root/'data'/'dashboard_cache.json')
os.environ['CRICKETCLUBAPP_SEED_FILE']=str(runtime_root/'data'/'seed.json')
os.environ['CRICKETCLUBAPP_UPLOAD_DIR']=str(runtime_root/'uploads')
os.environ['CRICKETCLUBAPP_DUPLICATE_DIR']=str(runtime_root/'duplicates')

sys.path.insert(0,str(REPO_ROOT))
from fastapi.testclient import TestClient
from app.main import app
from app.cricket_store import load_store
client=TestClient(app)
resp=client.post('/api/auth/signin', json={'identifier':'14164508695','password':'','player_name':'Amit S'})
print('signin', resp.status_code, resp.text)
if resp.status_code != 200:
    sys.exit(1)
token=resp.json()['token']
files={'file':('mobile-scorecard.heic', base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2b5XQAAAAASUVORK5CYII='),'image/heic')}
resp=client.post('/api/scorecards/upload', headers={'X-Auth-Token':token}, files=files, data={'season':'2025 Season','focus_club_id':'club-coca-cola-xi'})
print('upload', resp.status_code, resp.text)
archive=resp.json().get('upload')
if archive is None:
    print('no upload returned')
else:
    for k in ['id','status','ocr_engine','confidence','draft_scorecard','raw_extracted_text','extracted_summary','ocr_processed_at','file_path','file_hash','file_name','source','match_id','club_id','club_name']:
        print(k, repr(archive.get(k)))
print('saved_count', len(load_store()['archive_uploads']))
