#!/usr/bin/env python3
"""Credential-free broker provenance and role-isolation regressions."""
import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('broker_security', HERE / 'multica-git-credential-broker.py')
broker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(broker)
H='jtrtdhrst/harness-zar-i-szlif'
P='jtrtdhrst/zar-i-szlif'

class PrivateInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.base.chmod(0o700)
        self.owner=patch.object(broker,'TRUSTED_UID',os.getuid())
        self.owner.start();self.addCleanup(self.owner.stop)
        self.file=self.base/'role.json'
        self.file.write_text('{"role":"implementer-harness"}')
        self.file.chmod(0o600)

    def test_private_single_link_regular_file_is_admitted(self):
        self.assertEqual(broker.read_private_json(self.file)['role'],'implementer-harness')

    def test_world_readable_file_is_denied(self):
        self.file.chmod(0o644)
        with self.assertRaises(broker.UntrustedCredentialError):broker.read_private_json(self.file)

    def test_world_writable_role_map_is_denied(self):
        self.file.chmod(0o666)
        with self.assertRaises(broker.UntrustedCredentialError):broker.read_private_json(self.file)

    def test_symlink_is_denied(self):
        alias=self.base/'link.json';alias.symlink_to(self.file)
        with self.assertRaises(broker.UntrustedCredentialError):broker.read_private_json(alias)

    def test_hardlink_is_denied(self):
        os.link(self.file,self.base/'second-link.json')
        with self.assertRaises(broker.UntrustedCredentialError):broker.read_private_json(self.file)

    def test_nonprivate_parent_is_denied(self):
        self.base.chmod(0o755)
        with self.assertRaises(broker.UntrustedCredentialError):broker.read_private_json(self.file)

    def test_wrong_owner_is_denied(self):
        with patch.object(broker,'TRUSTED_UID',os.getuid()+10000):
            with self.assertRaises(broker.UntrustedCredentialError):broker.read_private_json(self.file)

    def test_untrusted_token_is_not_refreshed_into_success(self):
        self.file.unlink()
        token=self.base/'implementer-harness.json'
        token.write_text('{}');token.chmod(0o644)
        with patch.object(broker,'refresh_tokens') as refresh:
            with self.assertRaises(broker.UntrustedCredentialError):
                broker.token_for_role(self.base,'implementer-harness')
            refresh.assert_not_called()

class HandlerScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.map=self.root/'agent-roles.json'
        self.map.write_text(json.dumps({'agent':'implementer-harness'}));self.map.chmod(0o600)
        self.owner=patch.object(broker,'TRUSTED_UID',os.getuid());self.owner.start();self.addCleanup(self.owner.stop)

    def request(self, repo):
        h=object.__new__(broker.Handler)
        h.request=Mock();h.request.getsockopt.return_value=struct.pack('3i',800,997,981)
        h.rfile=io.BytesIO(json.dumps({'op':'credential','protocol':'https','host':'github.com','path':repo+'.git'}).encode()+b'\n')
        h.server=SimpleNamespace(daemon_unit='fake',pidfile=None,allow_any_daemon=False,roles_file=self.map,tokens=self.root)
        outputs=[];h.reply=outputs.append
        with patch.object(broker,'task_agent',return_value=('agent','task')),patch.object(broker,'token_for_role',return_value={'token':'synthetic-not-a-live-token','expires_at':'2099-01-01T00:00:00Z'}) as get_token:
            h.handle()
        return outputs[0],get_token.call_count

    def test_current_project_only(self):
        result,count=self.request(H)
        self.assertTrue(result['ok']);self.assertEqual(result['role'],'implementer-harness');self.assertEqual(count,1)

    def test_cross_project_request_denied_before_token_lookup(self):
        result,count=self.request(P)
        self.assertEqual(result['error'],'repository_not_allowed');self.assertEqual(count,0)

    def test_world_writable_role_map_never_reaches_token_lookup(self):
        self.map.chmod(0o666)
        result,count=self.request(H)
        self.assertEqual(result['error'],'credential_unavailable');self.assertEqual(count,0)

    def test_legacy_base_role_is_not_a_broker_actor(self):
        self.map.write_text(json.dumps({'agent':'implementer'}))
        result,count=self.request(H)
        self.assertEqual(result['error'],'agent_not_mapped');self.assertEqual(count,0)

if __name__=='__main__':unittest.main()
