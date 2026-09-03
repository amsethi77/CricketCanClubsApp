from pathlib import Path
from app.cricket_store import load_store, save_store

store = load_store()
removed = [item for item in store.get('archive_uploads', []) if item.get('file_name') == '441c00a58b.jpg']
if not removed:
    print('No archive upload found for 441c00a58b.jpg')
else:
    print('Removing', len(removed), 'archive item(s)')
    store['archive_uploads'] = [item for item in store.get('archive_uploads', []) if item.get('file_name') != '441c00a58b.jpg']
    store['duplicate_uploads'] = [item for item in store.get('duplicate_uploads', []) if item.get('original_file_name') != '441c00a58b.jpg' and item.get('duplicate_file_name') != '441c00a58b.jpg']
    save_store(store)
    print('Store saved. Removed archive upload')
    for item in removed:
        file_path = item.get('file_path')
        if file_path:
            p = Path(file_path)
            if p.exists():
                p.unlink()
                print('Deleted file:', p)
            else:
                print('File not found:', p)
