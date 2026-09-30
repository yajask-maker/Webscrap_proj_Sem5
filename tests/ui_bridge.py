from fastapi.testclient import TestClient
from app.main import create_app
from app.models import Record
from pathlib import Path
import tempfile,json,sys
class Provider:
 def fetch(self,source,query):
  return [Record(kind='paper',source=source,external_id='example',title='Live path fixture for graph research')]
 def close(self): pass
with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Path(tmp)/'ui.db',Provider())) as c:
 for line in sys.stdin:
  try:
   req=json.loads(line); r=c.request(req['method'],req['path'],json=req.get('body'))
   print(json.dumps({'id':req['id'],'status':r.status_code,'body':r.text}),flush=True)
  except Exception as e: print(json.dumps({'id':req.get('id'),'status':500,'body':json.dumps({'detail':str(e)})}),flush=True)
