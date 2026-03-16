import asyncio
import json
import sys
import os
from uuid import uuid4
from websockets import Origin
from websockets.asyncio.client import connect
from dotenv import load_dotenv
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from models.max import BaseMaxApiModel, MaxUserAgent, MaxAuthTokenRequest, MaxTokenData

load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(message)s",
    level=logging.INFO,
)

async def wait_for_opcode(ws, expected_opcode: int):
    while True:
        res = json.loads(await ws.recv())
        if res.get("opcode") == expected_opcode:
            return res

async def max_connect():
    url = "wss://ws-api.oneme.ru/websocket"
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
        await ws.recv()  

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
        await ws.recv() 

        group_request = BaseMaxApiModel(
            seq=seq,
            cmd=0,
            ver=11,
            opcode=48,
            payload={
                "chatIds": [int(os.getenv("MAX_CHAT_ID"))]
            }
        )
        await ws.send(json.dumps(group_request.model_dump()))
        seq += 1

        res_group = await wait_for_opcode(ws, 48)
        res_group_payload = res_group.get("payload", {})
        chats = res_group_payload.get("chats", [])

        if chats:
            chat = chats[0]  
            owner_id = chat.get("owner")
            participants = chat.get("participants", {})

            left_participants = [int(uid) for uid in participants.keys()]

            contact_request = {
            "ver": 11,
            "cmd": 0,
            "seq": seq,
            "opcode": 32,
            "payload": {
                    "contactIds": left_participants
                }
            }

            await ws.send(json.dumps(contact_request))
            seq += 1

            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                opcode = data.get("opcode")
                payload = data.get("payload") or {}

                if opcode == 32:
                    print("Участники:")

                    contacts = payload.get("contacts", [])

                    for contact in contacts:
                        user_id = contact.get("id")

                        names = contact.get("names", [])
                        first_name = ""
                        last_name = ""

                        if names:
                            name_data = names[0]
                            first_name = name_data.get("firstName", "")
                            last_name = name_data.get("lastName", "")

                        full_name = f"{first_name} {last_name}".strip()

                        print(f"{user_id} - {full_name}")

                    break

if __name__ == "__main__":
    asyncio.run(max_connect())