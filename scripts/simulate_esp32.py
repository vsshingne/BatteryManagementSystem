"""Post explicitly synthetic, dual-battery examples to a live development backend."""
import argparse, json, os, time, urllib.error, urllib.request

url=os.getenv('BMS_INGEST_URL','http://127.0.0.1:8000/api/ingest')
token=os.getenv('BMS_INGEST_TOKEN')
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--count',type=int,default=0,help='number of posts; 0 runs continuously');args=parser.parse_args()
tick=0
while not args.count or tick<args.count:
    payload={'device_id':'SIMULATED_ESP32_SENDER','batteries':[
        {'battery_id':'BATTERY_1','voltage':12.4+0.03*(tick%5),'current':1.4,'temperature':29.5,'soc':85-tick%10,'battery_status':'NORMAL','operating_mode':'Discharging'},
        {'battery_id':'BATTERY_2','voltage':12.1,'current':-0.8,'temperature':30.2,'soc':72+tick%8,'battery_status':'NORMAL','operating_mode':'Charging'}]}
    headers={'Content-Type':'application/json','User-Agent':'synthetic-esp32-development-sender'}
    if token: headers['Authorization']=f'Bearer {token}'
    request=urllib.request.Request(url,data=json.dumps(payload).encode(),headers=headers,method='POST')
    try:
        with urllib.request.urlopen(request,timeout=5) as response: print(response.status,response.read().decode())
    except (urllib.error.URLError,TimeoutError) as exc: print(f'Simulated sender error: {exc}')
    tick+=1; time.sleep(1)
