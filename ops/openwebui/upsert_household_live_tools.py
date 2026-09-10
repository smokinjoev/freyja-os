import asyncio
import json

from open_webui.models.tools import ToolForm, ToolMeta, Tools
from open_webui.utils.plugin import load_tool_module_by_id
from open_webui.utils.tools import get_tool_specs


WEATHER = r'''
"""Live weather lookup through Open-Meteo for OpenWebUI."""

import json
import urllib.parse
import urllib.request


class Tools:
    def weather_read(self, location: str = "Aiken, South Carolina") -> str:
        """Return current weather for a location using live Open-Meteo data."""
        try:
            geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
                {"name": location, "count": 1, "language": "en", "format": "json"}
            )
            with urllib.request.urlopen(geo_url, timeout=10) as response:
                geo = json.loads(response.read().decode("utf-8"))
            results = geo.get("results") or []
            if not results:
                return f"Weather lookup failed: location not found for {location!r}."
            place = results[0]
            display = ", ".join(str(part) for part in (place.get("name"), place.get("admin1"), place.get("country")) if part)
            params = {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "auto",
                "forecast_days": 1,
            }
            weather_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
            with urllib.request.urlopen(weather_url, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            current = data.get("current") or {}
            return json.dumps(
                {
                    "ok": True,
                    "source": "Open-Meteo",
                    "location": display,
                    "temperature_f": current.get("temperature_2m"),
                    "feels_like_f": current.get("apparent_temperature"),
                    "humidity_percent": current.get("relative_humidity_2m"),
                    "wind_mph": current.get("wind_speed_10m"),
                    "weather_code": current.get("weather_code"),
                    "observation_time": current.get("time"),
                },
                indent=2,
                sort_keys=True,
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True)
'''


HOME_ASSISTANT = r'''
"""Read-only Home Assistant status through Iris-side Freyja config."""

import json
import shlex
import subprocess
from typing import Literal


class Tools:
    _SSH_BASE = [
        "ssh",
        "-i",
        "/app/backend/data/ssh/openwebui_status_ed25519",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "UserKnownHostsFile=/app/backend/data/ssh/known_hosts",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "freyja@100.115.228.56",
    ]

    def _iris_python(self, code: str, timeout: int = 20) -> str:
        remote = "cd ~/freyja-os && PYTHONPATH=src .venv/bin/python -c " + shlex.quote(code)
        try:
            result = subprocess.run([*self._SSH_BASE, remote], capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return json.dumps({"ok": False, "error": f"timeout after {timeout}s"})
        output = (result.stdout or result.stderr or "").strip()
        if len(output) > 12000:
            output = output[:12000] + "\n[truncated]"
        return output

    def home_status(self, domain: Literal["light", "switch", "sensor", "binary_sensor", "climate", "all"] = "light") -> str:
        """Return read-only Home Assistant state summaries; use light for “how many lights are on”."""
        selected = "" if domain == "all" else domain
        code = (
            "import asyncio,json;"
            "from freyja.tools.home_assistant import _list_states;"
            "from freyja.tools.models import ToolExecutionRequest;"
            f"args={{'domain':{selected!r}}};"
            "result=asyncio.run(_list_states(ToolExecutionRequest(tool_name='home_status', arguments=args, actor='open-webui')));"
            "lights=[e for e in result.get('entities',[]) if e.get('domain')=='light'];"
            "result['lights_on_count']=sum(1 for e in lights if e.get('is_on'));"
            "result['lights_total_count']=len(lights);"
            "print(json.dumps(result, indent=2, sort_keys=True))"
        )
        return self._iris_python(code, timeout=75)

    def home_device_action(self) -> str:
        """Report that device actions require approval and are not exposed through this read-only tool."""
        return "Device actions are not available from this Open WebUI read-only tool. Ask for approval through Freyja before changing devices."
'''


IRIS_APPLE = r'''
"""Read-only Iris Apple calendar/reminder status through MacAgent."""

import json
import shlex
import subprocess


class Tools:
    _SSH_BASE = [
        "ssh",
        "-i",
        "/app/backend/data/ssh/openwebui_status_ed25519",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "UserKnownHostsFile=/app/backend/data/ssh/known_hosts",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "freyja@100.115.228.56",
    ]

    def _iris_python(self, code: str, timeout: int = 25) -> str:
        remote = "cd ~/freyja-os && PYTHONPATH=src .venv/bin/python -c " + shlex.quote(code)
        try:
            result = subprocess.run([*self._SSH_BASE, remote], capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return json.dumps({"ok": False, "error": f"timeout after {timeout}s"})
        output = (result.stdout or result.stderr or "").strip()
        if len(output) > 12000:
            output = output[:12000] + "\n[truncated]"
        return output

    def calendar_read(self, days: int = 14) -> str:
        """Return family calendar events for the next N days through Iris MacAgent/local calendar config."""
        bounded_days = max(1, min(int(days), 60))
        code = (
            "import asyncio,json,datetime as d;"
            "from freyja.tools.calendar import build_calendar_service;"
            " svc=build_calendar_service();"
            " start=d.datetime.now(d.UTC); end=start+d.timedelta(days=" + str(bounded_days) + ");"
            " events=asyncio.get_event_loop().run_until_complete(svc.list_events(start=start,end=end,calendar_ids=['family']));"
            " print(json.dumps({'ok':True,'days':" + str(bounded_days) + ",'count':len(events),'events':[e.model_dump(mode='json') for e in events]}, indent=2, sort_keys=True))"
        )
        return self._iris_python(code)

    def reminders_read(self) -> str:
        """Report reminder read status."""
        return "Reminder read is not wired yet; calendar_read is available."

    def calendar_create(self) -> str:
        """Calendar writes require explicit approval and are not exposed from this read-only tool."""
        return "Calendar creation requires approval and is not exposed from this Open WebUI read-only tool."

    def reminders_create(self) -> str:
        """Reminder writes require explicit approval and are not exposed from this read-only tool."""
        return "Reminder creation requires approval and is not exposed from this Open WebUI read-only tool."

    def imessage_send_approved(self) -> str:
        """Messaging requires explicit approval and is not exposed from this read-only tool."""
        return "iMessage sending requires approval and is not exposed from this Open WebUI read-only tool."

    def shortcuts_run(self) -> str:
        """Shortcut runs require explicit approval and are not exposed from this read-only tool."""
        return "Shortcut execution requires approval and is not exposed from this Open WebUI read-only tool."
'''


TOOLS = {
    "weather": ("Weather", "Live read-only weather lookup through Open-Meteo.", WEATHER),
    "home_assistant": ("Home Assistant", "Read-only Home Assistant status through Iris-side Freyja config.", HOME_ASSISTANT),
    "iris_apple": ("Iris Apple Capabilities", "Read-only family calendar through Iris; write operations return approval guidance.", IRIS_APPLE),
}


async def upsert_tool(tool_id: str, name: str, description: str, content: str) -> None:
    module, frontmatter = await load_tool_module_by_id(tool_id, content=content)
    specs = get_tool_specs(module)
    form = ToolForm(
        id=tool_id,
        name=name,
        content=content,
        meta=ToolMeta(description=description, manifest=frontmatter, has_user_valves=False),
        access_grants=[],
    )
    existing = await Tools.get_tool_by_id(tool_id)
    if existing:
        updated = await Tools.update_tool_by_id(
            tool_id,
            {
                "name": form.name,
                "content": form.content,
                "specs": specs,
                "meta": form.meta.model_dump(),
                "valves": {},
            },
        )
        print("updated", updated.id, [spec["name"] for spec in specs])
    else:
        created = await Tools.insert_new_tool("codex-local", form, specs)
        print("created", created.id, [spec["name"] for spec in specs])


async def main() -> None:
    for tool_id, (name, description, content) in TOOLS.items():
        await upsert_tool(tool_id, name, description, content)


asyncio.run(main())
