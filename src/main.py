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

from models.max import BaseMaxApiModel, MaxAuthTokenRequest, MaxUserAgent, MaxTokenData, MaxGetMessagesRequest, MaxGetMessagesRequestPayload, MaxGetFileUrlPayload, MaxGetFileUrlRequest, MaxGetContactInfoPayload

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 
LAST_MSG_FILE = os.path.join(BASE_DIR, 'last_msg_id.txt')
MAX_TG_TEXT = 4096
MAX_TG_CAPTION = 1024

load_dotenv()

FILTER_IDS = json.loads(os.getenv("USER_FILTER_IDs", "[]"))

logging.basicConfig(
    format="%(asctime)s %(message)s",
    level=logging.DEBUG,
)

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

async def max_connect():
    url = "wss://ws-api.oneme.ru/websocket"
    last_message_id = get_last_msg_id()
    seq = 0

    async with connect(
        url,
        user_agent_header=os.getenv("MAX_USER_AGENT"),
        origin=Origin("https://web.max.ru"),
    ) as ws:
        initial_session_request = BaseMaxApiModel(
            cmd=0,
            ver=11,
            seq=seq,
            opcode=6,
            payload={
                "deviceId": str(uuid4()),
                "userAgent": MaxUserAgent(
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

        res = BaseMaxApiModel(**json.loads(await ws.recv()))
        logging.info(f"Инициализация сессии: opcode={res.opcode}")

        auth_request = MaxAuthTokenRequest(
            seq=seq,
            payload=MaxTokenData(
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

        res = BaseMaxApiModel(**json.loads(await ws.recv()))
        logging.info(f"Авторизация успешна: opcode={res.opcode}")

        logging.info("Запускаю loop сообщений...")

        client = AsyncClient(base_url=f"https://api.telegram.org/bot{os.getenv('TG_TOKEN')}")
        
        while True:
            get_messages_request = MaxGetMessagesRequest(
                seq=seq,
                payload=MaxGetMessagesRequestPayload(
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
                logging.debug("Нет новых сообщений")
                await asyncio.sleep(3)
                continue

            last_message = messages[-1]
            current_msg_id = str(last_message.get("id", ""))

            if last_message.get("link") and last_message["link"]["type"] == "FORWARD":
                last_message = last_message["link"]["message"]

            if current_msg_id == last_message_id:
                logging.debug("Нет новых сообщений")
                await asyncio.sleep(3)
                continue

            logging.info(f"Новое сообщение! ID: {current_msg_id}")
            # logging.debug(f"DEBUG сообщения: {last_message}")

            set_last_msg_id(current_msg_id)
            last_message_id = current_msg_id

            sender_id = int(last_message.get("sender"))

            if FILTER_IDS and sender_id not in FILTER_IDS:
                logging.info(f"Сообщение от пользователя {sender_id} пропущено из-за фильтра")
                continue

            contact_request = BaseMaxApiModel(
                seq=seq,
                payload=MaxGetContactInfoPayload(contactIds=[sender_id]).model_dump(),
                cmd=0,
                ver=11,
                opcode=32
            )
            await ws.send(json.dumps(contact_request.model_dump()))
            seq += 1

            res_contact = await wait_for_opcode(ws, 32)

            contacts = res_contact.get("payload", {}).get("contacts", [])
            # logging.debug(res_contact)

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

            logging.info(f"Сообщение от: {sender_name}")

            text = last_message.get("text", "").strip()
            escaped_text = html.escape(text) if text else None
            tg_text = f"Сообщение от {sender_name}:\n\n<blockquote>{escaped_text}</blockquote>"
            tg_caption = tg_text

            if len(tg_text) > MAX_TG_TEXT:
                tg_text = tg_text[:MAX_TG_TEXT - 3] + "..."

            if len(tg_caption) > MAX_TG_CAPTION:
                tg_caption = tg_caption[:MAX_TG_CAPTION - 3] + "..."

            photos = [
                {"type": "photo", "media": attach["baseUrl"]}
                for attach in last_message.get("attaches", [])
                if attach["_type"] == "PHOTO"
            ]

            files = [
                attach
                for attach in last_message.get("attaches", [])
                if attach["_type"] == "FILE"
            ]

            if photos:
                if escaped_text:
                    photos[0]["caption"] = tg_caption
                    photos[0]["parse_mode"] = "html"
                else:
                    photos[0]["caption"] = f'Фото от {sender_name}'
                await client.post("/sendMediaGroup", json={
                    "chat_id": os.getenv("TG_CHAT_ID"),
                    "media": photos
                })

            elif files:
                for attach in files:
                    file_id = attach["fileId"]
                    request = MaxGetFileUrlRequest(
                        seq=seq,
                        payload=MaxGetFileUrlPayload(
                            fileId=file_id,
                            chatId=int(os.getenv("MAX_CHAT_ID")),
                            messageId=last_message["id"]
                        )
                    )
                    await ws.send(json.dumps(request.model_dump()))
                    seq += 1
                    res_file = await wait_for_opcode(ws, 88)
                    file_url = res_file.get("payload", {}).get("url")
                    if not file_url:
                        logging.warning("URL файла не получен")
                        continue

                    async with AsyncClient() as http:
                        file_data = await http.get(file_url)

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
                    "parse_mode": "html"
                })

            await asyncio.sleep(3)

if __name__ == "__main__":
    try:
        asyncio.run(max_connect())
    except KeyboardInterrupt:
        logging.info("Приложение остановлено")
    except Exception as e:
        logging.error(f"Ошибка приложения: {e}")
