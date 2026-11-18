"""Pack and verify the private ccNC Theme module for Seogaemo 0.1.54."""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
import zipfile
import zlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


MODULE_ID = "ccnc-theme-5w"
PRODUCT_GLOB = "GL3*"
SETTING = "progress_enabled"
REQUIRED_TEXT = ("module.properties", "apply.sh", "strings/en.txt", "strings/ko.txt")
OPTIONAL_TEXT = ("check.sh", "status.sh", "ui.txt", "README.md")
MAX_ARCHIVE = 10 * 1024 * 1024  # USB import limit in core/module.sh.
MAX_EXPANDED = 16 * 1024 * 1024  # HmgSeogaemoHsmExtract.java.
MAX_ENTRIES = 256
NAME = re.compile(r"[a-z0-9_]+")
HOOK_PATH = re.compile(r"files/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+\.jar")
HOOK_CLASS = re.compile(r"[A-Za-z0-9_$]+(?:\.[A-Za-z0-9_$]+)+")
HOOK_PROCESS = re.compile(r"[A-Za-z0-9_.:]+")
SCRIPT_TOKEN = re.compile(r'"((?:[^"\\]|\\["\\])+?)"(?= |$)|([^ "\\]+)(?= |$)')


def content_lines(data: bytes, member: str) -> list[str]:
    if re.search(rb"[\x00-\x09\x0b-\x1f\x7f]", data):
        raise ValueError(f"{member}: use UTF-8 with LF line endings and no control characters")
    text = data.decode("utf-8")
    if text.startswith("\ufeff"):
        raise ValueError(f"{member}: UTF-8 BOM is not supported")
    return text.removesuffix("\n").split("\n")


def read_entries(data: bytes, member: str) -> dict[str, str]:
    entries = {}
    for line in content_lines(data, member):
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not key or key in entries:
            raise ValueError(f"{member}: invalid or repeated key {key!r}")
        entries[key] = value
    return entries


def module_properties(data: bytes) -> dict[str, str]:
    props = read_entries(data, "module.properties")
    required_values = {
        "id": MODULE_ID,
        "api": "1",
        "cars": PRODUCT_GLOB,
        "setting.1": f"{SETTING}:toggle:on",
    }
    for key, expected in required_values.items():
        if props.get(key) != expected:
            raise ValueError(f"module.properties: expected {key}={expected}")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", props.get("version", "")):
        raise ValueError("module.properties: version must use N.N.N")
    # core/module.sh generates restart=head_unit for every hook_apps module.
    if props.get("restart", "head_unit") != "head_unit":
        raise ValueError("module.properties: hook_apps requires a head unit restart")
    icons = {"box", "wifi", "phone", "terminal", "car", "gear", "display", "speaker", "camera",
             "map", "power", "key", "skip", "button", "link", "bolt"}
    if props.get("icon", "box") not in icons:
        raise ValueError("module.properties: icon is unsupported")
    extras = props.keys() - required_values.keys() - {"version", "restart", "icon"}
    if extras:
        raise ValueError(f"module.properties: unsupported keys {', '.join(sorted(extras))}")
    return props


def script_lines(data: bytes, member: str) -> list[list[str]]:
    lines = content_lines(data, member)
    if len(lines) > 512:
        raise ValueError(f"{member}: more than 512 lines")
    commands = []
    for number, line in enumerate(lines, 1):
        rest = line.strip(" ")
        if not rest or rest.startswith("#"):
            continue
        tokens = []
        while rest:
            token = SCRIPT_TOKEN.match(rest)
            if token is None:
                raise ValueError(f"{member}:{number}: invalid Seogaemo quoting")
            quoted, literal = token.groups()
            tokens.append(re.sub(r'\\(["\\])', r"\1", quoted) if quoted is not None else literal)
            rest = rest[token.end():].lstrip(" ")
        commands.append(tokens)
    return commands


def hook_member(apply: bytes) -> str:
    hooks = []
    for verb, *args in script_lines(apply, "apply.sh"):
        if verb == "log" and args:
            continue
        if verb != "hook_apps" or not 3 <= len(args) <= 99:
            raise ValueError("apply.sh: expected one hook_apps <jar> <class> <process>... declaration")
        jar, entry, *processes = args
        if not HOOK_PATH.fullmatch(jar) or ".." in jar or "/./" in jar:
            raise ValueError(f"apply.sh: invalid hook payload path {jar!r}")
        if not HOOK_CLASS.fullmatch(entry) or any(not HOOK_PROCESS.fullmatch(p) for p in processes):
            raise ValueError("apply.sh: invalid hook_apps entry or process")
        if len(processes) != len(set(processes)):
            raise ValueError("apply.sh: repeated hook process")
        hooks.append(jar)
    if len(hooks) != 1:
        raise ValueError("apply.sh: expected exactly one hook_apps registration")
    return hooks[0]


def localized_strings(data: bytes, member: str) -> dict[str, str]:
    entries = read_entries(data, member)
    if len(data) > 2048 or len(entries) > 64:
        raise ValueError(f"{member}: exceeds the Seogaemo string limits")
    for key, value in entries.items():
        if not NAME.fullmatch(key) or len(key) > 40 or len(value.encode("utf-8")) > 200:
            raise ValueError(f"{member}: invalid string {key!r}")
    if not entries.get("name") or not entries.get("summary"):
        raise ValueError(f"{member}: name and summary are required")
    return entries


def validate_module_text(members: dict[str, bytes], en: dict[str, str]) -> None:
    def is_ref(value: str) -> bool:
        return value.startswith("@") and value[1:] in en

    if "check.sh" in members:
        guard = [["if", "not", "hookpoints_ok"], ["then"], ["block", "@map_required"], ["fi"]]
        if script_lines(members["check.sh"], "check.sh") != guard or not is_ref("@map_required"):
            raise ValueError("check.sh: expected the Seogaemo vehicle map check")

    if "status.sh" in members:
        for verb, *args in script_lines(members["status.sh"], "status.sh"):
            if verb == "log" and args:
                continue
            if verb == "fail" and len(args) == 1 and is_ref(args[0]):
                continue
            if verb == "info" and len(args) == 3 and NAME.fullmatch(args[0]):
                if args[1:] == ["setting", SETTING]:
                    continue
            raise ValueError(f"status.sh: invalid {verb!r} declaration")

    if "ui.txt" in members:
        data = members["ui.txt"]
        lines = [line for line in content_lines(data, "ui.txt") if line and not line.startswith("#")]
        if len(data) > 1024 or len(lines) > 32:
            raise ValueError("ui.txt: exceeds the Seogaemo UI limits")
        for line in lines:
            if len(line.encode("utf-8")) > 200:
                raise ValueError("ui.txt: line exceeds 200 bytes")
            tokens = line.split()
            if not tokens or tokens[0].startswith("#"):
                continue
            block, *args = tokens
            if block == "status" and not args:
                continue
            if block in {"info", "warning"} and len(args) == 1 and is_ref(args[0]):
                continue
            if block == "toggle" and len(args) == 2 and args[0] == f"setting={SETTING}":
                if args[1].startswith("label=") and is_ref(args[1][len("label="):]):
                    continue
            if block == "value" and len(args) == 2 and args[0].startswith("key="):
                if NAME.fullmatch(args[0][len("key="):]) and args[1].startswith("label="):
                    if is_ref(args[1][len("label="):]):
                        continue
            raise ValueError(f"ui.txt: invalid {block!r} declaration")

    if "README.md" in members:
        content_lines(members["README.md"], "README.md")


def validate_dex_jar(data: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as jar:
        if jar.namelist() != ["classes.dex"]:
            raise ValueError("hook JAR must have exactly one classes.dex member")
        info = jar.getinfo("classes.dex")
        if info.file_size > MAX_EXPANDED or info.flag_bits & 1:
            raise ValueError("invalid hook JAR DEX size or encryption")
        dex = jar.read(info)
    if len(dex) < 112 or not re.fullmatch(rb"dex\n[0-9]{3}\x00", dex[:8]):
        raise ValueError("hook JAR has an invalid DEX magic or header")
    file_size, header_size, endian = struct.unpack_from("<III", dex, 32)
    if (file_size, header_size, endian) != (len(dex), 112, 0x12345678):
        raise ValueError("hook JAR has inconsistent DEX header fields")
    signature = hashlib.sha1(dex[32:]).digest()  # Required DEX header field.
    checksum = zlib.adler32(dex[12:])
    if dex[12:32] != signature or struct.unpack_from("<I", dex, 8)[0] != checksum:
        raise ValueError("hook JAR DEX SHA-1 or Adler-32 check failed")


def validate_members(members: dict[str, bytes]) -> dict[str, str]:
    missing = set(REQUIRED_TEXT) - members.keys()
    if missing:
        raise ValueError(f"missing HSM members: {', '.join(sorted(missing))}")
    props = module_properties(members["module.properties"])
    hook = hook_member(members["apply.sh"])
    if hook not in members:
        raise ValueError(f"missing hook payload: {hook}")
    unexpected = members.keys() - {hook, *REQUIRED_TEXT, *OPTIONAL_TEXT}
    if unexpected:
        raise ValueError(f"unexpected HSM members: {', '.join(sorted(unexpected))}")
    en = localized_strings(members["strings/en.txt"], "strings/en.txt")
    ko = localized_strings(members["strings/ko.txt"], "strings/ko.txt")
    if en.keys() != ko.keys():
        raise ValueError("English and Korean string keys differ")
    validate_module_text(members, en)
    validate_dex_jar(members[hook])
    return props


def read_archive(data: bytes) -> dict[str, bytes]:
    if not 0 < len(data) <= MAX_ARCHIVE:
        raise ValueError("HSM archive exceeds the USB import limit or is empty")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES or sum(info.file_size for info in entries) > MAX_EXPANDED:
            raise ValueError("HSM archive exceeds Seogaemo extraction limits")
        members = {}
        for info in entries:
            name = info.filename
            if name in members or name != info.orig_filename or info.is_dir():
                raise ValueError(f"unexpected or repeated ZIP member: {name!r}")
            if stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG) or info.flag_bits & 1:
                raise ValueError(f"ZIP member is not a regular, unencrypted file: {name!r}")
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError(f"unsupported ZIP compression: {name!r}")
            members[name] = archive.read(info)
    return members


def make_archive(members: dict[str, bytes]) -> bytes:
    if sum(map(len, members.values())) > MAX_EXPANDED:
        raise ValueError("HSM members exceed the Seogaemo extraction limit")
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", allowZip64=False) as archive:
        for name, contents in sorted(members.items()):
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, contents)
    return data.getvalue()


def read_archive_file(path: Path) -> bytes:
    with path.open("rb") as archive:
        return archive.read(MAX_ARCHIVE + 1)


def sibling(path: Path, suffix: str) -> Path:
    return path.with_name(path.name + suffix)


def atomic_write(path: Path, contents: bytes, *, replace: bool = True) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temp_path = Path(temporary.name)
        try:
            temporary.write(contents)
            temporary.close()
            if replace:
                os.replace(temp_path, path)
            else:
                os.link(temp_path, path)
        finally:
            temporary.close()
            temp_path.unlink(missing_ok=True)


def load_signing_key(path: Path) -> Ed25519PrivateKey:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        try:
            atomic_write(path, pem, replace=False)
        except FileExistsError:
            pass  # A parallel build already generated the local key.
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("local signing key must be an Ed25519 PEM private key")
    return key


def public_pem(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def verify_hsm(path: Path, *, trusted_public_key: Path | None = None) -> str:
    """Verify archive, checksum and detached Ed25519 signature, returning its SHA-256."""
    data = read_archive_file(path)
    digest = hashlib.sha256(data).hexdigest()
    if sibling(path, ".sha256").read_bytes() != (digest + "\n").encode("ascii"):
        raise ValueError("HSM SHA-256 sidecar does not match the archive")
    pem = sibling(path, ".pub.pem").read_bytes()
    signer = serialization.load_pem_public_key(pem)
    if not isinstance(signer, Ed25519PublicKey):
        raise ValueError("HSM public key must be an Ed25519 PEM key")
    if trusted_public_key is not None:
        trusted = serialization.load_pem_public_key(trusted_public_key.read_bytes())
        if not isinstance(trusted, Ed25519PublicKey) or public_pem(trusted) != public_pem(signer):
            raise ValueError("HSM public key does not match the separately trusted key")
    try:
        signer.verify(sibling(path, ".sig").read_bytes(), data)
    except InvalidSignature as error:
        raise ValueError("HSM Ed25519 signature verification failed") from error
    props = validate_members(read_archive(data))
    if path.name != f"{props['id']}-{props['version']}.hsm":
        raise ValueError("HSM archive filename does not match the module properties")
    return digest


def build_hsm(module_dir: Path, hook_jar: Path, dist_dir: Path, signing_key: Path) -> Path:
    """Package a built hook with the module, sign it locally, and verify the result."""
    members = {name: (module_dir / name).read_bytes() for name in REQUIRED_TEXT}
    for name in OPTIONAL_TEXT:
        source = module_dir / name
        if source.is_file():
            members[name] = source.read_bytes()
    members[hook_member(members["apply.sh"])] = hook_jar.read_bytes()
    props = validate_members(members)
    data = make_archive(members)

    key = load_signing_key(signing_key)
    archive_name = f"{props['id']}-{props['version']}.hsm"
    dist_dir.mkdir(parents=True, exist_ok=True)
    result = dist_dir / archive_name
    pem = public_pem(key.public_key())
    digest = hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory(dir=dist_dir) as working:
        staged = Path(working) / archive_name
        staged.write_bytes(data)
        sibling(staged, ".sha256").write_bytes((digest + "\n").encode("ascii"))
        sibling(staged, ".sig").write_bytes(key.sign(data))
        sibling(staged, ".pub.pem").write_bytes(pem)
        verify_hsm(staged)
        for suffix in (".sha256", ".sig", ".pub.pem", ""):
            sibling(staged, suffix).replace(sibling(result, suffix))
    return result
