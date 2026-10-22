"""Execute the report's initialization with missing and configured leave periods."""
import json
import subprocess
import unittest
from pathlib import Path


class LeaveBalanceFiltersTests(unittest.TestCase):
    def run_onload(self, response):
        source = Path(__file__).resolve().parents[1] / "hrms/hr/report/employee_leave_balance/employee_leave_balance.js"
        script = r'''
const vm = require('vm'), fs = require('fs');
const updates = [];
const frappe = {
 query_reports: {}, datetime: {now_date: () => '2026-10-18'},
 defaults: {get_user_default: () => 'Local Company', get_user_permissions: () => ({})},
 call: options => options.callback(RESPONSE),
 query_report: {set_filter_value: value => {updates.push(value); return Promise.resolve();}},
};
vm.runInNewContext(fs.readFileSync(SOURCE, 'utf8'), {frappe, __: text => text});
frappe.query_reports['Employee Leave Balance'].onload();
console.log(JSON.stringify(updates));
'''.replace('RESPONSE', json.dumps(response)).replace('SOURCE', json.dumps(str(source)))
        return json.loads(subprocess.check_output(['node', '-e', script], text=True))

    def test_no_leave_period_keeps_the_required_filter_prompt(self):
        self.assertEqual(self.run_onload({}), [])
        self.assertEqual(self.run_onload({'message': []}), [])

    def test_leave_period_sets_both_dates_in_one_refresh(self):
        period = {'from_date': '2026-01-01', 'to_date': '2026-12-31'}
        self.assertEqual(self.run_onload({'message': [period]}), [period])


class VehicleExpenseFiltersTests(unittest.TestCase):
    def test_missing_fiscal_year_is_required_before_the_first_request(self):
        source = Path(__file__).resolve().parents[1] / "hrms/hr/report/vehicle_expenses/vehicle_expenses.js"
        script = r'''const vm=require('vm'),fs=require('fs');
const frappe={query_reports:{},defaults:{get_user_default:()=>''},datetime:{nowdate:()=> '2026-10-18',add_months:()=> '2025-10-18'}};
vm.runInNewContext(fs.readFileSync(SOURCE,'utf8'),{frappe,__:(x)=>x});
const filters=frappe.query_reports['Vehicle Expenses'].filters;
const values=Object.fromEntries(filters.map(f=>[f.fieldname,f.default]));
const missing=filters.filter(f=>f.reqd&&!values[f.fieldname]).map(f=>f.fieldname);
console.log(JSON.stringify(missing));'''.replace('SOURCE',json.dumps(str(source)))
        self.assertEqual(json.loads(subprocess.check_output(['node','-e',script],text=True)), ['fiscal_year'])
