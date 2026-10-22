"""Address lookup failures finish the check-in preview instead of leaving a spinner."""
import json
from pathlib import Path
import subprocess
import unittest


class CheckinAddressTests(unittest.TestCase):
    def check(self, result):
        source = (Path(__file__).resolve().parents[1] / 'frontend/src/components/CheckInPanel.vue').read_text()
        source = source[source.index('function handleLocationSuccess'):source.index('const handleEmployeeCheckin')]
        script = r'''
const vm=require('vm');const ctx={latitude:{value:0},longitude:{value:0},locationStatus:{value:''},checkinAddress:{value:''},__:(s)=>s,createResource:()=>({fetch:()=>RESULT}),navigator:{}};
vm.createContext(ctx);vm.runInContext(SOURCE,ctx);
(async()=>{ctx.handleLocationSuccess({coords:{latitude:51.5,longitude:-0.1}});await new Promise(r=>setImmediate(r));const address=ctx.checkinAddress.value;ctx.handleLocationError({code:1,message:'Denied'});const denied=ctx.checkinAddress.value;vm.runInContext('fetchLocation()',ctx);console.log(JSON.stringify([address,denied,ctx.checkinAddress.value]));})();
'''.replace('SOURCE',json.dumps(source)).replace('RESULT',result)
        return json.loads(subprocess.check_output(['node','-e',script],text=True))

    def test_success_uses_the_live_address(self):
        self.assertEqual(self.check('Promise.resolve("Test Street")'), ['Test Street', 'Address unavailable', 'Address unavailable'])

    def test_empty_lookup_and_network_failure_finish_the_preview(self):
        for response in ['Promise.resolve("")', 'Promise.reject(Error("offline"))']:
            self.assertEqual(self.check(response), ['Address unavailable'] * 3)
