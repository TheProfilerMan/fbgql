"""Synthetic GraphQL response fixtures mirroring Facebook's shapes.

Hand-authored (not copied) minimal structures that exercise the parser's field paths.
"""

from __future__ import annotations

import json

COMMENTS_PAGE = json.dumps(
    {
        "data": {
            "node": {
                "comment_rendering_instance_for_feed_location": {
                    "comments": {
                        "edges": [
                            {
                                "node": {
                                    "legacy_fbid": "111",
                                    "author": {"name": "Alice"},
                                    "created_time": 1690000000,
                                    "body": {"text": "hello world"},
                                    "feedback": {
                                        "id": "fb_comment_1",
                                        "reactors": {"count_reduced": 3},
                                        "expansion_info": {"expansion_token": "exp_tok_1"},
                                    },
                                }
                            },
                            {
                                "node": {
                                    "legacy_fbid": "112",
                                    "author": {"name": "Bob"},
                                    "created_time": 1690000100,
                                    "body": None,  # media-only comment: empty text
                                    "attachments": [
                                        {"__typename": "Photo", "target": {"uri": "https://x/p.jpg"}}
                                    ],
                                    "feedback": {"id": "fb_comment_2", "reactors": {"count": 1}},
                                }
                            },
                        ],
                        "page_info": {"end_cursor": "CURSOR_1", "has_next_page": True},
                    }
                }
            }
        }
    }
)

# Anti-hijacking prefix + a critical error code with no edges (the 1675012 case).
COMMENTS_EMPTY_1675012 = 'for (;;);' + json.dumps(
    {
        "data": {
            "node": {
                "comment_rendering_instance_for_feed_location": {
                    "comments": {"edges": [], "page_info": {"end_cursor": "CURSOR_2",
                                                             "has_next_page": True}}
                }
            }
        },
        "errors": [{"code": 1675012, "severity": "CRITICAL", "message": "empty"}],
    }
)

REPLIES_PAGE = json.dumps(
    {
        "data": {
            "node": {
                "replies_connection": {
                    "edges": [
                        {
                            "node": {
                                "legacy_fbid": "211",
                                "author": {"name": "Carol"},
                                "created_time": 1690000200,
                                "body": {"text": "a reply"},
                                "feedback": {"id": "fb_reply_1", "reactors": {"count_reduced": 0}},
                            }
                        }
                    ]
                }
            }
        }
    }
)

TIMELINE_PAGE = json.dumps(
    {
        "data": {
            "node": {
                "timeline_list_feed_units": {
                    "edges": [
                        {
                            "node": {
                                "post_id": "999",
                                "message": {"text": "a post"},
                                "feedback": {"id": "post_fb_1"},
                                "comet_sections": {
                                    "feedback": {
                                        "story": {
                                            "comment_rendering_instance": {
                                                "comments": {"total_count": 7}
                                            }
                                        }
                                    }
                                },
                                "wwwURL": "https://www.facebook.com/999",
                            }
                        }
                    ],
                    "page_info": {"end_cursor": "NEXT_CURSOR"},
                }
            }
        }
    }
)
