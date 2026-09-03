import os
import sys
import tempfile
import base64
import shutil
from pathlib import Path
from fastapi.testclient import TestClient

REPO_ROOT = Path('/Users/amitsethi/Downloads/HeartlakeCricketApp')
SOURCE_DATA_DIR = REPO_ROOT / 'app' / 'data'
SOURCE_SEED_FILE = SOURCE_DATA_DIR / 'seed.json'
SOURCE_DB_FILE = SOURCE_DATA_DIR / 'cricketclubapp.db'
SOURCE_CACHE_FILE = SOURCE_DATA_DIR / 'store_cache.json'
SOURCE_DASHBOARD_CACHE_FILE = SOURCE_DATA_DIR / 'dashboard_cache.json'

runtime_root = Path(tempfile.mkdtemp(prefix='cricketclubapp-qa-'))
for path in [runtime_root / 'data', runtime_root / 'uploads', runtime_root / 'duplicates']:
    path.mkdir(parents=True, exist_ok=True)
for src, dst in [
    (SOURCE_SEED_FILE, runtime_root / 'data' / 'seed.json'),
    (SOURCE_DB_FILE, runtime_root / 'data' / 'cricketclubapp.db'),
    (SOURCE_CACHE_FILE, runtime_root / 'data' / 'store_cache.json'),
    (SOURCE_DASHBOARD_CACHE_FILE, runtime_root / 'data' / 'dashboard_cache.json'),
]:
    shutil.copy2(src, dst)

os.environ['APP_ENV'] = 'local'
os.environ['CRICKETCLUBAPP_DATA_ROOT'] = str(runtime_root / 'data')
os.environ['CRICKETCLUBAPP_DATABASE_FILE'] = str(runtime_root / 'data' / 'cricketclubapp.db')
os.environ['CRICKETCLUBAPP_CACHE_FILE'] = str(runtime_root / 'data' / 'store_cache.json')
os.environ['CRICKETCLUBAPP_DASHBOARD_CACHE_FILE'] = str(runtime_root / 'data' / 'dashboard_cache.json')
os.environ['CRICKETCLUBAPP_SEED_FILE'] = str(runtime_root / 'data' / 'seed.json')
os.environ['CRICKETCLUBAPP_UPLOAD_DIR'] = str(runtime_root / 'uploads')
os.environ['CRICKETCLUBAPP_DUPLICATE_DIR'] = str(runtime_root / 'duplicates')

sys.path.insert(0, str(REPO_ROOT))
import app.main as main
client = TestClient(main.app)
resp = client.post('/api/auth/signin', json={'identifier': '14164508695', 'password': '', 'player_name': 'Amit S'})
print('signin', resp.status_code, resp.text)
if resp.status_code \!= 200:
    sys.exit(1)

files = {'file': ('mobile-scorecard.heic', base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2b5XQAAAAASUVORK5CYII='), 'image/heic')}
resp = client.post('/api/scorecards/upload', headers={'X-Auth-Token': resp.json()['token']}, files=files, data={'season': '2025 Season', 'focus_club_id': 'club-coca-cola-xi'})
print('upload', resp.status_code, resp.text)
store = main.load_store()
print('archives', len(store['archive_uploads']))
for item in store['archive_uploads']:
    print('---')
    print('file_name:', item.get('file_name'))
    print('status:', item.get('status'))
    print('ocr_engine:', item.get('ocr_engine'))
    print('confidence:', item.get('confidence'))
    print('draft_scorecard:', item.get('draft_scorecard'))
    print('raw_extracted_text:', repr(item.get('raw_extracted_text')[:120]))
