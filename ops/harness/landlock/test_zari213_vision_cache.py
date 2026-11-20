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
if __name__=="__main__":unittest.main()
