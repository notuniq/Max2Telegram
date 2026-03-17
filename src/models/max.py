from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class BaseApiModel(BaseModel):
    cmd: int
    opcode: int
    payload: Any
    seq: int
    ver: int


class UserAgent(BaseModel):
    deviceType: str
    locale: str
    deviceLocale: str
    osVersion: str
    deviceName: str
    headerUserAgent: str
    appVersion: str
    screen: str
    timezone: str


class AuthRequest(BaseModel):
    userAgent: UserAgent
    deviceId: str


class TokenData(BaseModel):
    interactive: bool
    token: str
    chatsCount: int
    chatsSync: int
    contactsSync: int
    presenceSync: int
    draftsSync: int


class AuthTokenRequest(BaseApiModel):
    cmd: int = 0
    opcode: int = 19
    ver: int = 11
    payload: TokenData


class GetMessagesRequestPayload(BaseModel):
    chatId: int
    from_: int = Field(alias="from", default_factory=lambda: int(datetime.now().timestamp() * 1000))
    forward: int
    backward: int
    getMessages: bool


class GetMessagesRequest(BaseApiModel):
    ver: int = 11
    cmd: int = 0
    opcode: int = 49
    payload: GetMessagesRequestPayload


class GetFileUrlPayload(BaseModel):
    fileId: int
    chatId: int
    messageId: str


class GetFileUrlRequest(BaseApiModel):
    ver: int = 11
    cmd: int = 0
    opcode: int = 88
    payload: GetFileUrlPayload


class GetContactInfoPayload(BaseModel):
    contactIds: list[int]


class GetGroupInfoPayload(BaseModel):
    chatIds: list[int]


class GetAudioVideoPayload(BaseModel):
    chatId: int
    messageId: str
    attachTypes: list[str] = ["VIDEO_MSG", "AUDIO"]
    forward: int = 25
    backward: int = 25


class GetVideoPayload(BaseModel):
    chatId: int
    messageId: int | str
    videoId: int