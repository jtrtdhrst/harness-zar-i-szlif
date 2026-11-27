#!/usr/bin/env python3
"""Credential-free assertions for canonical repo helper and pinned install."""
import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
import io
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parent

def module(path,name):
    spec=importlib.util.spec_from_loader(name,SourceFileLoader(name,str(path)))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

BROKER=module(BASE/'multica-git-credential-broker.py','helper_checked_broker')
HELPER=module(BASE/'multica-zar-git-credential','helper_checked_cli')

class HelperSafety(unittest.TestCase):
    def test_allowlist_matches_broker_exactly(self):
        self.assertEqual(HELPER.ALLOWED,BROKER.ALLOWED_REPOS)
        self.assertEqual(len(HELPER.ALLOWED),2)
        self.assertFalse(any('miloszspyrka-code/' in x for x in HELPER.ALLOWED))

    def invoke(self,path):
        result=[]
        with patch.object(sys,'argv',['helper','get']),patch.object(sys,'stdin',io.StringIO('protocol=https\nhost=github.com\npath='+path+'\n')),patch.object(sys,'stdout',io.StringIO()) as out,patch.object(HELPER,'request',side_effect=lambda arg: result.append(arg) or {'ok':False,'error':'synthetic-deny'}):
            rc=HELPER.main()
            return rc,result,out.getvalue()

    def test_canonical_harness_and_product_reach_broker_without_secrets(self):
        for repo in sorted(BROKER.ALLOWED_REPOS):
            rc,calls,output=self.invoke(repo+'.git')
            self.assertEqual(rc,0);self.assertEqual(len(calls),1)
            self.assertEqual(calls[0]['path'],repo)
            self.assertNotIn('password=',output)

    def test_legacy_owner_and_foreign_repo_do_not_reach_broker(self):
        for repo in ('miloszspyrka-code/harness-zar-i-szlif','evil/project'):
            rc,calls,output=self.invoke(repo+'.git')
            self.assertEqual((rc,calls,output),(0,[],''))

    def test_install_requires_pinned_sha256_and_private_backup(self):
        src=(BASE/'multica-zar-git-credential').read_bytes()
        script=(BASE/'install-multica-zar-git-credential.sh').read_text()
        expected=re.search(r'^EXPECTED_SHA256="([0-9a-f]{64})"$',script,re.M)
        self.assertIsNotNone(expected)
        self.assertEqual(expected.group(1),hashlib.sha256(src).hexdigest())
        self.assertIn('[[ "$(id -u)" == "0" ]]',script)
        self.assertIn('install -m 0600',script)
        self.assertIn('mv -fT',script)
        self.assertIn('! -L "$DEST"',script)

if __name__=='__main__':unittest.main()
