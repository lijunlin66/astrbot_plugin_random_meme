"""Random meme plugin by lijunlin66, based on astrbot_plugin_doro.

Created: 2026-10-26. Version: 1.0.0. License: AGPL-3.0.
Original project: https://github.com/2356820887/astrbot_plugin_doro
Original author: Shingetsu (shingetsu), version 0.0.6.
Modified and maintained by lijunlin66.
"""

import asyncio
import json
import logging
import random
import time
from urllib.parse import quote

import httpx
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, register

GALLERY_BASES = {
    "doro": "https://cdn.jsdmirror.com/gh/1143520/doro@main/",
    "奶龙": "https://cdn.jsdmirror.com/gh/GeorgeNaNN/nailong-memes@main/",
}


@register(
    "astrbot_plugin_random_meme",
    "lijunlin66",
    "随机获取 Doro、柴郡、龙图及奶龙动静态表情包",
    "1.0.0",
)
class RandomStickerPlugin(Star):
    """Fetch random stickers with independent cooldowns and bounded retries."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.logger = logging.getLogger(__name__)
        self.cooldown_period = config.get("cooldown_period", 5)
        self.last_called_times = {}
        self._sticker_urls = {}
        self.max_retries = 3

    async def initialize(self):
        self.logger.info("astrbot_plugin_random_meme 1.0.0 initialized")

    def _is_on_cooldown(self, command_name: str) -> tuple[bool, float]:
        """Check the cooldown for one sticker category.

        Args:
            command_name: Category used as the cooldown key.

        Returns:
            Whether the category is cooling down and the remaining seconds.
        """
        elapsed = time.time() - self.last_called_times.get(command_name, 0)
        remaining = max(0, self.cooldown_period - elapsed)
        return remaining > 0, remaining

    async def _get_random_sticker(
        self, event: AstrMessageEvent, command_name: str, api_url: str, entity_name: str
    ):
        """Fetch an image or gallery entry and construct one reply.

        Args:
            event: Incoming event used to construct the reply.
            command_name: Category used for cooldowns and gallery caching.
            api_url: Image endpoint or GitHub gallery endpoint.
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

        for attempt in range(self.max_retries):
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
                    if command_name == "奶龙" and isinstance(data, dict):
                        if data.get("truncated"):
                            raise httpx.RequestError(
                                "Incomplete gallery tree", request=response.request
                            )
                        data = [
                            {
                                "type": "file",
                                "name": item["path"].rsplit("/", 1)[-1],
                                "path": item["path"],
                            }
                            for item in data.get("tree", [])
                            if item.get("type") == "blob"
                            and item.get("path", "").split("/", 1)[0]
                            in ("gif", "images")
                        ]
                    if command_name in GALLERY_BASES and isinstance(data, list):
                        urls = [
                            GALLERY_BASES[command_name] + quote(item["path"])
                            for item in data
                            if item.get("type") == "file"
                            and item.get("name", "")
                            .lower()
                            .endswith((".gif", ".png", ".jpg", ".jpeg", ".webp"))
                        ]
                        self._sticker_urls[command_name] = urls

                if not urls:
                    self.logger.warning("%s API returned no usable images", entity_name)
                    self.last_called_times[command_name] = time.time()
                    yield event.plain_result(
                        f"未能从{entity_name} API获取到有效的表情包，请稍后再试。"
                    )
                    return
                self.last_called_times[command_name] = time.time()
                yield event.image_result(random.choice(urls))
                return

            except json.JSONDecodeError:
                self.logger.error("%s API returned invalid JSON", entity_name)
                self.last_called_times[command_name] = time.time()
                yield event.plain_result(
                    f"{entity_name} API返回了无效数据，接口可能已失效，请联系管理员更新。"
                )
                return
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 402:
                    self.logger.warning("%s API is unavailable (402)", entity_name)
                    self.last_called_times[command_name] = time.time()
                    yield event.plain_result(
                        f"{entity_name} API 链接可能正在维护中，请稍后再试。"
                    )
                    return
                self.logger.warning(
                    "%s API attempt %s failed: %s", entity_name, attempt + 1, exc
                )
                if attempt == self.max_retries - 1:
                    yield event.plain_result(
                        f"{entity_name} API 请求失败，错误码：{exc.response.status_code}"
                    )
            except httpx.RequestError as exc:
                self.logger.warning(
                    "%s API attempt %s failed: %s", entity_name, attempt + 1, exc
                )
                if attempt == self.max_retries - 1:
                    yield event.plain_result(
                        f"请求{entity_name} API失败，请检查网络或API是否可用。"
                    )
            except Exception:
                self.logger.exception("Unexpected %s sticker error", entity_name)
                self.last_called_times[command_name] = time.time()
                yield event.plain_result(f"处理{entity_name}请求时发生未知错误。")
                return

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2**attempt)
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

    async def terminate(self):
        self.logger.info("astrbot_plugin_random_meme terminated")
