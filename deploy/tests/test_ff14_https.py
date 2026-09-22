"""Deployment regressions: run python3 -m unittest discover -s deploy/tests -v."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class HttpsRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ff14-https-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.main = self.base / "yorozuya"
        self.game = self.base / "FF14Push"
        self.game.mkdir()
        (self.main / "deploy").mkdir(parents=True)
        for name in ("enable-ff14-https.sh", "docker-compose.ff14.yml", "docker-compose.ff14-game.yml"):
            shutil.copy(ROOT / "deploy" / name, self.main / "deploy" / name)
        for folder in (self.main, self.game):
            (folder / ".env").write_text("DOMAIN=example.com\n")
            (folder / "docker-compose.yml").write_text("services: {}\n")
        # Reproduce an already-installed legacy deployment; rerunning must work.
        shutil.copy(self.main / "deploy/docker-compose.ff14.yml", self.main / "docker-compose.override.yml")
        shutil.copy(self.main / "deploy/docker-compose.ff14-game.yml", self.game / "docker-compose.override.yml")
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.env = os.environ.copy()
        for key in ("COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "FF14_DIR"):
            self.env.pop(key, None)
        self.env.update(PATH=str(self.bin) + os.pathsep + self.env["PATH"], CALL_LOG=str(self.base / "calls"))
        self.command("docker", '''
import json, os, sys
args = sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
if args[:2] == ["compose", "version"]:
    print("5.5.0")
elif "config" in args and "--format" in args:
    print(json.dumps({"services": {"edge": {"environment": {"DOMAIN": "example.com"}}}}))
elif args[0] == "compose" and "ps" in args:
    print("edge-id" if args[-1] == "edge" else "game-id")
elif args[0] == "ps":
    print("edge-id")
''')
        self.command("curl", '''
import os, sys
args = sys.argv[1:]
if "--max-time" in args and args[args.index("--max-time") + 1] == "15":
    # Existing entry has valid TLS but wrong routing/HTTP 404. Allow repair.
    if os.environ.get("CASE") == "bad-cert": sys.exit(60)
    print("<html>wrong upstream</html>")
elif "-w" in args:
    game = ":19999/" in args[-1]
    if os.environ.get("CASE") == "bad-redirect": game = True
    print("301 https://example.com" + (":19999/" if game else "/"), end="")
elif args[-1].endswith("/api/health"):
    if os.environ.get("CASE") == "wrong-main": print("<html>game SPA</html>")
    else: print('{"status":"ok"}')
elif args[-1].endswith("/healthz"):
    print("ok")
elif args[-1].endswith("/health"):
    if os.environ.get("CASE") == "wrong-game": print('{"status":"ok"}')
    else: print('{"status":"ok","service":"eorzea-idle-backend"}')
else:
    sys.exit(22)
''')
        self.command("sleep", "pass\n")

    def command(self, name, code):
        path = self.bin / name
        path.write_text("#!/usr/bin/env python3\n" + code)
        path.chmod(0o755)

    def run_script(self, case="ok"):
        self.env["CASE"] = case
        return subprocess.run(["sh", str(self.main / "deploy/enable-ff14-https.sh")],
                              env=self.env, capture_output=True, text=True)

    def test_repair_legacy_routing_and_repeat(self):
        for _ in range(2):
            result = self.run_script()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = [json.loads(line) for line in (self.base / "calls").read_text().splitlines()]
        updates = [call for call in calls if "up" in call]
        self.assertEqual([call[-1] for call in updates[:3]], ["frontend", "frontend", "edge"])
        self.assertIn(str(self.main / "docker-compose.yml"), updates[0])

    def test_html_200_is_not_healthy_main(self):
        result = self.run_script("wrong-main")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("443/api/health 返回内容不属于预期服务 main", result.stderr)

    def test_main_health_is_not_healthy_game(self):
        result = self.run_script("wrong-game")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("19999/health 返回内容不属于预期服务 game-backend", result.stderr)

    def test_port_80_must_not_redirect_to_game(self):
        result = self.run_script("bad-redirect")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("80 HTTP 跳转异常", result.stderr)

    def test_bad_certificate_does_not_recreate_services(self):
        result = self.run_script("bad-cert")
        self.assertNotEqual(result.returncode, 0)
        calls = [json.loads(line) for line in (self.base / "calls").read_text().splitlines()]
        self.assertFalse(any("up" in call for call in calls))


class RoutingConfigTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI required (daemon not needed)")
    def test_main_upstream_is_unambiguous_on_shared_network(self):
        env = os.environ.copy()
        env.update(SECRET_KEY="test-only", ADMIN_PASSWORD="test-only", DOMAIN="example.com",
                   SITE_BASE_URL="https://example.com")
        result = subprocess.run([
            "docker", "compose", "--env-file", "/dev/null", "-f", "docker-compose.yml",
            "-f", "deploy/docker-compose.ff14.yml", "config", "--format", "json",
        ], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]
        frontend = services["frontend"]
        self.assertEqual(set(frontend["networks"]), {"default"})
        self.assertIn("yorozuya-web", frontend["networks"]["default"]["aliases"])
        self.assertFalse(frontend.get("ports"))
        self.assertEqual({str(p["published"]) for p in services["edge"]["ports"]}, {"80", "443", "19999"})
        main = (ROOT / "deploy/nginx/edge.conf.template").read_text()
        game = (ROOT / "deploy/nginx/ff14.conf.template").read_text()
        self.assertNotIn("http://frontend:", main)
        self.assertEqual(main.count("proxy_pass http://yorozuya-web:80;"), 3)
        self.assertNotIn("19999", main)
        self.assertIn("http://ff14-frontend:80", game)
        self.assertNotIn("listen 443", game)
        self.assertNotIn("listen 80", game)


if __name__ == "__main__":
    unittest.main()
