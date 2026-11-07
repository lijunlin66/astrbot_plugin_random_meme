"""Random meme plugin by lijunlin66, based on astrbot_plugin_doro.

Created: 2026-10-26. License: AGPL-3.0.
Original project: https://github.com/2356820887/astrbot_plugin_doro
Original author: Shingetsu (shingetsu), version 0.0.6.
Modified and maintained by lijunlin66.
"""

import asyncio
import json
import random
import time
from pathlib import Path
from urllib.parse import quote

import httpx
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, StarTools

GALLERY_BASES = {
    "doro": "https://cdn.jsdmirror.com/gh/1143520/doro@main/",
    "奶龙": "https://cdn.jsdmirror.com/gh/GeorgeNaNN/nailong-memes@main/",
}
IMAGE_SUFFIXES = (".gif", ".png", ".jpg", ".jpeg", ".webp")
MEME_REPO_CONTENTS = "https://api.github.com/repos/lijunlin66/taffy_meme/contents"
MEME_REPO_REVISION = "9983139039d705048e1225607f4aba1bdc16cbd3"


class RandomStickerPlugin(Star):
    """Fetch random stickers with independent cooldowns and bounded retries."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.repo_dir = (
            StarTools.get_data_dir("astrbot_plugin_random_meme")
            / "taffy"
            / MEME_REPO_REVISION
        )
        self._repo_sticker_names: dict[str, list[str]] = {}
        self.last_called_times = {}
        self._sticker_urls = {}
        self.max_retries = 3

    def _is_on_cooldown(self, command_name: str) -> tuple[bool, float]:
        """Check the cooldown for one sticker category.

        Args:
            command_name: Category used as the cooldown key.

        Returns:
            Whether the category is cooling down and the remaining seconds.
        """
        elapsed = time.time() - self.last_called_times.get(command_name, 0)
        remaining = max(0, self.config.get("cooldown_period", 5) - elapsed)
        return remaining > 0, remaining

    async def _get_random_sticker(
        self,
        event: AstrMessageEvent,
        command_name: str,
        api_url: str,
        entity_name: str,
    ):
        """Fetch an image or gallery entry and construct one reply.

        Args:
            event: Incoming event used to construct the reply.
            command_name: Category used for cooldowns and gallery caching.
            api_url: Image or gallery API endpoint.
            entity_name: Category name displayed in user messages.

        Yields:
            An image reply or a descriptive error or cooldown reply.
        """
        on_cooldown, remaining = self._is_on_cooldown(command_name)
        if on_cooldown:
            yield event.plain_result(
                f"请稍等，距离下一次获取随机{entity_name}表情包还有 {remaining:.0f} 秒。"
            )
            return

        for attempt in range(1, self.max_retries + 1):
            try:
                urls = self._sticker_urls.get(command_name, [])
                if not urls:
                    async with httpx.AsyncClient(
                        timeout=15, follow_redirects=True
                    ) as client:
                        response = await client.get(api_url)
                        response.raise_for_status()
                    if response.headers.get("content-type", "").startswith("image/"):
                        if not response.content:
                            raise httpx.RequestError(
                                "Empty image response", request=response.request
                            )
                        self.last_called_times[command_name] = time.time()
                        yield event.chain_result([Image.fromBytes(response.content)])
                        return

                    data = response.json()
                    base_url = GALLERY_BASES.get(command_name)
                    if base_url:
                        paths = []
                        if command_name == "奶龙" and isinstance(data, dict):
                            if data.get("truncated"):
                                raise httpx.RequestError(
                                    "Incomplete gallery tree", request=response.request
                                )
                            paths = [
                                item["path"]
                                for item in data.get("tree", [])
                                if item.get("type") == "blob"
                                and item.get("path", "").split("/", 1)[0]
                                in ("gif", "images")
                                and item["path"].lower().endswith(IMAGE_SUFFIXES)
                            ]
                        elif isinstance(data, list):
                            paths = [
                                item["path"]
                                for item in data
                                if item.get("type") == "file"
                                and item.get("name", "")
                                .lower()
                                .endswith(IMAGE_SUFFIXES)
                            ]
                        urls = [base_url + quote(path) for path in paths]
                        if urls:
                            self._sticker_urls[command_name] = urls

                if not urls:
                    logger.warning("%s API returned no usable images", entity_name)
                    self.last_called_times[command_name] = time.time()
                    yield event.plain_result(
                        f"未能从{entity_name} API获取到有效的表情包，请稍后再试。"
                    )
                    return
                self.last_called_times[command_name] = time.time()
                yield event.image_result(random.choice(urls))
                return

            except json.JSONDecodeError:
                logger.error("%s API returned invalid JSON", entity_name)
                self.last_called_times[command_name] = time.time()
                yield event.plain_result(
                    f"{entity_name} API返回了无效数据，接口可能已失效，请联系管理员更新。"
                )
                return
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 402:
                    logger.warning("%s API is unavailable (402)", entity_name)
                    self.last_called_times[command_name] = time.time()
                    yield event.plain_result(
                        f"{entity_name} API 链接可能正在维护中，请稍后再试。"
                    )
                    return
                logger.warning(
                    "%s API attempt %s failed: %s", entity_name, attempt, exc
                )
                if attempt == self.max_retries:
                    yield event.plain_result(
                        f"{entity_name} API 请求失败，错误码：{exc.response.status_code}"
                    )
            except httpx.RequestError as exc:
                logger.warning(
                    "%s API attempt %s failed: %s", entity_name, attempt, exc
                )
                if attempt == self.max_retries:
                    yield event.plain_result(
                        f"请求{entity_name} API失败，请检查网络或API是否可用。"
                    )
            except Exception:
                logger.exception("Unexpected %s sticker error", entity_name)
                self.last_called_times[command_name] = time.time()
                yield event.plain_result(f"处理{entity_name}请求时发生未知错误。")
                return

            if attempt < self.max_retries:
                await asyncio.sleep(2 ** (attempt - 1))
        self.last_called_times[command_name] = time.time()

    @filter.command("doro")
    async def doro(self, event: AstrMessageEvent):
        """获取一张随机 Doro 表情包。"""
        async for result in self._get_random_sticker(
            event,
            "doro",
            "https://api.github.com/repos/1143520/doro/contents/loop",
            "Doro",
        ):
            yield result

    @filter.command("柴郡")
    async def chaijun(self, event: AstrMessageEvent):
        """获取一张随机柴郡表情包。"""
        async for result in self._get_random_sticker(
            event, "柴郡", "https://api.hlz7.com/chajun", "柴郡"
        ):
            yield result

    @filter.command("龙图")
    async def longtu(self, event: AstrMessageEvent):
        """获取一张随机龙图表情包。"""
        async for result in self._get_random_sticker(
            event, "龙图", "https://oiapi.net/api/FunBoxEmoji?0=dragon", "龙图"
        ):
            yield result

    @filter.command("奶龙")
    async def nailong(self, event: AstrMessageEvent):
        """从全部奶龙 GIF 和静态图中随机获取一张表情包。"""
        async for result in self._get_random_sticker(
            event,
            "奶龙",
            "https://api.github.com/repos/GeorgeNaNN/nailong-memes/git/trees/main?recursive=1",
            "奶龙",
        ):
            yield result

    async def _load_repo_names(
        self, client: httpx.AsyncClient, folder_url: str, local_dir: Path
    ) -> list[str]:
        try:
            response = await client.get(folder_url)
            response.raise_for_status()
            entries = response.json()
            if not isinstance(entries, list):
                raise ValueError("Expected a GitHub directory listing")
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("获取 GitHub %s 图库清单失败：%s", local_dir.name, exc)
            return [path.name for path in local_dir.glob("*.gif") if path.is_file()]
        names = []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("type") != "file":
                continue
            name = entry.get("name")
            if (
                isinstance(name, str)
                and name.lower().endswith(".gif")
                and "/" not in name
                and "\\" not in name
            ):
                names.append(name)
        return names

    async def _get_repo_sticker(
        self, event: AstrMessageEvent, command_name: str, folder: str
    ):
        on_cooldown, remaining = self._is_on_cooldown(command_name)
        if on_cooldown:
            yield event.plain_result(
                f"请稍等，距离下一次获取随机{command_name}表情包还有 {remaining:.0f} 秒。"
            )
            return

        self.last_called_times[command_name] = time.time()
        folder_url = f"{MEME_REPO_CONTENTS}/{quote(folder)}"
        local_dir = self.repo_dir / folder
        async with httpx.AsyncClient(
            timeout=8,
            params={"ref": MEME_REPO_REVISION},
        ) as client:
            names = self._repo_sticker_names.get(folder)
            if not names:
                names = await self._load_repo_names(client, folder_url, local_dir)
                if names:
                    self._repo_sticker_names[folder] = names
            for name in random.sample(names, min(self.max_retries, len(names))):
                try:
                    payload = await asyncio.to_thread((local_dir / name).read_bytes)
                except OSError:
                    try:
                        response = await client.get(
                            f"{folder_url}/{quote(name)}",
                            headers={"Accept": "application/vnd.github.raw+json"},
                        )
                        response.raise_for_status()
                        payload = response.content
                    except httpx.HTTPError as exc:
                        logger.warning(
                            "获取 GitHub %s 图片 %s 失败：%s", folder, name, exc
                        )
                        continue
                if payload.startswith((b"GIF87a", b"GIF89a")):
                    yield event.chain_result([Image.fromBytes(payload)])
                    return
                logger.warning("%s 图库文件 %s 不是有效的 GIF 文件", folder, name)

        yield event.plain_result(f"{command_name}图库暂无可用图片，请稍后再试。")

    @filter.command("塔菲")
    async def taffy(self, event: AstrMessageEvent):
        """随机获取一张永雏塔菲 GIF 表情包。"""
        async for result in self._get_repo_sticker(event, "塔菲", "taffy"):
            yield result

    @filter.command("牢大")
    async def laoda(self, event: AstrMessageEvent):
        """随机获取一张科比牢大 GIF 表情包。"""
        async for result in self._get_repo_sticker(event, "牢大", "牢大"):
            yield result

    @filter.command("呆猫")
    async def daimao(self, event: AstrMessageEvent):
        """随机获取一张怪猎呆猫 GIF 表情包。"""
        async for result in self._get_repo_sticker(event, "呆猫", "呆猫"):
            yield result
