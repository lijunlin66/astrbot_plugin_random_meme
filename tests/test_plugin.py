"""Test astrbot_plugin_random_meme without sending messages or calling live APIs."""

import ast
import base64
import importlib.util
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import httpx
import yaml
from PIL import Image

PLUGIN_PATH = Path(__file__).resolve().parents[1] / "main.py"
spec = importlib.util.spec_from_file_location(
    "random_meme_validation_plugin", PLUGIN_PATH
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

GALLERY = [
    {"type": "file", "name": "first.gif", "path": "loop/first.gif"},
    {"type": "file", "name": "a b.PNG", "path": "loop/a b.PNG"},
    {"type": "file", "name": "README.md", "path": "loop/README.md"},
    {"type": "dir", "name": "nested.gif", "path": "loop/nested.gif"},
]
NAILONG_TREE = {
    "truncated": False,
    "tree": [
        {"type": "blob", "path": "gif/first.gif"},
        {"type": "blob", "path": "gif/second.gif"},
        {"type": "blob", "path": "images/static.JPG"},
        {"type": "blob", "path": "gif/README.md"},
        {"type": "tree", "path": "images/folder.png"},
        {"type": "blob", "path": "other/unrelated.jpg"},
        {"type": "blob", "path": "logo.png"},
    ],
}


class FakeEvent:
    def chain_result(self, chain):
        return ("chain", chain)

    def image_result(self, url):
        return ("image", url)

    def plain_result(self, text):
        return ("plain", text)


class RandomMemeTests(unittest.IsolatedAsyncioTestCase):
    def test_plugin_identity_and_icon(self):
        root = PLUGIN_PATH.parent
        metadata = yaml.safe_load((root / "metadata.yaml").read_text(encoding="utf-8"))
        self.assertEqual("astrbot_plugin_random_meme", metadata["name"])
        self.assertEqual("lijunlin66", metadata["author"])
        self.assertEqual("1.2.0", metadata["version"])
        self.assertEqual(
            "https://github.com/lijunlin66/astrbot_plugin_random_meme", metadata["repo"]
        )
        self.assertIn(
            "astrbot_plugin_doro", (root / "ATTRIBUTION.md").read_text(encoding="utf-8")
        )
        with Image.open(root / "logo.png") as icon:
            self.assertEqual("PNG", icon.format)
            self.assertEqual((475, 475), icon.size)

    def setUp(self):
        self.plugin = module.RandomStickerPlugin.__new__(module.RandomStickerPlugin)
        self.plugin.config = {"cooldown_period": 5}
        self.plugin.last_called_times = {}
        self.plugin._sticker_urls = {}
        self.plugin._repo_sticker_names = {}
        self.plugin.max_retries = 3
        self.event = FakeEvent()
        self.requests = []

    async def run_command(
        self, responses, command="doro", calls=1, reset_cooldown=True
    ):
        """Capture command results using an in-memory HTTP transport.

        Args:
            responses: HTTP responses or request exceptions to return in order.
            command: Plugin command to execute.
            calls: Number of command invocations, with cooldown reset between calls.
            reset_cooldown: Whether to clear previous cooldowns before each invocation.

        Returns:
            A list containing the captured results for each invocation.
        """
        original_client = httpx.AsyncClient
        pending = list(responses)

        def respond(request):
            self.requests.append(request)
            response = pending.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        with (
            patch.object(
                module.httpx,
                "AsyncClient",
                side_effect=lambda **kwargs: original_client(
                    transport=httpx.MockTransport(respond), **kwargs
                ),
            ),
            patch.object(module.asyncio, "sleep", new=AsyncMock()),
        ):
            results = []
            for _ in range(calls):
                if reset_cooldown:
                    self.plugin.last_called_times.clear()
                results.append(
                    [item async for item in getattr(self.plugin, command)(self.event)]
                )
            return results

    async def test_gallery_images_and_cache(self):
        results = await self.run_command([httpx.Response(200, json=GALLERY)], calls=2)
        self.assertEqual(1, len(self.requests))
        self.assertEqual("api.github.com", self.requests[0].url.host)
        self.assertEqual(2, len(self.plugin._sticker_urls["doro"]))
        self.assertIn(
            "https://cdn.jsdmirror.com/gh/1143520/doro@main/loop/a%20b.PNG",
            self.plugin._sticker_urls["doro"],
        )
        for result in results:
            self.assertEqual("image", result[0][0])
            self.assertIn(result[0][1], self.plugin._sticker_urls["doro"])

    async def test_html_response_has_clear_error(self):
        results = await self.run_command(
            [httpx.Response(200, text="<!DOCTYPE html><title>Domain for sale</title>")]
        )
        self.assertEqual("plain", results[0][0][0])
        self.assertIn("接口可能已失效", results[0][0][1])
        self.assertNotIn("未知错误", results[0][0][1])
        self.assertIn("doro", self.plugin.last_called_times)

    async def test_empty_gallery_returns_error(self):
        results = await self.run_command([httpx.Response(200, json=[])])
        self.assertEqual("plain", results[0][0][0])
        self.assertIn("未能", results[0][0][1])

    async def test_cheshire_image_response(self):
        image = io.BytesIO()
        Image.new("RGB", (8, 8), (20, 100, 200)).save(image, format="PNG")
        payload = image.getvalue()
        results = await self.run_command(
            [
                httpx.Response(
                    200, content=payload, headers={"content-type": "image/png"}
                )
            ],
            command="chaijun",
        )
        self.assertEqual("https://api.hlz7.com/chajun", str(self.requests[0].url))
        self.assertEqual("chain", results[0][0][0])
        component = results[0][0][1][0]
        self.assertEqual(payload, base64.b64decode(component.file.split("//", 1)[1]))
        self.assertIn("柴郡", self.plugin.last_called_times)
        self.assertNotIn("doro", self.plugin.last_called_times)

    async def test_cheshire_html_response_has_clear_error(self):
        results = await self.run_command(
            [httpx.Response(200, text="<html>Unavailable</html>")], command="chaijun"
        )
        self.assertIn("接口可能已失效", results[0][0][1])
        self.assertNotIn("未知错误", results[0][0][1])

    async def test_cheshire_image_cooldown(self):
        image = io.BytesIO()
        Image.new("RGB", (8, 8)).save(image, format="PNG")
        await self.run_command(
            [
                httpx.Response(
                    200, content=image.getvalue(), headers={"content-type": "image/png"}
                )
            ],
            command="chaijun",
        )
        results = [item async for item in self.plugin.chaijun(self.event)]
        self.assertEqual("plain", results[0][0])
        self.assertIn("请稍等", results[0][1])

    async def test_http_failure_retries_then_succeeds(self):
        results = await self.run_command(
            [httpx.Response(503), httpx.Response(200, json=GALLERY)]
        )
        self.assertEqual(2, len(self.requests))
        self.assertEqual("image", results[0][0][0])

    async def test_network_failure_exhausts_retries(self):
        results = await self.run_command([httpx.ConnectError("offline")] * 3)
        self.assertEqual(3, len(self.requests))
        self.assertEqual("plain", results[0][0][0])
        self.assertIn("请求Doro API失败", results[0][0][1])

    async def test_maintenance_response_stops_retries(self):
        results = await self.run_command([httpx.Response(402)])
        self.assertEqual(1, len(self.requests))
        self.assertIn("维护", results[0][0][1])

    async def test_cooldown_does_not_send_cached_image(self):
        await self.run_command([httpx.Response(200, json=GALLERY)])
        results = [item async for item in self.plugin.doro(self.event)]
        self.assertEqual("plain", results[0][0])
        self.assertIn("请稍等", results[0][1])

    def test_public_commands_and_removed_legacy_command(self):
        tree = ast.parse(PLUGIN_PATH.read_text(encoding="utf-8"))
        names = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "command"
                ):
                    names.append(decorator.args[0].value)
        self.assertCountEqual(
            ["doro", "柴郡", "龙图", "奶龙", "塔菲", "牢大", "呆猫"], names
        )
        self.assertFalse(hasattr(self.plugin, "cheshire"))
        self.assertFalse(hasattr(self.plugin, "nailong_gif"))
        self.assertFalse(hasattr(self.plugin, "nailong_image"))

    async def test_dragon_binary_image_and_category(self):
        image = io.BytesIO()
        Image.new("RGB", (8, 8)).save(image, format="JPEG")
        payload = image.getvalue()
        results = await self.run_command(
            [
                httpx.Response(
                    200, content=payload, headers={"content-type": "image/jpeg"}
                )
            ],
            command="longtu",
        )
        self.assertEqual(
            "https://oiapi.net/api/FunBoxEmoji?0=dragon", str(self.requests[0].url)
        )
        self.assertEqual("chain", results[0][0][0])
        self.assertEqual(
            payload, base64.b64decode(results[0][0][1][0].file.split("//", 1)[1])
        )
        self.assertIn("龙图", self.plugin.last_called_times)

    async def test_nailong_union_has_equal_weight_and_separate_cache(self):
        await self.run_command([httpx.Response(200, json=GALLERY)])
        picks = iter([0, -1])
        with patch.object(
            module.random,
            "choice",
            side_effect=lambda population: population[next(picks)],
        ) as choose:
            results = await self.run_command(
                [httpx.Response(200, json=NAILONG_TREE)], command="nailong", calls=2
            )
        self.assertEqual(2, len(self.requests))
        self.assertEqual(
            "/repos/GeorgeNaNN/nailong-memes/git/trees/main", self.requests[-1].url.path
        )
        self.assertEqual("1", self.requests[-1].url.params.get("recursive"))
        base = "https://cdn.jsdmirror.com/gh/GeorgeNaNN/nailong-memes@main/"
        expected = [
            base + path
            for path in ("gif/first.gif", "gif/second.gif", "images/static.JPG")
        ]
        self.assertEqual(expected, self.plugin._sticker_urls["奶龙"])
        for call in choose.call_args_list:
            self.assertEqual(expected, call.args[0])
        self.assertEqual([[("image", expected[0])], [("image", expected[-1])]], results)
        self.assertNotEqual(
            self.plugin._sticker_urls["doro"], self.plugin._sticker_urls["奶龙"]
        )

    async def test_cooldowns_are_independent_across_categories(self):
        self.plugin.last_called_times["柴郡"] = module.time.time()
        results = await self.run_command(
            [httpx.Response(200, json=NAILONG_TREE)],
            command="nailong",
            reset_cooldown=False,
        )
        self.assertEqual("image", results[0][0][0])
        self.assertIn("奶龙", self.plugin.last_called_times)
        self.assertIn("柴郡", self.plugin.last_called_times)

    async def test_empty_image_retries_without_sending(self):
        results = await self.run_command(
            [
                httpx.Response(200, content=b"", headers={"content-type": "image/png"})
                for _ in range(3)
            ],
            command="longtu",
        )
        self.assertEqual(3, len(self.requests))
        self.assertEqual("plain", results[0][0][0])
        self.assertIn("请求龙图 API失败", results[0][0][1])

    async def test_nailong_gif_and_static_share_one_cooldown(self):
        await self.run_command(
            [httpx.Response(200, json=NAILONG_TREE)], command="nailong"
        )
        results = [reply async for reply in self.plugin.nailong(self.event)]
        self.assertEqual("plain", results[0][0])
        self.assertIn("请稍等", results[0][1])
        self.assertEqual({"奶龙"}, set(self.plugin.last_called_times))

    async def test_truncated_nailong_tree_retries_without_partial_images(self):
        results = await self.run_command(
            [
                httpx.Response(200, json={**NAILONG_TREE, "truncated": True})
                for _ in range(3)
            ],
            command="nailong",
        )
        self.assertEqual(3, len(self.requests))
        self.assertEqual("plain", results[0][0][0])
        self.assertNotIn("奶龙", self.plugin._sticker_urls)

    async def test_empty_nailong_tree_returns_clear_error(self):
        results = await self.run_command(
            [httpx.Response(200, json={"tree": [], "truncated": False})],
            command="nailong",
        )
        self.assertEqual("plain", results[0][0][0])
        self.assertIn("未能", results[0][0][1])

    async def test_taffy_fetches_one_gif_from_github_and_has_separate_cooldown(self):
        image = io.BytesIO()
        frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
        frames[0].save(image, format="GIF", save_all=True, append_images=frames[1:])
        payload = image.getvalue()
        self.plugin.last_called_times["奶龙"] = module.time.time()
        name = "002-永雏塔菲表情包.gif"
        with TemporaryDirectory() as directory:
            self.plugin.repo_dir = Path(directory)
            first, second = await self.run_command(
                [
                    httpx.Response(
                        200,
                        json=[
                            {"name": name, "type": "file"},
                            {"name": "folder.gif", "type": "dir"},
                            {"name": "static.png", "type": "file"},
                            {"name": "../invalid.gif", "type": "file"},
                        ],
                    ),
                    httpx.Response(200, content=payload),
                ],
                command="taffy",
                calls=2,
                reset_cooldown=False,
            )

        self.assertEqual(2, len(self.requests))
        self.assertEqual("api.github.com", self.requests[0].url.host)
        self.assertEqual(
            "/repos/lijunlin66/taffy_meme/contents/taffy", self.requests[0].url.path
        )
        self.assertEqual(module.MEME_REPO_REVISION, self.requests[0].url.params["ref"])
        self.assertTrue(self.requests[1].url.path.endswith("/" + name))
        self.assertEqual(
            "application/vnd.github.raw+json", self.requests[1].headers["Accept"]
        )
        self.assertEqual(1, len(first))
        kind, chain = first[0]
        self.assertEqual("chain", kind)
        self.assertEqual(1, len(chain))
        self.assertEqual(payload, base64.b64decode(chain[0].file.split("//", 1)[1]))
        self.assertIn("请稍等", second[0][1])
        self.assertEqual({"奶龙", "塔菲"}, self.plugin.last_called_times.keys())

    async def test_taffy_uses_local_snapshot_when_github_is_unavailable(self):
        image = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(image, format="GIF")
        payload = image.getvalue()
        with TemporaryDirectory() as directory:
            self.plugin.repo_dir = Path(directory)
            gallery = self.plugin.repo_dir / "taffy"
            gallery.mkdir()
            (gallery / "single-frame.gif").write_bytes(payload)
            results = await self.run_command([httpx.Response(403)], command="taffy")
        self.assertEqual(1, len(self.requests))
        kind, chain = results[0][0]
        self.assertEqual("chain", kind)
        self.assertEqual(payload, base64.b64decode(chain[0].file.split("//", 1)[1]))

    async def test_taffy_handles_a_missing_gallery(self):
        with TemporaryDirectory() as directory:
            self.plugin.repo_dir = Path(directory)
            results = await self.run_command([httpx.Response(503)], command="taffy")
        self.assertEqual("plain", results[0][0][0])
        self.assertIn("暂无可用图片", results[0][0][1])

    async def test_new_galleries_have_separate_catalogues_and_cooldowns(self):
        with TemporaryDirectory() as directory:
            self.plugin.repo_dir = Path(directory)
            for handler, folder, color in [
                ("laoda", "牢大", "red"),
                ("daimao", "呆猫", "blue"),
            ]:
                name = f"{folder}.gif"
                image = io.BytesIO()
                Image.new("RGB", (8, 8), color).save(image, format="GIF")
                payload = image.getvalue()
                first, second = await self.run_command(
                    [
                        httpx.Response(200, json=[{"name": name, "type": "file"}]),
                        httpx.Response(200, content=payload),
                    ],
                    command=handler,
                    calls=2,
                    reset_cooldown=False,
                )
                kind, chain = first[0]
                self.assertEqual("chain", kind)
                self.assertEqual(
                    payload, base64.b64decode(chain[0].file.split("//", 1)[1])
                )
                self.assertIn("请稍等", second[0][1])
                self.assertTrue(self.requests[-2].url.path.endswith(f"/{folder}"))
                self.assertTrue(
                    self.requests[-1].url.path.endswith(f"/{folder}/{name}")
                )
                self.assertEqual([name], self.plugin._repo_sticker_names[folder])

        self.assertEqual(4, len(self.requests))
        self.assertEqual({"牢大", "呆猫"}, self.plugin.last_called_times.keys())
