"""Initializing print controls waits for the document before rendering."""
import ast
import json
from pathlib import Path
import subprocess
import unittest


class PrintPreviewTests(unittest.TestCase):
    def test_early_control_changes_wait_and_saved_document_changes_render(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'docker/patch-framework.py').read_text())
        replacements=[node.value.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='new' for t in node.targets) and isinstance(node.value,ast.Constant)]
        guard=next(s for s in replacements if 'if (!this.frm?.doc) return;' in s)
        method=guard.replace('preview() {','function preview() {')+'\n}'
        script='''const vm=require('vm');const ctx={};vm.createContext(ctx);vm.runInContext(METHOD,ctx);let renders=0;const view={toggle_style_picker:()=>renders++};ctx.preview.call(view);view.frm={doc:{name:'TEST-1'}};ctx.preview.call(view);console.log(renders);'''.replace('METHOD',json.dumps(method))
        self.assertEqual(subprocess.check_output(['node','-e',script],text=True).strip(),'1')
