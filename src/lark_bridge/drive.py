"""Feishu Drive operations: create folder, upload file."""

import logging
import zlib

import httpx

from lark_bridge._urls import DRIVE_STREAM

logger = logging.getLogger(__name__)


async def create_folder(
    cookie: str, cookies: dict[str, str], name: str, parent_token: str = "", domain: str = ""
) -> dict | None:
    """Create a folder in Feishu Drive.

    Returns {"token": "...", "url": "..."} or None.
    """
    try:
        headers = {
            "Cookie": cookie,
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-csrftoken": cookies.get("_csrf_token", ""),
            "referer": f"https://{domain}/",
            "origin": f"https://{domain}",
        }
        data = f"parent_token={parent_token}&name={name}&desc=&source=0"
        async with httpx.AsyncClient(headers=headers, verify=False, timeout=15) as client:
            resp = await client.post(
                f"https://{domain}/space/api/explorer/v2/create/folder/",
                content=data,
            )
            result = resp.json()
            if result.get("code") != 0:
                logger.error(f"Create folder failed: {result.get('msg')}")
                return None
            nodes = result.get("data", {}).get("entities", {}).get("nodes", {})
            node = next(iter(nodes.values()), {})
            return {"token": node.get("token", ""), "url": node.get("url", "")}
    except Exception as e:
        logger.error(f"Create folder error: {e}")
        return None


async def upload_file(
    cookie: str,
    cookies: dict[str, str],
    folder_token: str,
    file_name: str,
    file_content: bytes,
    domain: str = "",
) -> dict | None:
    """Upload a file to Feishu Drive.

    Returns {"file_token": "...", "node_token": "..."} or None.
    """
    try:
        checksum = zlib.adler32(file_content) & 0xFFFFFFFF
        params = {
            "name": file_name,
            "size": len(file_content),
            "checksum": str(checksum),
            "mount_node_token": folder_token,
            "mount_point": "explorer",
            "push_open_history_record": "1",
            "size_checker": "true",
        }
        headers = {
            "Cookie": cookie,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-csrftoken": cookies.get("_csrf_token", ""),
            "referer": f"https://{domain}/",
            "origin": f"https://{domain}",
        }
        async with httpx.AsyncClient(headers=headers, verify=False, timeout=60) as client:
            resp = await client.post(
                f"{DRIVE_STREAM}/space/api/box/stream/upload/all/",
                params=params,
                files={"file": (file_name, file_content)},
            )
            result = resp.json()
            if result.get("code") != 0:
                logger.error(f"Upload file failed: {result.get('message')}")
                return None
            data = result.get("data", {})
            file_token = data.get("file_token", "")
            return {
                "file_token": file_token,
                "node_token": data.get("extra", {}).get("node_token", ""),
                "url": f"https://{domain}/file/{file_token}",
            }
    except Exception as e:
        logger.error(f"Upload file error: {e}")
        return None


OBJ_TYPE_MAP = {22: "docx", 3: "sheet", 2: "doc"}


async def _resolve_wiki_token(cookie: str, cookies: dict[str, str], wiki_token: str, domain: str) -> tuple[str, str]:
    """Resolve wiki_token to (obj_token, type). Returns ("", "") on failure."""
    headers = {
        "Cookie": cookie,
        "x-csrftoken": cookies.get("_csrf_token", ""),
    }
    try:
        async with httpx.AsyncClient(headers=headers, verify=False, timeout=10) as client:
            resp = await client.get(
                f"https://{domain}/space/api/wiki/v2/tree/get_node/",
                params={"wiki_token": wiki_token, "expand_shortcut": "true"},
            )
            data = resp.json().get("data", {})
            obj_token = data.get("obj_token", "")
            obj_type = OBJ_TYPE_MAP.get(data.get("obj_type"), "")
            return obj_token, obj_type
    except Exception as e:
        logger.error(f"Resolve wiki token error: {e}")
        return "", ""


async def export_document(
    cookie: str,
    cookies: dict[str, str],
    token: str,
    type: str,
    file_extension: str,
    domain: str = "",
) -> bytes | None:
    """Export a document and download as bytes.

    Args:
        token: Document token (e.g. from URL).
        type: Document type - "docx", "sheet", "doc".
        file_extension: Export format - "markdown", "docx", "pdf", "xlsx", "csv".

    Returns file bytes on success, None on failure.
    """
    import asyncio

    headers = {
        "Cookie": cookie,
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-csrftoken": cookies.get("_csrf_token", ""),
        "referer": f"https://{domain}/",
    }
    try:
        async with httpx.AsyncClient(headers=headers, verify=False, timeout=30) as client:
            # Step 1: Create export task
            resp = await client.post(
                f"https://{domain}/space/api/export/create/",
                json={"token": token, "type": type, "file_extension": file_extension, "event_source": "6"},
            )
            result = resp.json()
            if result.get("code") != 0:
                logger.error(f"Export create failed: {result.get('msg')}")
                return None
            job_id = result.get("data", {}).get("ticket")
            if not job_id:
                logger.error(f"Export create: no ticket in response: {result}")
                return None

            # Step 2: Poll for result
            for _ in range(30):
                await asyncio.sleep(1)
                resp = await client.get(
                    f"https://{domain}/space/api/export/result/{job_id}",
                    params={"token": token, "type": type},
                )
                result = resp.json()
                if result.get("code") != 0:
                    logger.error(f"Export poll failed: {result.get('msg')}")
                    return None
                job_result = result.get("data", {}).get("result", {})
                status = job_result.get("job_status")
                if status == 0 or (status == 2 and job_result.get("file_token")):
                    file_token = job_result["file_token"]
                    break
                if status == 1 or status == 2:  # processing or pending
                    continue
                logger.error(f"Export failed with status: {status}")
                return None
            else:
                logger.error("Export timed out")
                return None

            # Step 3: Download file
            resp = await client.get(
                f"{DRIVE_STREAM}/space/api/box/stream/download/all/{file_token}/",
            )
            if resp.status_code != 200:
                logger.error(f"Export download failed: {resp.status_code}")
                return None
            return resp.content
    except Exception as e:
        logger.error(f"Export document error: {e}")
        return None
