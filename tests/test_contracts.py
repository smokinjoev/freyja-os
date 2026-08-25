from freyja.contracts import CanonicalAttachment, CanonicalRequest, CanonicalResponse, CanonicalSender
from connectors.messaging import NormalizedAttachment, NormalizedMessage


def test_canonical_request_and_response_contracts_are_channel_neutral() -> None:
    request = CanonicalRequest(
        trace_id="trace-1",
        message_id="msg-1",
        channel="signal",
        conversation_id="conv-1",
        sender=CanonicalSender(channel_id="sender-1", address="+15550000000"),
        resolved_user_id="person-joe",
        resolved_agent_id="cloyd",
        text="analyze this",
        attachments=[
            CanonicalAttachment(
                attachment_id="att-1",
                media_type="application/pdf",
                filename="report.pdf",
                size=123,
                source="signal",
                reference="signal-attachment:1",
            )
        ],
        permissions=["memory:read"],
    )

    response = CanonicalResponse(
        trace_id=request.trace_id,
        request_message_id=request.message_id,
        channel=request.channel,
        conversation_id=request.conversation_id,
        resolved_user_id=request.resolved_user_id,
        resolved_agent_id=request.resolved_agent_id,
        text="done",
    )

    assert request.attachments[0].media_type == "application/pdf"
    assert response.trace_id == "trace-1"
    assert response.status == "ok"
    assert response.tool_results == []


def test_normalized_message_converts_to_canonical_request() -> None:
    message = NormalizedMessage(
        transport="imessage",
        sender="joe@example.com",
        conversation_id="conv-1",
        message_id="msg-1",
        text="look at this",
        thread_id="thread-1",
        attachments=[
            NormalizedAttachment(
                filename="photo.png",
                mime_type="image/png",
                size_bytes=42,
                local_ref="imessage:attachment:1",
            )
        ],
        authorized=True,
    )

    request = message.to_canonical_request(
        resolved_user_id="person-joe",
        resolved_agent_id="cloyd",
        permissions=["tools:weather"],
    )

    assert request.channel == "imessage"
    assert request.sender.channel_id == "joe@example.com"
    assert request.resolved_user_id == "person-joe"
    assert request.resolved_agent_id == "cloyd"
    assert request.attachments[0].reference == "imessage:attachment:1"
    assert request.channel_metadata["authorized"] is True
