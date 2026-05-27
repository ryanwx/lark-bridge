"""Feishu Drive operations: create folder, upload file."""

import logging
import zlib

import httpx

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
                "https://internal-api-drive-stream.feishu.cn/space/api/box/stream/upload/all/",
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
