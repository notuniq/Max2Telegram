import asyncio
import json
import os
from uuid import uuid4
from httpx import AsyncClient
from websockets import Origin
from websockets.asyncio.client import connect
import logging
from dotenv import load_dotenv
import html
import subprocess
import io

from models.max import BaseApiModel, AuthTokenRequest, UserAgent, TokenData, GetMessagesRequest, GetMessagesRequestPayload, GetFileUrlPayload, GetFileUrlRequest, GetContactInfoPayload, GetAudioVideoPayload, GetVideoPayload
from models.enum import Opcode

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 
LAST_MSG_FILE = os.path.join(BASE_DIR, 'last_msg_id.txt')
MAX_TG_TEXT = 4096
MAX_TG_CAPTION = 1024

load_dotenv()

FILTER_IDS = json.loads(os.getenv("USER_FILTER_IDs", "[]"))

logging.basicConfig(
    format="%(asctime)s %(message)s",
    level=logging.INFO,
)

headers = {
    "User-Agent": os.getenv("MAX_USER_AGENT"),
    "Accept": "audio/webm,audio/ogg,audio/wav,audio/*;q=0.9,application/ogg;q=0.7,video/*;q=0.6,*/*;q=0.5",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Range": "bytes=0-",
    "Referer": "https://web.max.ru/"
        }

def get_last_msg_id():
    try:
        content = open(LAST_MSG_FILE, "r+").readline().strip()
        return content if content else None
    except FileNotFoundError:
        return None

def set_last_msg_id(msg_id):
    with open(LAST_MSG_FILE, "w") as f:
        f.write(str(msg_id))

async def wait_for_opcode(ws, expected_opcode: int):
    while True:
        res = json.loads(await ws.recv())
        if res.get("opcode") == expected_opcode:
            return res
        
ahttp = AsyncClient(timeout=30)
        
async def max_connect():
    url = "wss://ws-api.oneme.ru/websocket"
    last_message_id = get_last_msg_id()
    seq = 0

    async with connect(
        url,
        user_agent_header=os.getenv("MAX_USER_AGENT"),
        origin=Origin("https://web.max.ru"),
    ) as ws:
        initial_session_request = BaseApiModel(
            cmd=0,
            ver=11,
            seq=seq,
            opcode=Opcode.SESSION_INIT,
            payload={
                "deviceId": str(uuid4()),
                "userAgent": UserAgent(
                    deviceType=os.getenv("MAX_DEVICE_TYPE"),
                    locale=os.getenv("MAX_LOCALE"),
                    deviceLocale=os.getenv("MAX_DEVICE_LOCALE"),
                    osVersion=os.getenv("MAX_OS_VERSION"),
                    headerUserAgent=os.getenv("MAX_USER_AGENT"),
                    appVersion=os.getenv("MAX_APP_VERSION"),
                    screen=os.getenv("MAX_SCREEN"),
                    timezone=os.getenv("MAX_TZ"),
                    deviceName=os.getenv("MAX_DEVICE_NAME")
                ).model_dump(),
            },
        )
        await ws.send(json.dumps(initial_session_request.model_dump()))
        seq += 1

        res = BaseApiModel(**json.loads(await ws.recv()))
        logging.info(f"Инициализация сессии: opcode={res.opcode}")

        auth_request = AuthTokenRequest(
            seq=seq,
            payload=TokenData(
                interactive=True,
                token=os.getenv("MAX_AUTH_TOKEN"),
                chatsCount=40,
                chatsSync=0,
                contactsSync=0,
                presenceSync=0,
                draftsSync=0
            )
        )
        await ws.send(json.dumps(auth_request.model_dump()))
        seq += 1

        res = BaseApiModel(**json.loads(await ws.recv()))
        logging.info(f"Авторизация успешна: opcode={res.opcode}")

        logging.info("Запускаю loop сообщений...")

        client = AsyncClient(base_url=f"https://api.telegram.org/bot{os.getenv('TG_TOKEN')}", timeout=60.0)
        
        while True:
            get_messages_request = GetMessagesRequest(
                seq=seq,
                payload=GetMessagesRequestPayload(
                    chatId=int(os.getenv("MAX_CHAT_ID")),
                    forward=0,
                    backward=30,
                    getMessages=True,
                )
            )
            await ws.send(json.dumps(get_messages_request.model_dump(by_alias=True)))
            seq += 1

            res = await wait_for_opcode(ws, 49)
            messages = res.get("payload", {}).get("messages", [])

            if not messages:
                logging.info("Нет новых сообщений")
                await asyncio.sleep(3)
                continue

            messages.sort(key=lambda x: x.get("id"))  

            if not last_message_id:
                if messages:
                    last_message_id = str(messages[-1].get("id"))
                    set_last_msg_id(last_message_id)
                    logging.info(f"Инициализация last_message_id: {last_message_id}, ждем новые сообщения...")
                await asyncio.sleep(3)
                continue

            start_index = 0
            for i, msg in enumerate(messages):
                if str(msg.get("id")) == last_message_id:
                    start_index = i + 1
                    break
            
            new_messages = messages[start_index:]

            for msg in new_messages:
                current_msg_id = str(msg.get("id", ""))
                original_sender = msg.get("sender")

                if msg.get("link") and msg["link"]["type"] == "FORWARD":
                    forwarded_msg = msg["link"]["message"]

                    forwarded_msg["forwardedSender"] = forwarded_msg.get("sender")

                    forwarded_msg["sender"] = original_sender

                    msg = forwarded_msg

                if current_msg_id == last_message_id:
                    logging.info("Нет новых сообщений")
                    await asyncio.sleep(3)
                    continue

                logging.info(f"Новое сообщение! ID: {current_msg_id}")
                #logging.debug(f"DEBUG сообщения: {msg}")

                set_last_msg_id(current_msg_id)
                last_message_id = current_msg_id

                sender_id = int(msg.get("sender"))

                if FILTER_IDS and sender_id not in FILTER_IDS:
                    logging.info(f"Сообщение от пользователя {sender_id} пропущено из-за фильтра")
                    continue

                contact_request = BaseApiModel(
                    seq=seq,
                    payload=GetContactInfoPayload(contactIds=[sender_id]).model_dump(),
                    cmd=0,
                    ver=11,
                    opcode=Opcode.CONTACT_INFO
                )
                await ws.send(json.dumps(contact_request.model_dump()))
                seq += 1

                res_contact = await wait_for_opcode(ws, 32)

                contacts = res_contact.get("payload", {}).get("contacts", [])

                if contacts:
                    contact = contacts[0]
                    names = contact.get("names", [])
                    if names:
                        name_data = names[0]
                        full_name = f"{name_data.get('firstName','')} {name_data.get('lastName','')}".strip()
                        sender_name = full_name or name_data.get("name")
                    else:
                        sender_name = contact.get("id") 
                else:
                    sender_name = sender_id

                logging.info(f"Поймано сообщение от: {sender_name}")

                text = msg.get("text", "").strip()
                escaped_text = html.escape(text) if text else None
                tg_text = f"Сообщение от {sender_name}:\n\n<blockquote>{escaped_text}</blockquote>"
                tg_caption = tg_text

                if len(tg_text) > MAX_TG_TEXT:
                    tg_text = tg_text[:MAX_TG_TEXT - 3] + "..."

                if len(tg_caption) > MAX_TG_CAPTION:
                    tg_caption = tg_caption[:MAX_TG_CAPTION - 3] + "..."

                files = [
                    attach
                    for attach in msg.get("attaches", [])
                    if attach.get("_type") == "FILE"
                ]
                
                contacts_attach = [
                    attach
                    for attach in msg.get("attaches", [])
                    if attach.get("_type") == "CONTACT"
                ]

                stickers = [
                    attach
                    for attach in msg.get("attaches", [])
                    if attach.get("_type") == "STICKER" or attach.get("stickerId")
                ]

                audios = [
                    attach
                    for attach in msg.get("attaches", [])
                    if attach.get("_type") == "AUDIO" or attach.get("audioId")
                ]

                videos = [
                    attach
                    for attach in msg.get("attaches", [])
                    if attach.get("_type") == "VIDEO" or attach.get("videoId")
                ]

                media = []
                files_data = {}

                photo_attachments = [attach for attach in msg.get("attaches", []) if attach.get("_type") == "PHOTO" and not attach.get("gif")]
                gif_attachments = [attach for attach in msg.get("attaches", []) if attach.get("_type") == "PHOTO" and attach.get("gif") and attach.get("mp4Url")]
                video_attachments = [
                    attach for attach in msg.get("attaches", [])
                    if (attach.get("_type") == "VIDEO" or attach.get("videoId")) and attach.get("videoType") == 0
                ]

                for attach in photo_attachments:
                    media.append({
                        "type": "photo",
                        "media": attach["baseUrl"]
                    })
                
                if gif_attachments:
                    tasks = [ahttp.get(attach["mp4Url"]) for attach in gif_attachments]
                    responses = await asyncio.gather(*tasks)

                    for i, resp in enumerate(responses):
                        attach = gif_attachments[i]
                        name = f"gif{i}.mp4"
                        files_data[name] = resp.content
                        media.append({
                            "type": "video",
                            "media": f"attach://{name}",
                            "is_gif": True
                        })

                if video_attachments:
                    for i, video in enumerate(video_attachments):
                        video_id = video.get("videoId")

                        res_video = BaseApiModel(
                            seq=seq,
                            payload=GetVideoPayload(
                                chatId=int(os.getenv("MAX_CHAT_ID")),
                                messageId=str(current_msg_id),
                                videoId=int(video_id)
                            ).model_dump(),
                            cmd=0,
                            ver=11,
                            opcode=Opcode.VIDEO_PLAY
                        )
                        await ws.send(json.dumps(res_video.model_dump()))
                        seq += 1

                        res_video_data = await wait_for_opcode(ws, 83)

                        payload = res_video_data.get("payload", {})
                        mp4_keys = [k for k in payload.keys() if k.startswith("MP4_")]
                        if not mp4_keys:
                            logging.warning("Нет MP4 форматов")
                            continue
                        mp4_keys.sort(key=lambda x: int(x.split("_")[1]), reverse=True)

                        video_url = payload[mp4_keys[0]]

                        if not video_url:
                            logging.warning("URL видео не получен")
                            continue

                        resp = await ahttp.get(video_url, headers=headers)
                        if resp.status_code != 200:
                            logging.warning(f"Не удалось скачать видео: {resp.status_code}")
                            continue

                        name = f"video{i}.mp4"
                        files_data[name] = resp.content

                        media.append({
                            "type": "video",
                            "media": f"attach://{name}",
                            "is_video": True
                        })

                if media:
                    if escaped_text:
                        media[0]["caption"] = tg_caption
                        media[0]["parse_mode"] = "HTML"
                    else:
                        has_gif = any(m.get("is_gif") for m in media)
                        has_video = any(m.get("is_video") for m in media)
                        has_photo = any(m["type"] == "photo" for m in media)

                        if has_video and has_photo:
                            caption = f"Фото и видео от {sender_name}"
                        elif has_video:
                            caption = f"Видео от {sender_name}"
                        elif has_gif and has_photo:
                            caption = f"Фото и GIF от {sender_name}"
                        elif has_gif:
                            caption = f"GIF от {sender_name}"
                        else:
                            caption = f"Фото от {sender_name}"

                        media[0]["caption"] = caption

                    files = {
                        name: (name, io.BytesIO(data), "video/mp4")
                        for name, data in files_data.items()
                    }

                    await client.post(
                        "/sendMediaGroup",
                        data={
                            "chat_id": os.getenv("TG_CHAT_ID"),
                            "media": json.dumps(media)
                        },
                        files=files
                    )

                elif files:
                    for attach in files:
                        file_id = attach["fileId"]
                        request = GetFileUrlRequest(
                            seq=seq,
                            payload=GetFileUrlPayload(
                                fileId=file_id,
                                chatId=int(os.getenv("MAX_CHAT_ID")),
                                messageId=msg["id"]
                            )
                        )
                        await ws.send(json.dumps(request.model_dump()))
                        seq += 1
                        res_file = await wait_for_opcode(ws, 88)
                        file_url = res_file.get("payload", {}).get("url")
                        if not file_url:
                            logging.warning("URL файла не получен")
                            continue

                        file_data = await ahttp.get(file_url)

                        await client.post(
                            "/sendDocument",
                            data={
                                "chat_id": os.getenv("TG_CHAT_ID"),
                                "caption": f'Файл от {sender_name}'
                            },
                            files={"document": (attach["name"], file_data.content)}
                        )

                elif escaped_text:
                    await client.post("/sendMessage", json={
                        "chat_id": os.getenv("TG_CHAT_ID"),
                        "text": f"{tg_text}",
                        "parse_mode": "HTML"
                    })

                elif stickers:
                    sticker = stickers[0]
                    sticker_id = sticker.get("stickerId")
                    logging.info(f'{sender_name} отправил стикер с ID: {sticker_id}, пропускаю.')
                    continue

                elif audios:
                    audio = audios[0]
                    audio_id = audio.get("audioId")
                    audio_url = audio.get("url")
                    duration = audio.get("duration")
                    logging.info(f'{sender_name} отправил голосовое сообщение с ID: {audio_id}, длительность: {duration}мс')
                    if not audio_url:
                        logging.warning("URL аудио не найден")
                        continue


                    audio_resp = await ahttp.get(audio_url, headers=headers)
                    if audio_resp.status_code != 200:
                        logging.warning(f"Не удалось скачать аудио: {audio_resp.status_code}")
                    else:
                        mp3_bytes = io.BytesIO(audio_resp.content)
                        ogg_bytes = io.BytesIO()
                        process = await asyncio.to_thread(
                            subprocess.run,
                            [
                                "ffmpeg",
                                "-i", "pipe:0",
                                "-c:a", "libopus",
                                "-b:a", "64k",
                                "-f", "ogg",
                                "pipe:1"
                            ],
                            input=mp3_bytes.read(),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE
                            )
                        ogg_bytes.write(process.stdout)
                        ogg_bytes.seek(0)

                        await client.post(
                            "/sendVoice",
                            data={
                                "chat_id": os.getenv("TG_CHAT_ID"),
                                "caption": f"Голосовое сообщение от {sender_name}",
                                "parse_mode": "HTML" 
                            },
                            files={
                                "voice": ("voice.ogg", ogg_bytes.read(), "audio/ogg")
                                }
                        )

                elif videos:
                    video = videos[0]
                    videoType = video.get("videoType")
                    video_id = video.get("videoId")
                    duration = video.get("duration")

                    if videoType == 1:
                        logging.info(f'{sender_name} отправил видео сообщение с ID: {video_id}, длительность: {duration}мс')

                        res_video = BaseApiModel(
                            seq=seq,
                            payload=GetVideoPayload(
                                chatId=int(os.getenv("MAX_CHAT_ID")),
                                messageId=str(current_msg_id),
                                videoId=int(video_id)
                            ).model_dump(),
                            cmd=0,
                            ver=11,
                            opcode=Opcode.VIDEO_PLAY
                        )
                        await ws.send(json.dumps(res_video.model_dump()))
                        seq += 1 
                        res_video_data = await wait_for_opcode(ws, 83)

                        payload = res_video_data.get("payload", {})
                        mp4_keys = [k for k in payload.keys() if k.startswith("MP4_")]
                        if not mp4_keys:
                            logging.warning("Нет MP4 форматов")
                            continue
                        mp4_keys.sort(key=lambda x: int(x.split("_")[1]), reverse=True)

                        video_url = payload[mp4_keys[0]]

                        if not video_url:
                            logging.warning("URL видео не получен")
                            continue

                        video_resp = await ahttp.get(video_url, headers=headers)

                        if video_resp.status_code != 200:
                            logging.warning(f"Не удалось скачать видео: {video_resp.status_code}")
                            continue

                        video_bytes = io.BytesIO(video_resp.content)
                        video_bytes.seek(0)

                        res_msg = await client.post(
                            "/sendVideoNote",
                            data={
                                "chat_id": os.getenv("TG_CHAT_ID"),
                                "length": 240
                            },
                            files={
                                "video_note": ("video.mp4", video_bytes, "video/mp4")
                            }
                        )

                        msg_id = res_msg.json()["result"]["message_id"]

                        await client.post("/sendMessage", json={
                            "chat_id": os.getenv("TG_CHAT_ID"),
                            "text": f"Кружок от {sender_name}",
                            "reply_to_message_id": msg_id
                        })
                    
                elif contacts_attach:
                    contact = contacts_attach[0]
                    contact_name = contact.get("name") or contact.get("firstName")
                    contact_id = contact.get("contactId")
                    logging.info(f"{sender_name} отправил контакт: {contact_name} (ID: {contact_id}), пропускаю.")
                    continue

if __name__ == "__main__":
    try:
        asyncio.run(max_connect())
    except KeyboardInterrupt:
        logging.info("Приложение остановлено")
    except Exception as e:
        logging.error(f"Ошибка приложения: {e}")
