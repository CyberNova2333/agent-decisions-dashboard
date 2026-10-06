"""Portable identifiers and explicit legacy state aliases shared by all write paths."""
import re


def validate_portable_id(topic_id):
    if not isinstance(topic_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", topic_id):
        raise ValueError("Topic ID 必须为 1–128 位英文字母、数字、下划线或连字符")
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", topic_id, re.I):
        raise ValueError("Topic ID 不能使用 Windows 保留设备名")
    return topic_id


def canonical_impl_state(value):
    return {"未实现": "not_started", "未开始": "not_started", "进行中": "in_progress",
            "已实现": "implemented", "已完成": "implemented", "已核验": "verified"}.get(value, value)
