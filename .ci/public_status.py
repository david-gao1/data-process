"""Only verification status is eligible for artifact; no source rows or monetary results."""
import json,sys
from pathlib import Path
status=int(sys.argv[1]);phase=sys.argv[2]
result={'passed':status==0,'phase':phase,'exit_code':status,'historical_replay':True,'realtime_cdc':False,'raw_data_artifact':False}
Path('.ci-reports').mkdir(exist_ok=True)
Path('.ci-reports/public-status.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
