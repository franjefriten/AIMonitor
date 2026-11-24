import pytest

from aimonitor.exporters.http import WebhookExporter


@pytest.mark.asyncio
async def test_webhook_description_does_not_expose_credentials():
    exporter = WebhookExporter(
        url="https://user:url-password@example.com/hook?api_key=url-key",
        headers={
            "Authorization": "Bearer header-token",
            "X-Api-Key": "header-api-key",
        },
        auth=("basic-user", "basic-password"),
    )
    await exporter.connect()
    try:
        description = await exporter.describe()
    finally:
        await exporter.close()

    rendered_description = repr(description)
    for credential in (
        "url-password",
        "url-key",
        "header-token",
        "header-api-key",
        "basic-user",
        "basic-password",
    ):
        assert credential not in rendered_description
