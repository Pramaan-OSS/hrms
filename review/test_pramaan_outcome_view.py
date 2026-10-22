"""Completed, partial and failed reports remain distinct in reviewer screens."""
import json
import subprocess
import unittest
from pathlib import Path


class OutcomeViewTests(unittest.TestCase):
    def render(self, report):
        source = Path(__file__).resolve().parents[1] / 'hrms/public/js/pramaan.js'
        script = r'''
const fs=require('fs'),vm=require('vm'),messages=[],alerts=[],hrms={pramaan:{}};
const frappe={provide:()=>{},msgprint:m=>messages.push(m),show_alert:m=>alerts.push(m)};
vm.runInNewContext(fs.readFileSync(SOURCE,'utf8'),{hrms,frappe,__:(x)=>x});
const report=REPORT;const before=JSON.stringify(report);
const data=hrms.pramaan.outcome_result(report);
console.log(JSON.stringify({data,messages,alerts,preserved:before===JSON.stringify(report)}));
'''.replace('SOURCE', json.dumps(str(source))).replace('REPORT', json.dumps(report))
        return json.loads(subprocess.check_output(['node', '-e', script], text=True))

    def test_failed_run_never_becomes_an_empty_successful_check(self):
        result = self.render({'status': 'failed', 'error': {'message': 'private upstream diagnostics'}, 'steps': [{'status': 'failed'}]})
        self.assertIsNone(result['data'])
        self.assertIn('No conclusion was reached', result['messages'][0]['message'])
        self.assertNotIn('private upstream', str(result))
        self.assertTrue(result['preserved'])

    def test_completed_run_reads_the_canonical_result(self):
        data = {'criteria': [{'text': 'Support experience', 'status': 'not_checked'}]}
        result = self.render({'status': 'done', 'completeness': 'complete', 'result': data, 'cost': {'charged_micro': 1000}})
        self.assertEqual(result['data'], data)
        self.assertEqual(result['messages'], [])
        self.assertEqual(result['alerts'], [])
        self.assertTrue(result['preserved'])

    def test_partial_run_keeps_the_result_and_warns_the_reviewer(self):
        result = self.render({'status': 'done', 'completeness': 'partial', 'result': {'accounts': []}})
        self.assertEqual(result['data'], {'accounts': []})
        self.assertIn('Only part', result['alerts'][0]['message'])
        self.assertTrue(result['preserved'])
