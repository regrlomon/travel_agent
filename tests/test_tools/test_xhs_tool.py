import pytest
from tools.xhs_tool._core import _parse_note


def test_parse_note_with_full_card():
    item = {
        "note_card": {
            "display_title": "稻城亚丁攻略",
            "interact_info": {"liked_count": "1.2万"},
            "user": {"nickname": "旅行者"},
        },
        "id": "abc123",
        "xsec_token": "tok",
    }
    note = _parse_note(item)
    assert note["title"] == "稻城亚丁攻略"
    assert note["author"] == "旅行者"
    assert "abc123" in note["url"]
    assert note["content"] == ""


def test_parse_note_missing_fields():
    note = _parse_note({})
    assert note["title"] == ""
    assert note["author"] == ""
    assert note["url"] == ""
    assert note["content"] == ""
