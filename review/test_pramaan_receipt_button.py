"""The visible receipt action calls the same tested server boundary."""
import json
import subprocess
import unittest
from pathlib import Path


class ReceiptButtonTests(unittest.TestCase):
    def run_refresh(self, is_new):
        source = Path(__file__).resolve().parents[1] / 'hrms/hr/doctype/expense_claim/expense_claim.js'
        script = r'''
const fs=require('fs'),vm=require('vm'),handlers={},buttons={},calls=[];
const frappe={provide:()=>{},ui:{form:{on:(name,h)=>handlers[name]=h}},call:options=>calls.push({method:options.method,args:options.args})};
vm.runInNewContext(fs.readFileSync(SOURCE,'utf8'),{frappe,__:(x)=>x});
const frm={doc:{name:'CLAIM-1',docstatus:0,expenses:[{}]},multi_currency_enabled:0,is_new:()=>IS_NEW,trigger:()=>{},add_custom_button:(label,fn)=>buttons[label]=fn};
(async()=>{await handlers['Expense Claim'].refresh(frm);buttons['Fill From Receipt']?.();console.log(JSON.stringify({buttons:Object.keys(buttons),calls}));})();
'''.replace('SOURCE', json.dumps(str(source))).replace('IS_NEW', json.dumps(is_new))
        return json.loads(subprocess.check_output(['node', '-e', script], text=True))

    def test_saved_claim_exposes_the_receipt_action_and_correct_endpoint(self):
        result = self.run_refresh(False)
        self.assertIn('Fill From Receipt', result['buttons'])
        self.assertEqual(result['calls'], [{'method': 'hrms.integrations.pramaan_receipts.extract_from_claim', 'args': {'claim': 'CLAIM-1'}}])

    def test_unsaved_claim_does_not_offer_an_unusable_receipt_action(self):
        self.assertEqual(self.run_refresh(True), {'buttons': [], 'calls': []})
