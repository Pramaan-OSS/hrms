"""Dismissed mobile installation offers stay dismissed during the browser session."""
import json
from pathlib import Path
import subprocess
import unittest


class InstallPromptTests(unittest.TestCase):
    def test_dismissal_survives_a_page_reload_and_storage_failure_is_safe(self):
        source = (Path(__file__).resolve().parents[1] / 'frontend/src/components/InstallPrompt.vue').read_text().split('<script setup>')[1].split('</script>')[0]
        source = '\n'.join(line for line in source.splitlines() if not line.startswith('import '))
        program = r'''
const vm=require('vm'),store=new Map();
function page(fail=false){const events={},watchers=[];const ctx={ref:value=>({value}),watch:(r,cb)=>watchers.push(cb),sessionStorage:{getItem:k=>{if(fail)throw Error();return store.get(k)},setItem:(k,v)=>{if(fail)throw Error();store.set(k,v)}},window:{navigator:{userAgent:'test'},addEventListener:(k,fn)=>events[k]=fn},console:{log:()=>{}}};vm.createContext(ctx);vm.runInContext(SOURCE,ctx);events.beforeinstallprompt({preventDefault(){}});return {visible:vm.runInContext('showDialog.value',ctx),close:()=>watchers[0](false,true)}}
const first=page();first.close();console.log(JSON.stringify([first.visible,page().visible,page(true).visible]));
'''.replace('SOURCE', json.dumps(source))
        self.assertEqual(json.loads(subprocess.check_output(['node', '-e', program], text=True)), [True, False, True])
