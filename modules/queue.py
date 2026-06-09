import asyncio
from typing import Literal
from utils.logger import logger
from modules.base import BaseModule


class QueueModule(BaseModule):
    async def wait_start(self) -> None:
        locator = self.page.locator("video")
        while True:
            try:
                await locator.first.wait_for()
                return
            except Exception:
                await asyncio.sleep(1)

    async def start(self) -> None:
        response = await self.click_start_game()
        chosen_queue = self.make_queue_decision(response)
        await self.handle_choice_dialog(chosen_queue)
        await self.monitor_queue_loop()

    async def remove_overlays(self) -> None:
        old_cancel_locator = self.page.locator(
            "body > div.van-popup.van-popup--center.van-dialog.van-dialog--round-button.clg-confirm-dialog.font-dynamic.clg-dialog-z-index > div.van-action-bar.van-safe-area-bottom.van-dialog__footer > button.van-button.van-button--warning.van-button--large.van-action-bar-button.van-action-bar-button--warning.van-action-bar-button--first.van-dialog__cancel"
        )
        got_it_locator = self.page.locator("button:has-text('我知道了')")

        while True:
            try:
                if await old_cancel_locator.is_visible():
                    await old_cancel_locator.click()
                    logger.debug("检测到默认覆盖层并已成功移除")
                if await got_it_locator.is_visible():
                    await got_it_locator.click()
                    logger.debug("检测到【收藏页面】提示，已点击“我知道了”")
            except asyncio.CancelledError:
                return
            except Exception:
                await asyncio.sleep(1)

    async def click_start_game(self) -> None:
        thread = asyncio.create_task(self.remove_overlays())
        response = await self.wait_for_request(
            [
                "https://cg-hkrpg-api.mihoyo.com/hkrpg_cn/cg/dispatcher/api/preDispatchVerify",
                "https://cg-hkrpg-api.mihoyo.com/hkrpg_cn/cg/dispatcher/api/paasDispatch",
            ],
            after_listen=lambda: self.page.locator(
                "#app > div.home-wrapper > div.welcome > div.welcome-wrapper > div > div.wel-card__content > div.wel-card__content--start"
            ).click(),
        )
        thread.cancel()
        return response

    def make_queue_decision(self, data: dict) -> Literal["fast", "normal", "default"]:
        queue_info = data.get("queue_info")
        normal_len = queue_info.get("queue_len", queue_info.get("queue_length", "0"))
        normal_wait = float(queue_info.get("waiting_time_min", "0"))
        logger.info(f"普通排队: {normal_len} 人 ({normal_wait} 分钟)")

        prior_queue_info = data.get("prior_queue_info")
        if prior_queue_info:
            prior_len = prior_queue_info.get("queue_len", "0")
            prior_wait = float(prior_queue_info.get("waiting_time_min", "0"))
            logger.info(f"快速排队: {prior_len} 人 ({prior_wait} 分钟)")

        if not prior_queue_info:
            logger.info("没有检测到快速通道，自动选择普通通道")
            return "default"

        pref = self.manager.config.queue.queue_pref
        if pref == "threshold":
            if normal_wait >= self.manager.config.queue.threshold_minutes:
                logger.debug(
                    f"预计等待时间 {normal_wait} > {self.manager.config.queue.threshold_minutes}，选择快速通道"
                )
                return "fast"
            else:
                logger.debug(
                    f"预计等待时间 {normal_wait} < {self.manager.config.queue.threshold_minutes}，选择普通通道"
                )
                return "normal"
        logger.debug(f"直接根据配置选择 {pref} 通道")
        return pref

    async def handle_choice_dialog(
        self, chosen_queue: Literal["fast", "normal", "default"]
    ) -> None:
        if chosen_queue == "default":
            waiting_locator = self.page.locator(
                "#app > div.home-wrapper > div.welcome > div.van-overlay.waiting-overlay"
            )
            await waiting_locator.first.wait_for()
            logger.debug("检测到等待排队面板...")
            return

        dialog_locator = self.page.locator(
            "div.van-dialog__content div.custom-dialog-message"
        )
        await dialog_locator.first.wait_for(),
        logger.debug("检测到排队类型选项确认面板...")
        choices_locator = self.page.locator(
            "div.van-dialog__content div.custom-dialog-message > div > div"
        )
        if chosen_queue == "fast":
            await choices_locator.nth(0).click()
        else:
            await choices_locator.nth(1).click()

    async def monitor_queue_loop(self) -> None:
        logger.debug("进入排队监测循环，持续监听排队状态更新...")
        while True:
            try:
                response = await self.wait_for_request(
                    "https://cg-hkrpg-api.mihoyo.com/hkrpg_cn/cg/dispatcher/api/getDispatchTicketInfo"
                )
                status = response.get("ticket_status", "UNKNOWN")
                if status == "QUEUEING":
                    q_info = response.get("queue_info")
                    if q_info:
                        node_name = q_info.get("node_name", "N/A")
                        q_len = q_info.get("queue_length", "N/A")
                        q_rank = q_info.get("queue_rank", "N/A")
                        wait_time = q_info.get("waiting_time_min", "N/A")
                        logger.info(
                            f"[实时排队] 物理节点: {node_name} | "
                            f"队列载量: {q_len} | "
                            f"顺位等级: {q_rank} | "
                            f"预计消耗: {wait_time} 分钟"
                        )
                else:
                    logger.info(
                        f"检测到云游戏实例连接就绪，排队状态变更为: {status}。销毁排队轮询器。"
                    )
                    break
            except Exception:
                continue
