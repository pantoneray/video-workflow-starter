#!/usr/bin/env python3
"""Cross-platform YouTube OAuth, channel verification and private upload.

Extracts the proven verification/MediaFileUpload pattern from youtube_api.py.
Tokens live in the OS credential store through keyring, never in the package.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from config_paths import resolve_path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly",
          "openid", "email"]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def store(channel_id):
    import keyring
    backend = keyring.get_keyring()
    module = type(backend).__module__
    expected = {"darwin": "keyring.backends.macOS", "win32": "keyring.backends.Windows"}.get(sys.platform)
    if not expected or not module.startswith(expected):
        raise RuntimeError("仅支持 macOS Keychain 或 Windows Credential Manager；当前未找到对应安全存储")
    # v2 adds Google account identity scopes; do not silently reuse old-scope credentials.
    return keyring, "video-workflow-starter-youtube-v2", channel_id


def client_binding(client_file, expected_project_id):
    data = json.loads(Path(client_file).read_text(encoding="utf-8"))
    installed = data.get("installed") or {}
    project_id, client_id = installed.get("project_id"), installed.get("client_id")
    if not project_id or not client_id or project_id != expected_project_id:
        raise ValueError("OAuth Desktop 客户端的 GCP 项目 ID 与预期不一致")
    return {"gcp_project_id": project_id, "client_id": client_id}


def credentials(channel_id, client_file, expected_project_id, expected_email, allow_login=False):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    binding = client_binding(client_file, expected_project_id)
    keyring, service, account = store(channel_id)
    raw = keyring.get_password(service, account)
    if raw:
        creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
        if creds.client_id != binding["client_id"]:
            raise ValueError("现有 OAuth 凭据不属于指定 GCP 项目的客户端；已停止")
        if not creds.has_scopes(SCOPES):
            raise ValueError("现有授权缺少频道读取或上传权限，请重新授权")
        if not creds.valid:
            creds.refresh(Request())
            keyring.set_password(service, account, creds.to_json())
        return creds
    if not allow_login:
        raise ValueError("本机尚未授权该频道；请由本人显式运行 auth")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
    creds = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        raise ValueError("授权未返回 refresh token")
    if creds.client_id != binding["client_id"]:
        raise ValueError("新 OAuth 凭据的客户端与指定 GCP 项目不一致")
    # Verify both account and channel before saving the credential.
    verify_identity(creds, channel_id, expected_email, expected_project_id)
    keyring.set_password(service, account, creds.to_json())
    return creds


def verify_identity(creds, channel_id, expected_email, gcp_project_id):
    from google.auth.transport.requests import AuthorizedSession
    response = AuthorizedSession(creds).get("https://openidconnect.googleapis.com/v1/userinfo", timeout=20)
    response.raise_for_status()
    profile = response.json()
    email = profile.get("email")
    if (not profile.get("email_verified") or not email or
            email.casefold() != expected_email.casefold() or not profile.get("sub")):
        raise ValueError("Google OAuth 账号邮箱未验证或与预期不一致")
    channel = verify_channel(creds, channel_id)
    return {**channel, "google_account_email": email, "gcp_project_id": gcp_project_id,
            "account_verified": True, "channel_verified": True}


def api(creds):
    from googleapiclient.discovery import build
    from google_auth_httplib2 import AuthorizedHttp
    import httplib2
    return build("youtube", "v3", http=AuthorizedHttp(creds, http=httplib2.Http(timeout=30)),
                 cache_discovery=False)


def read_request(request):
    for attempt in range(3):
        try:
            return request.execute()
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            transient = isinstance(exc, (OSError, TimeoutError)) or status in (429, 500, 502, 503, 504)
            if not transient or attempt == 2:
                raise
            time.sleep(2 ** attempt)


def verify_channel(creds, expected_id):
    response = read_request(api(creds).channels().list(part="id,snippet", mine=True))
    items = response.get("items") or []
    if expected_id not in [x.get("id") for x in items]:
        raise ValueError("OAuth 当前频道与 --channel-id 不一致，已停止")
    return {"channel_id": expected_id, "title": next(x.get("snippet", {}).get("title") for x in items if x.get("id") == expected_id)}


def reconcile(creds, expected_channel, video_id):
    response = read_request(api(creds).videos().list(part="id,status,snippet,processingDetails", id=video_id))
    items = response.get("items") or []
    if len(items) != 1 or items[0].get("id") != video_id:
        raise ValueError("未在授权频道查到此视频")
    item = items[0]
    if item.get("snippet", {}).get("channelId") != expected_channel:
        raise ValueError("视频不属于指定频道")
    return {"video_id": video_id, "channel_id": expected_channel,
            "privacyStatus": item.get("status", {}).get("privacyStatus"),
            "uploadStatus": item.get("status", {}).get("uploadStatus"),
            "processingStatus": item.get("processingDetails", {}).get("processingStatus"),
            "title": item.get("snippet", {}).get("title"),
            "description": item.get("snippet", {}).get("description"),
            "tags": item.get("snippet", {}).get("tags") or [],
            "thumbnails": item.get("snippet", {}).get("thumbnails", {})}


def wait_processing(creds, channel_id, video_id, timeout=600, interval=15):
    deadline = time.monotonic() + timeout
    while True:
        current = reconcile(creds, channel_id, video_id)
        if current["privacyStatus"] != "private":
            raise ValueError("远端视频不再是 private，已停止")
        if current["processingStatus"] in ("succeeded", "failed", "terminated"):
            return current
        if time.monotonic() + interval > deadline:
            return {**current, "wait_status": "timeout; continue with wait-processing, do not reupload"}
        time.sleep(interval)


def verify_thumbnail_upload(upload_receipt, approved, video_id, channel_id, expected_email, project_id):
    receipt = json.loads(Path(upload_receipt).read_text(encoding="utf-8"))
    if (receipt.get("video_id") != video_id or receipt.get("channel_id") != channel_id
            or receipt.get("privacyStatus") != "private"
            or receipt.get("publication_candidate_sha256") != approved["candidate_sha256"]
            or receipt.get("sha256") != approved["video_sha256"]
            or str(receipt.get("google_account_email", "")).casefold() != expected_email.casefold()
            or receipt.get("gcp_project_id") != project_id):
        raise ValueError("封面任务与本次已批准的私密上传回执、账号或成片不一致")
    return sha256(upload_receipt)


def set_thumbnail(creds, channel_id, video_id, image_path, receipt,
                  candidate_hash=None, upload_receipt_hash=None):
    from googleapiclient.http import MediaFileUpload
    image = Path(image_path)
    if not image.is_file() or image.suffix.lower() not in (".jpg", ".jpeg", ".png") or image.stat().st_size > 50_000_000:
        raise ValueError("封面须为不超过 50 MB 的 JPEG/PNG")
    checked = reconcile(creds, channel_id, video_id)
    if checked["privacyStatus"] != "private" or checked["processingStatus"] != "succeeded":
        raise ValueError("仅在所属频道私密视频处理成功后设置封面")
    image_hash = sha256(image)
    write_new(receipt, {"status": "thumbnail_outcome_unknown", "video_id": video_id,
                        "channel_id": channel_id, "image_sha256": image_hash})
    response = api(creds).thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(image))).execute()
    if not response.get("items"):
        raise ValueError("封面设置结果不明；先回查远端，不要盲目再次上传")
    checked = reconcile(creds, channel_id, video_id)
    result = {"video_id": video_id, "channel_id": channel_id, "image_sha256": image_hash,
              "processingStatus": checked["processingStatus"], "remote_thumbnails": checked["thumbnails"],
              "publication_candidate_sha256": candidate_hash,
              "upload_receipt_sha256": upload_receipt_hash,
              "status": "submitted; inspect the actual thumbnail in YouTube Studio"}
    write_new(str(receipt) + ".result.json", result)
    return result


def upload(creds, channel_id, path, title, description, out, tags=None):
    from googleapiclient.http import MediaFileUpload
    path = Path(path)
    if not path.is_file(): raise FileNotFoundError(path)
    if not title.strip(): raise ValueError("标题不能为空")
    if tags is not None and (not isinstance(tags, list) or any(not isinstance(x, str) for x in tags)):
        raise ValueError("tags 须为字符串列表")
    channel = verify_channel(creds, channel_id)
    fingerprint = sha256(path)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / "intent.json", {"status": "upload_outcome_unknown", "file_name": path.name,
                                    "sha256": fingerprint, "channel_id": channel_id,
                                    "title": title, "description": description, "tags": tags or [],
                                    "privacyStatus": "private"})
    body = {"snippet": {"title": title, "description": description, "categoryId": "22", "tags": tags or []},
            "status": {"privacyStatus": "private"}}
    media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
    request = api(creds).videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk(num_retries=0)
    video_id = response.get("id")
    if not video_id:
        raise ValueError("上传响应缺 video_id；先查远端，勿重复上传")
    write_new(out / "upload-response.json", {"video_id": video_id, "channel_id": channel_id,
                                               "privacyStatus": (response.get("status") or {}).get("privacyStatus")})
    checked = reconcile(creds, channel_id, video_id)
    write_new(out / "reconcile.json", checked)
    if checked.get("privacyStatus") != "private":
        raise ValueError("远端隐私状态不是 private；需人工检查，不得报告私密上传成功")
    if (checked.get("title") != title or checked.get("description") != description
            or checked.get("tags") != (tags or [])):
        raise ValueError("远端标题、简介或 tags 与审核稿不同；需人工核查")
    return {**checked, "sha256": fingerprint, "channel_title": channel["title"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    a = sub.add_parser("auth")
    a = sub.add_parser("verify")
    a = sub.add_parser("upload-private"); a.add_argument("--file", required=True); a.add_argument("--out", required=True)
    a.add_argument("--candidate", required=True); a.add_argument("--publication-decision", required=True)
    a.add_argument("--version", required=True); a.add_argument("--approval", required=True)
    a = sub.add_parser("reconcile"); a.add_argument("--video-id", required=True)
    a = sub.add_parser("wait-processing"); a.add_argument("--video-id", required=True); a.add_argument("--timeout", type=int, default=600); a.add_argument("--out", required=True)
    a = sub.add_parser("set-thumbnail"); a.add_argument("--video-id", required=True); a.add_argument("--image", required=True); a.add_argument("--upload-receipt", required=True); a.add_argument("--receipt", required=True)
    a.add_argument("--candidate", required=True); a.add_argument("--publication-decision", required=True)
    a.add_argument("--version", required=True); a.add_argument("--approval", required=True)
    for command in sub.choices.values():
        command.add_argument("--config", required=True, help="包外本人账号/GCP 项目配置 JSON")
    args = p.parse_args()
    try:
        if args.action == "wait-processing" and Path(args.out).exists():
            raise FileExistsError("处理状态回执已存在；使用新文件名保存下一次检查")
        config_path = Path(args.config).expanduser().resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        channel_id = config["channel_id"]
        expected_email = config["expected_email"]
        project_id = config["gcp_project_id"]
        client_file = str(resolve_path(config["client_secret_path"], config_path.parent))
        approved = None
        if args.action in ("upload-private", "set-thumbnail"):
            from publication_review import verify as verify_publication
            approved = verify_publication(args.candidate, args.publication_decision,
                                          args.version, args.approval,
                                          args.image if args.action == "set-thumbnail" else None,
                                          args.file if args.action == "upload-private" else None)
        upload_receipt_hash = (verify_thumbnail_upload(args.upload_receipt, approved, args.video_id,
                                                       channel_id, expected_email, project_id)
                               if args.action == "set-thumbnail" else None)
        creds = credentials(channel_id, client_file, project_id, expected_email,
                            allow_login=args.action == "auth")
        identity = verify_identity(creds, channel_id, expected_email, project_id)
        if args.action in ("auth", "verify"):
            result = identity
        elif args.action == "upload-private":
            result = {**upload(creds, channel_id, args.file, approved["title"], approved["description"], args.out, approved["tags"]),
                      "publication_candidate_sha256": approved["candidate_sha256"],
                      "google_account_email": identity["google_account_email"], "gcp_project_id": project_id}
            write_new(Path(args.out) / "upload-verified.json", result)
        elif args.action == "wait-processing":
            result = {**wait_processing(creds, channel_id, args.video_id, args.timeout),
                      "google_account_email": identity["google_account_email"], "gcp_project_id": project_id}
            write_new(args.out, result)
        elif args.action == "set-thumbnail":
            result = set_thumbnail(creds, channel_id, args.video_id, args.image, args.receipt,
                                   approved["candidate_sha256"], upload_receipt_hash)
        else:
            result = reconcile(creds, channel_id, args.video_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "message": str(exc) if isinstance(exc, (ValueError, FileNotFoundError, FileExistsError)) else "检查本地回执；结果未知时勿重新上传"}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
