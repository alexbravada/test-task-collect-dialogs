from pydantic import BaseModel, field_validator
import asyncio
from collections import defaultdict
from typing import Any

import httpx

BASE_URL = "https://dialog-task.edwardmalov.tech"
POLL_INTERVAL_SECONDS = 1


class DialogMsg(BaseModel):
    dialog_id: str
    role: str
    text: str
    message_id: int
    is_last: bool

    @field_validator("role")
    @classmethod
    def role_name(cls, v):
        role_dict = {"client": "user"}
        if isinstance(v, str):
            v = role_dict.get(v, "manager")
        return v


class ListDialog(BaseModel):
    dialogs: list[DialogMsg]


def build_dialog(messages: dict[int, dict[str, Any]]) -> str:
    last_role = ""
    output_dialog = ""
    for _, message in sorted(messages.items()):
        role_name = message['role']
        if not last_role:
            last_role = role_name
            output_dialog += f"{role_name}:"
        if role_name == last_role:
            output_dialog += f" {message['text']}"
        else:
            output_dialog += f"\n{role_name}: {message['text']}"
            last_role = role_name
    return output_dialog


def is_dialog_complete(
    messages: dict[int, dict[str, Any]],
    last_message_id: int,
) -> bool:
    return all(message_id in messages for message_id in range(last_message_id + 1))


async def main() -> None:
    storage: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    last_messages: dict[str, int] = {}

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        while True:
            try:
                response = await client.get("/get_last_messages")
                response.raise_for_status()
                messages = ListDialog.model_validate({"dialogs": response.json()})

                for message in messages.dialogs:
                    dialog_id = message.dialog_id
                    message_id = message.message_id

                    storage[dialog_id][message_id] = {
                        "role": message.role,
                        "text": message.text,
                    }

                    if message.is_last:
                        last_messages[dialog_id] = message_id

                completed_dialogs = [
                    dialog_id
                    for dialog_id, last_message_id in last_messages.items()
                    if is_dialog_complete(storage[dialog_id], last_message_id)
                ]

                for dialog_id in completed_dialogs:
                    dialog_text = build_dialog(storage[dialog_id])
                    #print(dialog_text)
                    payload = {
                        "dialog": dialog_id,
                        "content": dialog_text,
                    }
                    print(payload)
                    result = await client.post("/process_dialog", json=payload)
                    #print(result.json())
                    #result.raise_for_status()

                    if result.json().get("status") == "success":
                        print(f"\n--- {dialog_id} ---")
                        print(dialog_text)
                        print("--- конец диалога ---\n")

                        del storage[dialog_id]
                        del last_messages[dialog_id]

            except httpx.HTTPError as error:
                print(f"Ошибка HTTP: {error}")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
