"""Feishu Drive operations: create folder, upload file, import, export."""

import json
import logging
import zlib

import httpx

from lark_bridge._urls import DRIVE_STREAM, USER_AGENT

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
            "user-agent": USER_AGENT,
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
            "user-agent": USER_AGENT,
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


async def import_document(
    cookie: str,
    cookies: dict[str, str],
    folder_token: str,
    file_name: str,
    file_content: bytes,
    file_extension: str = "md",
    target_type: str = "docx",
    domain: str = "",
) -> dict | None:
    """Import a file (e.g. markdown) as an online document in Drive.

    Args:
        folder_token: Target folder token.
        file_name: File name (e.g. "report.md").
        file_content: Raw file bytes.
        file_extension: Source format - "md", "docx", "xlsx", etc.
        target_type: Target doc type - "docx", "sheet".

    Returns {"token": "...", "url": "..."} on success, None on failure.
    """
    import asyncio
    import zlib

    headers = {
        "Cookie": cookie,
        "user-agent": USER_AGENT,
        "x-csrftoken": cookies.get("_csrf_token", ""),
        "referer": f"https://{domain}/",
        "origin": f"https://{domain}",
    }
    try:
        async with httpx.AsyncClient(headers=headers, verify=False, timeout=60) as client:
            # Step 1: Prepare upload
            resp = await client.post(
                f"https://{domain}/space/api/box/upload/prepare/",
                json={
                    "mount_point": "ccm_import",
                    "mount_node_token": folder_token,
                    "name": file_name,
                    "size": len(file_content),
                    "extra": {"extra": json.dumps({"obj_type": target_type, "file_extension": file_extension})},
                    "size_checker": True,
                },
                headers={**headers, "content-type": "application/json"},
            )
            result = resp.json()
            if result.get("code") != 0:
                logger.error(f"Import prepare failed: {result.get('message')}")
                return None
            upload_id = result["data"]["upload_id"]

            # Step 2: Upload content
            checksum = zlib.adler32(file_content) & 0xFFFFFFFF
            resp = await client.post(
                f"{DRIVE_STREAM}/space/api/box/stream/upload/merge_block/",
                params={"upload_id": upload_id, "mount_point": "ccm_import"},
                content=file_content,
                headers={
                    **headers,
                    "content-type": "application/octet-stream",
                    "x-block-list-checksum": str(checksum),
                    "x-block-origin-size": "4194304",
                    "x-seq-list": "0",
                },
            )
            result = resp.json()
            if result.get("code") != 0:
                logger.error(f"Import upload block failed: {result.get('message')}")
                return None

            # Step 3: Finish upload
            resp = await client.post(
                f"https://{domain}/space/api/box/upload/finish/",
                json={"upload_id": upload_id, "num_blocks": 1, "mount_point": "ccm_import"},
                headers={**headers, "content-type": "application/json"},
            )
            result = resp.json()
            if result.get("code") != 0:
                logger.error(f"Import finish failed: {result.get('message')}")
                return None
            file_token = result["data"]["file_token"]

            # Step 4: Create import task
            resp = await client.post(
                f"https://{domain}/space/api/import/create/",
                json={
                    "file_token": file_token,
                    "type": target_type,
                    "file_extension": file_extension,
                    "point": {"mount_type": 1, "mount_key": folder_token},
                    "event_source": "1",
                },
                headers={**headers, "content-type": "multipart/form-data"},
            )
            result = resp.json()
            if result.get("code") != 0:
                logger.error(f"Import create failed: {result.get('msg')}")
                return None
            ticket = result["data"]["ticket"]

            # Step 5: Poll for result
            for _ in range(30):
                await asyncio.sleep(1)
                resp = await client.get(
                    f"https://{domain}/space/api/import/result/{ticket}",
                )
                result = resp.json()
                if result.get("code") != 0:
                    logger.error(f"Import poll failed: {result.get('msg')}")
                    return None
                job_result = result.get("data", {}).get("result", {})
                status = job_result.get("job_status")
                if status == 0:
                    token = job_result.get("token", "")
                    url = job_result.get("url", f"https://{domain}/{target_type}/{token}")
                    return {"token": token, "url": url}
                if status == 1 or status == 2:
                    continue
                logger.error(f"Import failed with status: {status}")
                return None
            logger.error("Import timed out")
            return None
    except Exception as e:
        logger.error(f"Import document error: {e}")
        return None


async def download_file(cookie: str, cookies: dict[str, str], file_token: str, domain: str = "") -> bytes | None:
    """Download a file from Drive by its file_token.

    Returns file bytes on success, None on failure.
    """
    headers = {
        "Cookie": cookie,
        "user-agent": USER_AGENT,
        "x-csrftoken": cookies.get("_csrf_token", ""),
        "referer": f"https://{domain}/",
    }
    try:
        async with httpx.AsyncClient(headers=headers, verify=False, timeout=60) as client:
            resp = await client.get(
                f"{DRIVE_STREAM}/space/api/box/stream/download/all/{file_token}/",
            )
            if resp.status_code != 200:
                logger.error(f"Download file failed: {resp.status_code}")
                return None
            return resp.content
    except Exception as e:
        logger.error(f"Download file error: {e}")
        return None


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
        "user-agent": USER_AGENT,
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


async def list_my_space(cookie: str, cookies: dict[str, str], domain: str = "") -> list[dict]:
    """List root folders in 'My Space'.

    Returns list of {"token", "name", "type", "url", "edit_time"} or empty list.
    """
    headers = {
        "Cookie": cookie,
        "user-agent": USER_AGENT,
        "x-csrftoken": cookies.get("_csrf_token", ""),
        "referer": f"https://{domain}/drive/me/",
    }
    try:
        async with httpx.AsyncClient(headers=headers, verify=False, timeout=15) as client:
            resp = await client.get(
                f"https://{domain}/space/api/explorer/v3/my_space/folder/",
                params={"asc": "0", "rank": "3", "length": "50"},
            )
            result = resp.json()
            if result.get("code") != 0:
                logger.error(f"list_my_space failed: {result.get('msg')}")
                return []
            return _parse_node_list(result.get("data", {}))
    except Exception as e:
        logger.error(f"list_my_space error: {e}")
        return []


async def list_shared_folders(cookie: str, cookies: dict[str, str], domain: str = "") -> list[dict]:
    """List root folders in 'Shared Space'.

    Returns list of {"token", "name", "type", "url", "edit_time"} or empty list.
    """
    headers = {
        "Cookie": cookie,
        "user-agent": USER_AGENT,
        "x-csrftoken": cookies.get("_csrf_token", ""),
        "referer": f"https://{domain}/drive/shared/",
    }
    try:
        async with httpx.AsyncClient(headers=headers, verify=False, timeout=15) as client:
            resp = await client.get(
                f"https://{domain}/space/api/explorer/v2/share/folder/list/",
                params={"asc": "0", "rank": "3", "length": "50"},
            )
            result = resp.json()
            if result.get("code") != 0:
                logger.error(f"list_shared_folders failed: {result.get('msg')}")
                return []
            return _parse_node_list(result.get("data", {}))
    except Exception as e:
        logger.error(f"list_shared_folders error: {e}")
        return []


async def list_children(cookie: str, cookies: dict[str, str], folder_token: str, domain: str = "") -> list[dict]:
    """List children (files + subfolders) of a folder.

    Returns list of {"token", "name", "type", "url", "edit_time"} or empty list.
    """
    headers = {
        "Cookie": cookie,
        "user-agent": USER_AGENT,
        "x-csrftoken": cookies.get("_csrf_token", ""),
        "referer": f"https://{domain}/drive/folder/{folder_token}",
    }
    try:
        async with httpx.AsyncClient(headers=headers, verify=False, timeout=15) as client:
            resp = await client.get(
                f"https://{domain}/space/api/explorer/v3/children/list/",
                params={"token": folder_token, "asc": "0", "rank": "3", "length": "50"},
            )
            result = resp.json()
            if result.get("code") != 0:
                logger.error(f"list_children failed: {result.get('msg')}")
                return []
            return _parse_node_list(result.get("data", {}))
    except Exception as e:
        logger.error(f"list_children error: {e}")
        return []


async def delete_nodes(cookie: str, cookies: dict[str, str], tokens: list[str], domain: str = "") -> bool:
    """Delete files/folders by their node tokens. Returns True on success."""
    headers = {
        "Cookie": cookie,
        "content-type": "application/json",
        "user-agent": USER_AGENT,
        "x-csrftoken": cookies.get("_csrf_token", ""),
        "referer": f"https://{domain}/",
        "origin": f"https://{domain}",
    }
    try:
        async with httpx.AsyncClient(headers=headers, verify=False, timeout=15) as client:
            resp = await client.post(
                f"https://{domain}/space/api/explorer/v3/remove/",
                json={"tokens": tokens, "apply": 1},
            )
            result = resp.json()
            if result.get("code") != 0:
                logger.error(f"delete_nodes failed: {result.get('msg')}")
                return False
            return True
    except Exception as e:
        logger.error(f"delete_nodes error: {e}")
        return False


# Type code to human-readable name
_TYPE_NAMES = {0: "folder", 2: "doc", 3: "sheet", 22: "docx", 8: "bitable", 12: "mindnote"}


def _parse_node_list(data: dict) -> list[dict]:
    """Parse the common node list response format."""
    nodes_map = data.get("entities", {}).get("nodes", {})
    node_order = data.get("node_list", [])
    # If no explicit order, use dict keys
    if not node_order:
        node_order = list(nodes_map.keys())
    items = []
    for token in node_order:
        node = nodes_map.get(token, {})
        if not node:
            continue
        type_code = node.get("type", -1)
        items.append(
            {
                "token": node.get("token", token),
                "obj_token": node.get("obj_token", ""),
                "name": node.get("name", ""),
                "type": _TYPE_NAMES.get(type_code, f"type_{type_code}"),
                "type_code": type_code,
                "url": node.get("url", ""),
                "edit_time": node.get("edit_time", 0),
            }
        )
    return items
