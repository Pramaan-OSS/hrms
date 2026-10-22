"""Mobile script labels resolve the injected translator without a global variable."""
import json
from pathlib import Path
import subprocess
import unittest


class MobileTranslationTests(unittest.TestCase):
    def test_expense_filters_and_shift_validation_run_without_a_global_translator(self):
        root=Path(__file__).resolve().parents[1]
        expense=(root/'frontend/src/views/expense_claim/List.vue').read_text().split('<script setup>')[1].split('</script>')[0]
        expense='\n'.join(line for line in expense.splitlines() if not line.startswith('import '))
        shift=(root/'frontend/src/views/attendance/ShiftAssignmentForm.vue').read_text()
        validate=shift[shift.index('function validateDates('):shift.index('function validateForm(')]
        translator=next(line for line in shift.splitlines() if line.startswith('const __'))
        script='''const vm=require('vm');const ctx={inject:()=>s=>'translated '+s};vm.createContext(ctx);vm.runInContext(EXPENSE,ctx);const labels=vm.runInContext('FILTER_CONFIG.map(f=>f.label)',ctx);const other={inject:ctx.inject,formFields:{data:[{fieldname:'start_date'}]}};vm.createContext(other);vm.runInContext(SHIFT,other);other.validateDates('2026-10-20','2026-10-19');console.log(JSON.stringify([labels,other.formFields.data[0].error_message]));'''.replace('EXPENSE',json.dumps(expense)).replace('SHIFT',json.dumps(translator+'\n'+validate))
        labels,error=json.loads(subprocess.check_output(['node','-e',script],text=True))
        self.assertEqual(len(labels),5)
        self.assertTrue(all(label.startswith('translated ') for label in labels))
        self.assertEqual(error,'translated End Date cannot be before Start Date')
