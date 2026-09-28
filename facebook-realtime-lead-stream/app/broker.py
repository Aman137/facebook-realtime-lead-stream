from __future__ import annotations

import json
from typing import Any, Protocol

from aiokafka import AIOKafkaProducer


class Publisher(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def publish(self, topic: str, value: dict[str, Any], key: str) -> None: ...


class KafkaPublisher:
    def __init__(self, bootstrap_servers: str):
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            key_serializer=lambda value: value.encode("utf-8"),
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            acks="all",
            enable_idempotence=True,
        )

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()

    async def publish(self, topic: str, value: dict[str, Any], key: str) -> None:
        await self._producer.send_and_wait(topic, value=value, key=key)


class InMemoryPublisher:
    """Test publisher that keeps emitted events in memory."""

    def __init__(self):
        self.messages: list[tuple[str, dict[str, Any], str]] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, topic: str, value: dict[str, Any], key: str) -> None:
        self.messages.append((topic, value, key))

