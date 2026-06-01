import asyncio
import time
from typing import Optional, Tuple, Callable
import cv2
import numpy as np
from playwright.async_api import Locator
from utils.logger import logger
from modules.base import BaseModule


class InGameModule(BaseModule):
    _video_locator: Optional[Locator]
    _input_locator: Optional[Locator]

    def __init__(self, manager) -> None:
        super().__init__(manager)
        self._video_locator = None
        self._input_locator = None

    def setup_locators(self) -> None:
        self._input_locator = self.page.locator(
            "#app > div > div.game-player__event-layer"
        )
        self._video_locator = self.page.locator("#app > div > video")

    async def dismiss_guides_and_agree_tos(self) -> None:
        logger.debug("正在等待引导提示加载并尝试自动关闭...")
        for i in range(3):
            try:
                await self.page.locator(
                    "body > div.game-menu-setting-guide > div > div.game-menu-setting-guide__step > div.game-menu-setting-guide__step-btn"
                ).nth(i).click(timeout=3000 if i == 0 else 500)
                logger.debug(f"引导提示 {i+1} 已关闭")
            except Exception:
                logger.debug(f"引导提示 {i+1} 未出现，继续等待...")

        logger.debug("正在等待并尝试自动确认云端用户许可协议...")
        try:
            await self.page.locator(
                "body > div.van-popup.van-popup--center.van-dialog.van-dialog--round-button"
                ".combo-dialog.user-agreement-dialog > div.van-action-bar.van-safe-area-bottom"
                ".van-dialog__footer > button.van-button.van-button--danger.van-button--large"
                ".van-action-bar-button.van-action-bar-button--danger.van-action-bar-button--last"
                ".van-dialog__confirm > div",
            ).click(timeout=20000)
            logger.success("云端用户许可协议已确认")
        except Exception:
            logger.error("确认云端用户未出现")

    async def shot(self) -> np.ndarray:
        screenshot_bytes = await self.page.evaluate(
            """async () => {
                    const video = document.querySelector('#app > div > video');
                    const canvas = document.createElement('canvas');
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                    return await new Promise(resolve => {
                        canvas.toBlob(blob => {
                            const reader = new FileReader();
                            reader.onloadend = () => resolve(new Uint8Array(reader.result));
                            reader.readAsArrayBuffer(blob);
                        }, 'image/jpeg', 0.8);
                    });
                }""",
        )
        nparr = np.asarray(screenshot_bytes, dtype=np.uint8)
        img_rgb = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img_rgb

    async def click_template(
        self,
        template_path: str,
        threshold: float = 0.8,
        timeout_limit: float = 0.1,
    ) -> bool:
        assert self._video_locator is not None
        assert self._input_locator is not None

        template = cv2.imread("assets/" + template_path, cv2.IMREAD_COLOR)
        if template is None:
            raise FileNotFoundError(f"未找到模板图片文件: {template_path}")
        temp_h, temp_w = template.shape[:2]

        start_time = time.time()

        while True:
            max_val, max_loc = await self.match(template_path)

            if max_val >= threshold:
                box = await self._input_locator.bounding_box()
                if box is None:
                    logger.error("无法获取点击目标层的 CSS 宽高，请确认元素是否可见")
                    return False

                target_x = max_loc[0] + temp_w // 2
                target_y = max_loc[1] + temp_h // 2
                location = {
                    "x": target_x,
                    "y": target_y,
                }
                await self._input_locator.click(position=location)
                logger.debug(f"点击目标成功: {template_path} | 置信度: {max_val:.4f}")
                return True

            if time.time() - start_time >= timeout_limit:
                return False

    async def do_until_match(
        self,
        template_path: str,
        action: Callable,
        threshold: float = 0.8,
        timeout_limit: float = 10.0,
    ) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout_limit:
            max_val, _ = await self.match(template_path)
            if max_val >= threshold:
                logger.debug(f"目标 '{template_path}' 已匹配成功，结束重复动作")
                return True
            try:
                await action()
            except Exception:
                continue
        logger.warning(f"执行动作超时，未能匹配到目标 '{template_path}'")
        return False

    async def match(self, template_path: str) -> Tuple[float, Tuple[int, int]]:
        assert self._video_locator is not None

        template = cv2.imread("assets/" + template_path, cv2.IMREAD_COLOR)
        if template is None:
            raise FileNotFoundError(f"未找到模板图片文件: {template_path}")

        screenshot = await self.shot()
        res = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        logger.debug(f"目标 '{template_path}' 匹配结果: {max_val:.4f} {max_loc}")
        return max_val, max_loc

    async def toggle_switch_on(self, off_template: str, on_template: str) -> None:
        assert self._video_locator is not None

        try:
            screenshot = await self.shot()

            off_temp = cv2.imread("assets/" + off_template, cv2.IMREAD_COLOR)
            on_temp = cv2.imread("assets/" + on_template, cv2.IMREAD_COLOR)

            if off_temp is None or on_temp is None:
                logger.error(f"加载开关模板失败: {off_template} 或 {on_template}")
                return

            res_off = cv2.matchTemplate(screenshot, off_temp, cv2.TM_CCOEFF_NORMED)
            _, off_score, _, _ = cv2.minMaxLoc(res_off)

            res_on = cv2.matchTemplate(screenshot, on_temp, cv2.TM_CCOEFF_NORMED)
            _, on_score, _, _ = cv2.minMaxLoc(res_on)

            logger.debug(
                f"[开关检测] 统一截图比对 | 关闭状态({off_template}): {off_score:.4f} | 开启状态({on_template}): {on_score:.4f}"
            )

            if max(off_score, on_score) < 0.7:
                logger.warning(
                    f"开关匹配置信度不足（双方最大值: {max(off_score, on_score):.4f} < 0.7），跳过点击决策。"
                )
                return

            if off_score > on_score:
                logger.debug(
                    f"检测到开关处于关闭状态，正在执行点击开启: {off_template}"
                )
                await self.click_template(off_template, threshold=0.7)
            else:
                logger.debug("检测到开关已处于开启状态，无需重复点击。")

        except Exception as e:
            logger.error(f"开关同图智能比对时发生异常: {e}")

    async def wait_for_template(
        self,
        template_path: str,
        threshold: float = 0.8,
        timeout: float = 30.0,
    ) -> bool:
        assert self._video_locator is not None

        template = cv2.imread("assets/" + template_path, cv2.IMREAD_COLOR)
        if template is None:
            raise FileNotFoundError(f"未找到模板图片文件: {template_path}")

        start_time = time.time()
        logger.debug(
            f"正在等待目标元素出现: {template_path} (阈值: {threshold}, 超时: {timeout}s)..."
        )

        while time.time() - start_time < timeout:
            screenshot = await self.shot()
            res = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)

            logger.debug(
                f"[监测轮询] 匹配 '{template_path}' 状态... 当前最大分值: {max_val:.4f}"
            )

            if max_val >= threshold:
                elapsed = time.time() - start_time
                logger.success(
                    f"成功等待到目标元素: {template_path} | 置信度: {max_val:.4f} | 耗时: {elapsed:.2f}s"
                )
                return True

        logger.warning(f"等待目标元素超时: {template_path}")
        return False

    async def press_system_key(self, key_name: str) -> None:
        assert self._input_locator is not None
        logger.debug(f"发送键盘事件: {key_name}")
        await self._input_locator.press(key_name)

    async def create_template_interactively(
        self, output_path: str = "template.png"
    ) -> bool:
        logger.info("正在获取实时截图并准备弹出选择窗口...")
        img = await self.shot()

        window_name = "Select Template (ENTER/SPACE to save, 'C' to cancel)"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        roi = cv2.selectROI(window_name, img, showCrosshair=True, fromCenter=False)
        x, y, w, h = roi

        cv2.destroyWindow(window_name)
        cv2.destroyAllWindows()
        for _ in range(5):
            cv2.waitKey(1)

        if w > 0 and h > 0:
            cropped_img = img[y : y + h, x : x + w]
            cv2.imwrite(output_path, cropped_img)
            logger.success(f"模板创建成功！已保存至: {output_path} ({w}x{h})")
            return True
        else:
            logger.warning("操作已被取消或框选无效，未保存任何模板。")
            return False
