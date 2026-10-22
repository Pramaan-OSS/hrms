"""Payout controls survive the submitted form's context-button refresh."""
import json
import subprocess
import unittest
from pathlib import Path


class PayoutButtonTests(unittest.TestCase):
    def labels(self, status=1, quote=None, transfer=None):
        source = Path(__file__).resolve().parents[1] / 'hrms/payroll/doctype/payroll_entry/payroll_entry.js'
        doc = {'docstatus': status, 'payout_quote_ref': quote, 'payout_transfer_ref': transfer}
        script = r'''
const fs=require('fs'),vm=require('vm'),handlers={};let labels=[];
const frappe={provide:()=>{},ui:{form:{on:(name,h)=>handlers[name]=h}}};
vm.runInNewContext(fs.readFileSync(SOURCE,'utf8'),{frappe,__:(x)=>x});
const frm={doc:DOC,is_new:()=>false,custom_buttons:{},clear_custom_buttons:()=>labels=[],
 page:{clear_primary_action:()=>{}},events:{add_context_buttons:()=>labels.push('Context')},
 add_custom_button:label=>{labels.push(label);return {toggleClass:()=>{}}}};
handlers['Payroll Entry'].refresh(frm);console.log(JSON.stringify(labels));
'''.replace('SOURCE', json.dumps(str(source))).replace('DOC', json.dumps(doc))
        return json.loads(subprocess.check_output(['node', '-e', script], text=True))

    def test_submitted_run_has_approval_and_quote_controls_after_refresh(self):
        self.assertEqual(self.labels(), ['Context', 'Approve Payout', 'Prepare Payout Quote'])

    def test_send_requires_a_quote_and_disappears_after_a_transfer(self):
        self.assertIn('Send Payout', self.labels(quote='quote-1'))
        self.assertNotIn('Send Payout', self.labels(quote='quote-1', transfer='transfer-1'))

    def test_draft_runs_cannot_offer_payout_actions(self):
        self.assertFalse(any('Payout' in label for label in self.labels(status=0)))
