import json
import sys
import urllib.request

DEVTOOLS_URL = "http://127.0.0.1:9222/json"

try:
    with urllib.request.urlopen(DEVTOOLS_URL) as resp:
        data = json.load(resp)
except Exception as e:
    print(f"ERROR: could not fetch {DEVTOOLS_URL}: {e}")
    sys.exit(1)

# Find the Wastewater PCR page
ws_url = None
for item in data:
    if "Wastewater PCR" in item.get("title", ""):
        ws_url = item.get("webSocketDebuggerUrl")
        print("Found target:", item.get("title"), "ws:", ws_url)
        break

if not ws_url:
    print("ERROR: Could not find Wastewater PCR target in DevTools list.")
    sys.exit(1)

# Try websocket-client first
try:
    from websocket import create_connection
except Exception as e:
    print("websocket-client not installed:", e)
    print("Install with: pip install websocket-client and re-run this script")
    sys.exit(2)

try:
    ws = create_connection(ws_url)
    # Evaluate equipment_json
    msg_id = 1
    expr = 'typeof equipment_json !== "undefined" ? JSON.stringify(equipment_json, null, 2) : "__EQUIPMENT_JSON_UNDEFINED__"'
    payload = json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}})
    ws.send(payload)
    while True:
        resp = ws.recv()
        print(resp)
        # break after we see the result id
        try:
            j = json.loads(resp)
            if j.get('id') == msg_id:
                print('\n--- Parsed result ---')
                print(json.dumps(j, indent=2))
                break
        except Exception:
            pass
        # Force-run the page's updateTipChoices for the Liquid Handler and return the select options
        expr_force = '(function(){try{let er = equipment_json.find(e=> e.name==="Wastewater PCR Liquid Handler"); if(!er) return "__NO_ER__"; if(typeof updateTipChoices!="function") return "__NO_FN__"; updateTipChoices(er); let el=document.getElementById("Wastewater PCR Liquid Handler_tips"); if(!el) return "__NO_ELEMENT__"; let a=[]; for(let i=0;i<el.options.length;i++) a.push(el.options[i].value); return JSON.stringify({len:el.options.length, opts:a});}catch(e){return "__ERR__:"+e.toString();}})()'
        payload_force = json.dumps({"id": msg_id+1, "method": "Runtime.evaluate", "params": {"expression": expr_force, "returnByValue": True}})
        ws.send(payload_force)
        respf = ws.recv()
        print('Force eval response:', respf)
        try:
            j = json.loads(respf)
            print('\n--- Forced eval parsed ---')
            print(json.dumps(j, indent=2))
        except Exception:
            print('Could not parse forced eval response')
        ws.close()
        ws.close()
except Exception as e:
    print('ERROR connecting or evaluating via websocket:', e)
    sys.exit(3)
