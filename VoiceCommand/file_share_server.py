import os
import discord
from discord.ext import commands
import asyncio
import logging
import aiohttp
import threading
from Config import get_discord_bot_token, get_discord_user_id

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

FILEBROWSER_ROOT = "/mnt/"
DISCORD_BOT_TOKEN = get_discord_bot_token()
YOUR_DISCORD_USER_ID = get_discord_user_id()

# 전역 변수로 봇 객체와 이벤트 루프를 저장
bot = None
main_loop = None
bot_ready = asyncio.Event()

def init_bot():
    global bot, main_loop
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    main_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_loop)

    @bot.event
    async def on_ready():
        logging.info(f"{bot.user}로 로그인했습니다!")
        bot_ready.set()

init_bot()

# Discord 봇을 실행하는 함수
def run_bot():
    main_loop.run_until_complete(bot.start(DISCORD_BOT_TOKEN))

# 봇을 별도의 스레드에서 실행
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

def find_file(partial_name):
    matches = []
    for root, dirs, files in os.walk(FILEBROWSER_ROOT):
        for name in files:
            file_name_without_ext = os.path.splitext(name)[0]
            if partial_name.lower() in file_name_without_ext.lower():
                matches.append(os.path.join(root, name))
    return matches

async def upload_to_catbox(file_path):
    logging.debug(f"파일 업로드 시작: {file_path}")
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as file:
            form = aiohttp.FormData()
            form.add_field('reqtype', 'fileupload')
            form.add_field('fileToUpload', file, filename=os.path.basename(file_path))
            async with session.post('https://catbox.moe/user/api.php', data=form) as response:
                if response.status == 200:
                    download_link = await response.text()
                    logging.debug(f"파일 업로드 완료. 다운로드 링크: {download_link}")
                    return download_link.strip()
                else:
                    raise Exception(f"파일 업로드 실패: {response.status}")

async def share_file(partial_name):
    logging.debug(f"파일 공유 시작: {partial_name}")
    try:
        if not bot_ready.is_set():
            logging.debug("봇이 준비되지 않음. 대기 중...")
            await asyncio.wait_for(bot_ready.wait(), timeout=60)
        logging.debug("봇 준비 완료")
        
        matching_files = find_file(partial_name)
        logging.debug(f"일치하는 파일: {matching_files}")
        if not matching_files:
            return f"'{partial_name}'과 일치하는 파일을 찾을 수 없습니다."

        file_path = matching_files[0]
        file_name = os.path.basename(file_path)
        file_name_without_ext = os.path.splitext(file_name)[0]

        logging.debug(f"파일 '{file_path}' 업로드 중...")
        download_link = await upload_to_catbox(file_path)
        logging.debug(f"파일 업로드 완료. 다운로드 링크: {download_link}")

        message = f"파일 '{file_name_without_ext}'의 다운로드 링크입니다: {download_link}"

        logging.debug(f"사용자 ID {YOUR_DISCORD_USER_ID} 조회 중...")
        user = await bot.fetch_user(YOUR_DISCORD_USER_ID)
        if user:
            logging.debug(f"사용자 {user.name} 찾음. 메시지 전송 중...")
            try:
                await user.send(message)
                logging.debug("메시지 전송 완료")
                return f"파일 '{file_name_without_ext}'의 다운로드 링크를 디스코드 DM으로 전송했습니다."
            except discord.errors.Forbidden:
                logging.error("사용자에게 DM을 보낼 수 없습니다. 사용자 설정을 확인하세요.")
                return "디스코드 DM 전송에 실패했습니다. 사용자 설정을 확인하세요."
        else:
            logging.error(f"사용자 ID {YOUR_DISCORD_USER_ID}를 찾을 수 없음")
            return "디스코드 메시지 전송에 실패했습니다."
    except asyncio.TimeoutError:
        logging.error("봇 준비 또는 작업 수행 중 시간 초과")
        return "Discord 봇 작업이 시간 초과되었습니다. 잠시 후 다시 시도해주세요."
    except Exception as e:
        logging.error(f"파일 공유 중 오류 발생: {e}", exc_info=True)
        return f"파일 공유 중 오류가 발생했습니다: {str(e)}"

def send_file(partial_name):
    logging.debug(f"send_file 함수 호출: {partial_name}")
    future = asyncio.run_coroutine_threadsafe(share_file(partial_name), main_loop)
    try:
        result = future.result(timeout=300)  # 타임아웃을 300초(5분)로 늘림
        logging.debug(f"파일 공유 결과: {result}")
        return result
    except asyncio.TimeoutError:
        logging.error("send_file 작업 시간 초과")
        return "파일 공유 작업이 시간 초과되었습니다. 파일 크기가 너무 크거나 네트워크 문제일 수 있습니다."
    except Exception as e:
        logging.error(f"파일 공유 중 오류 발생: {e}", exc_info=True)
        return f"파일 공유 중 오류가 발생했습니다: {str(e)}"

if __name__ == "__main__":
    # 봇 실행 (이미 별도의 스레드에서 실행 중)
    pass
