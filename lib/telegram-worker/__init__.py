"""Telegram Queue Consumer - Bridges Redis queue to Telegram notifications."""

from .consumer import TelegramQueueConsumer

__all__ = ["TelegramQueueConsumer"]
