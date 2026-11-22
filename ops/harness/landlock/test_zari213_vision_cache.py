import unittest, pathlib, tempfile, importlib.util, os
P=pathlib.Path(__file__).with_name("zari213-hermes-task-landlock.py")
S=importlib.util.spec_from_file_location("source",P); M=importlib.util.module_from_spec(S); S.loader.exec_module(M)
class VisionCacheTest(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        self.root=pathlib.Path(self.t.name); self.home=self.root/"home";self.home.mkdir()
        self.shared=self.root/"role";(self.shared/"cache").mkdir(parents=True)
        (self.shared/"cache"/"sentinel").write_text("untouched")
    def test_localization(self):
        (self.home/"cache").symlink_to(self.shared/"cache")
        M.localize_private_vision_cache(self.home,self.shared)
        self.assertFalse((self.home/"cache").is_symlink())
        self.assertEqual((self.home/"cache"/"vision").stat().st_mode & 0o777,0o700)
        self.assertEqual((self.shared/"cache"/"sentinel").read_text(),"untouched")
    def test_idempotent(self):
        M.localize_private_vision_cache(self.home,self.shared)
        M.localize_private_vision_cache(self.home,self.shared)
        self.assertTrue((self.home/"cache"/"vision").is_dir())
    def test_foreign_link_denied(self):
        other=self.root/"foreign";other.mkdir()
        (self.home/"cache").symlink_to(other)
        with self.assertRaises(ValueError):M.localize_private_vision_cache(self.home,self.shared)
        self.assertTrue((self.home/"cache").is_symlink())
    def test_symlink_in_vision_denied(self):
        (self.home/"cache").mkdir(mode=0o700)
        (self.home/"cache"/"vision").symlink_to(self.shared/"cache")
        with self.assertRaises(OSError):M.localize_private_vision_cache(self.home,self.shared)
    def test_bad_cache_mode_denied(self):
        (self.home/"cache").mkdir(mode=0o700)
        os.chmod(self.home/"cache", 0o755)  # fixed world-readable fixture despite umask 0077
        with self.assertRaises(ValueError):M.localize_private_vision_cache(self.home,self.shared)
class RoleAuthIsolationTests(unittest.TestCase):
    """Synthetic files only; never touch live OAuth or session credentials."""
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = pathlib.Path(self.t.name) / "hermes"
        self.root.mkdir(mode=0o700)
        (self.root / "profiles").mkdir(mode=0o700)
        self.role_dir = self.root / "profiles" / "cto"
        self.role_dir.mkdir(mode=0o700)
        self.auth = self.role_dir / "auth.json"
        self.uid = os.getuid()

    def create_private(self):
        self.auth.write_text('{"synthetic":"not-a-secret"}')
        self.auth.chmod(0o600)

    def test_private_role_auth_is_accepted(self):
        self.create_private()
        self.assertEqual(M.private_role_auth_file(self.root, "cto", self.uid), self.auth)

    def test_symlink_into_global_oauth_is_rejected(self):
        shared = self.root / "auth.json"
        shared.write_text('{}')
        shared.chmod(0o600)
        self.auth.symlink_to(shared)
        with self.assertRaisesRegex(ValueError, "private regular file"):
            M.private_role_auth_file(self.root, "cto", self.uid)

    def test_hardlink_into_global_oauth_is_rejected(self):
        shared = self.root / "auth.json"
        shared.write_text('{}')
        shared.chmod(0o600)
        os.link(shared, self.auth)
        with self.assertRaisesRegex(ValueError, "private regular file"):
            M.private_role_auth_file(self.root, "cto", self.uid)

    def test_missing_role_secret_fails_closed(self):
        with self.assertRaises(FileNotFoundError):
            M.private_role_auth_file(self.root, "cto", self.uid)

    def test_world_readable_secret_fails_closed(self):
        self.create_private()
        self.auth.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "private regular file"):
            M.private_role_auth_file(self.root, "cto", self.uid)

    def test_foreign_owner_claim_fails_closed(self):
        self.create_private()
        with self.assertRaisesRegex(ValueError, "directory is not private"):
            M.private_role_auth_file(self.root, "cto", self.uid + 1)

    def test_role_directory_symlink_is_rejected(self):
        self.create_private()
        self.role_dir.rename(self.root / "real-role")
        self.role_dir.symlink_to(self.root / "real-role", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "directory is not private"):
            M.private_role_auth_file(self.root, "cto", self.uid)

    def test_unapproved_role_cannot_read_codex_token(self):
        self.create_private()
        with self.assertRaisesRegex(ValueError, "not authorized"):
            M.private_role_auth_file(self.root, "harness-engineer", self.uid)


class TaskHermesHomeACLTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = pathlib.Path(self.t.name)
        self.task = self.root / "workspaces" / "task"
        self.task.mkdir(parents=True)
        self.home = self.task / "hermes-home"
        self.home.mkdir(mode=0o700)
        self.sessions = self.root / "persistent-sessions"
        self.sessions.mkdir()
        self.agent = "3a54e0b4-6526-4de5-a1fd-e66e205cb3b4"
        self.issue = "01a20413-9f18-70b2-b518-a0cd487c5b12"

    def verify(self, path, role="cto"):
        return M.verified_hermes_home_profile(self.task, path, self.sessions,
                                             self.agent, role, os.getuid())

    def test_own_private_task_home_allowed(self):
        self.assertEqual(self.verify(self.home), "cto")

    def test_task_home_world_readable_denied(self):
        self.home.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "not private"):
            self.verify(self.home)

    def test_task_home_symlink_denied(self):
        original = self.task / "authentic"
        self.home.rename(original)
        self.home.symlink_to(original, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            self.verify(self.home)

    def test_foreign_task_home_denied(self):
        foreign = self.root / "workspaces" / "foreign-task" / "hermes-home"
        foreign.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "outside own task/session"):
            self.verify(foreign)

    def test_own_persisted_session_allowed(self):
        own = self.sessions / self.agent / "cto" / self.issue
        own.mkdir(parents=True, mode=0o700)
        self.assertEqual(self.verify(own), "cto")

    def test_foreign_persisted_profile_denied(self):
        foreign = self.sessions / self.agent / "cho" / self.issue
        foreign.mkdir(parents=True, mode=0o700)
        with self.assertRaisesRegex(ValueError, "foreign Hermes profile"):
            self.verify(foreign)

    def test_foreign_persisted_agent_denied(self):
        other = self.sessions / "c1c8b457-e602-4eda-8ac7-67b994348878" / "cto" / self.issue
        other.mkdir(parents=True, mode=0o700)
        with self.assertRaisesRegex(ValueError, "outside own task/session"):
            self.verify(other)


if __name__=="__main__":unittest.main()
